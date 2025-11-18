"""
题目裁剪器 - 从单张图片中裁剪指定题目
根据题号检测bbox，裁剪图片并上传到bucket
"""
import os
import json
import base64
import re
import cv2
import numpy as np
from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.id import ID
from appwrite.input_file import InputFile
from llm_provider import get_llm_provider
from utils import success_response, error_response, parse_request_body


# Configuration
ORIGIN_IMAGE_BUCKET = os.environ.get('APPWRITE_STORAGE_BUCKET_ID', 'origin_question_image')


def get_storage() -> Storage:
    """Initialize Storage service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Storage(client)


def download_image_from_storage(storage: Storage, file_id: str) -> bytes:
    """从 storage bucket 下载图片"""
    try:
        result = storage.get_file_download(
            bucket_id=ORIGIN_IMAGE_BUCKET,
            file_id=file_id
        )
        return result
    except Exception as e:
        raise ValueError(f"下载图片失败: {str(e)}")


def parse_bbox_from_response(response: str) -> tuple:
    """从LLM响应中解析bbox坐标"""
    # 匹配 <bbox>x1 y1 x2 y2</bbox> 格式
    bbox_pattern = r'<bbox>\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*</bbox>'
    match = re.search(bbox_pattern, response)
    
    if match:
        x_min = int(match.group(1))
        y_min = int(match.group(2))
        x_max = int(match.group(3))
        y_max = int(match.group(4))
        return (x_min, y_min, x_max, y_max)
    
    # 尝试其他格式：bbox: x1 y1 x2 y2
    bbox_pattern2 = r'bbox[:\s]+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)'
    match2 = re.search(bbox_pattern2, response, re.IGNORECASE)
    
    if match2:
        x_min = int(match2.group(1))
        y_min = int(match2.group(2))
        x_max = int(match2.group(3))
        y_max = int(match2.group(4))
        return (x_min, y_min, x_max, y_max)
    
    # 尝试提取数字数组
    numbers = re.findall(r'\d+', response)
    if len(numbers) >= 4:
        x_min = int(numbers[0])
        y_min = int(numbers[1])
        x_max = int(numbers[2])
        y_max = int(numbers[3])
        return (x_min, y_min, x_max, y_max)
    
    raise ValueError(f"无法从响应中解析bbox坐标: {response}")


def crop_question(image_file_id: str, question_number: str) -> dict:
    """裁剪指定题目"""
    storage = get_storage()
    
    # 1. 下载原图
    print(f"正在下载图片: {image_file_id}")
    image_bytes = download_image_from_storage(storage, image_file_id)
    
    # 2. 读取图片
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if image is None:
        raise ValueError("无法解码图片")
    
    h, w = image.shape[:2]
    print(f"图片尺寸: {w}x{h}")
    
    # 3. 转换为base64供LLM使用
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    image_base64_with_prefix = f"data:image/jpeg;base64,{image_base64}"
    
    # 4. 使用LLM检测bbox
    print(f"正在检测题目 '{question_number}' 的bbox...")
    provider = get_llm_provider()
    
    prompt = f'请检测图像中的"{question_number}"，覆盖完全题目内容和选项，检测精准，无需识别题目内容。以<bbox>x1 y1 x2 y2</bbox>的形式表示，坐标范围为0-1000（归一化到1000*1000的比例坐标）'
    
    try:
        response = provider.chat_with_vision(
            prompt=prompt,
            image_base64=image_base64_with_prefix,
            temperature=0.3,  # 降低温度以提高准确性
        )
        
        print(f"LLM响应: {response}")
        
        # 5. 解析bbox坐标（0-1000归一化）
        x_min, y_min, x_max, y_max = parse_bbox_from_response(response)
        
        # 验证坐标范围
        if not (0 <= x_min < x_max <= 1000 and 0 <= y_min < y_max <= 1000):
            raise ValueError(f"bbox坐标超出范围: ({x_min}, {y_min}, {x_max}, {y_max})")
        
        # 6. 转换为实际像素坐标
        x_min_real = int(x_min * w / 1000)
        y_min_real = int(y_min * h / 1000)
        x_max_real = int(x_max * w / 1000)
        y_max_real = int(y_max * h / 1000)
        
        print(f"原始bbox: ({x_min_real}, {y_min_real}, {x_max_real}, {y_max_real})")
        
        # 7. 扩大10%边距以消除误差
        width = x_max_real - x_min_real
        height = y_max_real - y_min_real
        margin_x = int(width * 0.1)
        margin_y = int(height * 0.1)
        
        x_min_real = max(0, x_min_real - margin_x)
        y_min_real = max(0, y_min_real - margin_y)
        x_max_real = min(w, x_max_real + margin_x)
        y_max_real = min(h, y_max_real + margin_y)
        
        print(f"扩大边距后bbox: ({x_min_real}, {y_min_real}, {x_max_real}, {y_max_real})")
        
        # 8. 裁剪图片
        cropped_image = image[y_min_real:y_max_real, x_min_real:x_max_real]
        
        if cropped_image.size == 0:
            raise ValueError("裁剪后的图片为空")
        
        # 9. 编码为JPEG
        _, encoded_image = cv2.imencode('.jpg', cropped_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        cropped_bytes = encoded_image.tobytes()
        
        # 10. 上传裁剪后的图片到bucket
        print("正在上传裁剪后的图片...")
        cropped_file_id = ID.unique()
        cropped_file_name = f"cropped_{question_number.replace(' ', '_')}_{cropped_file_id}.jpg"
        
        # Appwrite Python SDK 需要 InputFile 对象
        from appwrite.input_file import InputFile
        
        storage.create_file(
            bucket_id=ORIGIN_IMAGE_BUCKET,
            file_id=cropped_file_id,
            file=InputFile.from_bytes(cropped_bytes, filename=cropped_file_name)
        )
        
        print(f"✓ 成功上传裁剪图片: {cropped_file_id}")
        
        return {
            'success': True,
            'croppedImageId': cropped_file_id
        }
        
    except Exception as e:
        print(f"裁剪失败: {str(e)}")
        raise ValueError(f"题目裁剪失败: {str(e)}")


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        image_file_id = body.get('imageFileId')
        question_number = body.get('questionNumber')
        
        if not image_file_id:
            return res.json(error_response("缺少参数: imageFileId", 400))
        if not question_number:
            return res.json(error_response("缺少参数: questionNumber", 400))
        
        # 裁剪题目
        result = crop_question(image_file_id, question_number)
        
        return res.json(success_response(result, "题目裁剪成功"))
        
    except ValueError as e:
        return res.json(error_response(str(e), 400))
    except Exception as e:
        context.log(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json(error_response(f"服务器错误: {str(e)}", 500))


"""
题目检测器 - 从单张图片中检测所有题目
检测图像中的所有题目，返回题号列表
"""
import os
import json
import base64
import sys
import ast
from appwrite.client import Client
from appwrite.services.storage import Storage

# 添加当前目录到 Python 路径，确保可以导入同目录下的模块
sys.path.insert(0, os.path.dirname(__file__))

# 尝试导入 LLM provider（需要根据实际路径调整）
try:
    from .llm_provider import get_llm_provider
except ImportError:
    # 如果相对导入失败，尝试从当前目录导入
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


def parse_questions_from_response(response: str) -> list:
    """从LLM响应中解析题目列表"""
    if not response or not response.strip():
        return []
    
    # 清理响应，移除可能的 Markdown 代码块标记
    cleaned_response = response.strip()
    # 移除可能的 ```json 或 ``` 标记
    if cleaned_response.startswith('```'):
        lines = cleaned_response.split('\n')
        cleaned_response = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned_response
        cleaned_response = cleaned_response.strip()
    
    # 先尝试解析JSON（双引号格式）
        try:
        questions = json.loads(cleaned_response)
        if isinstance(questions, list):
            result = [str(q).strip() for q in questions if q]
            print(f"JSON解析成功，得到 {len(result)} 个题目: {result}")
            return result
    except json.JSONDecodeError:
        # JSON解析失败，尝试使用 ast.literal_eval 解析Python字面量（单引号格式）
        try:
            questions = ast.literal_eval(cleaned_response)
            if isinstance(questions, list):
                result = [str(q).strip() for q in questions if q]
                print(f"Python字面量解析成功，得到 {len(result)} 个题目: {result}")
                return result
        except (ValueError, SyntaxError) as e:
            print(f"解析失败: {e}, 响应内容: {cleaned_response[:200]}")
    
    # 如果解析失败，返回空列表
    return []


def detect_questions(image_file_id: str) -> dict:
    """检测图片中的所有题目"""
    storage = get_storage()
    
    # 1. 下载图片
    print(f"正在下载图片: {image_file_id}")
    image_bytes = download_image_from_storage(storage, image_file_id)
    
    # 2. 转换为base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    image_base64_with_prefix = f"data:image/jpeg;base64,{image_base64}"
    
    # 3. 使用LLM检测题目
    print("正在使用LLM检测题目...")
    provider = get_llm_provider()
    
    prompt = """请检测图像中的所有题目，覆盖完全题目内容和选项，检测精准全面，无需识别题目内容。忽略内容不全的题目和手写痕迹，但是不要漏题。输出题号列表，例如['第一题','第二题','第三题(1)','第三题(4)']"""
    
    try:
        response = provider.chat_with_vision(
            prompt=prompt,
            image_base64=image_base64_with_prefix,
            temperature=0.6,  # 降低温度以提高准确性
        )
        
        print(f"LLM响应: {response}")
        
        # 4. 解析题目列表
        questions = parse_questions_from_response(response)
        
        if not questions:
            raise ValueError("未能从响应中解析出题目列表，请检查图片是否包含题目")
        
        print(f"检测到 {len(questions)} 个题目: {questions}")
        
        return {
            'success': True,
            'questions': questions
        }
        
    except Exception as e:
        print(f"LLM检测失败: {str(e)}")
        raise ValueError(f"题目检测失败: {str(e)}")


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        image_file_id = body.get('imageFileId')
        
        if not image_file_id:
            return res.json(error_response("缺少参数: imageFileId", 400))
        
        # 检测题目
        result = detect_questions(image_file_id)
        
        return res.json(success_response(result, "题目检测成功"))
        
    except ValueError as e:
        return res.json(error_response(str(e), 400))
    except Exception as e:
        context.log(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json(error_response(f"服务器错误: {str(e)}", 500))


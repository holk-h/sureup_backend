"""
题目裁剪 Worker

功能：
1. 接收裁剪任务
2. 下载原图
3. 使用 LLM 检测题目 bbox
4. 裁剪图片
5. 上传裁剪后的图片
6. 更新任务状态
"""

import os
import asyncio
import base64
import re
import cv2
import numpy as np
from typing import Dict, Any, Tuple, Optional
from loguru import logger

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.id import ID
from appwrite.input_file import InputFile

from ..base import BaseWorker


# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
QUESTION_CROPPING_TASKS_COLLECTION = 'question_cropping_tasks'
ORIGIN_IMAGE_BUCKET = os.environ.get('APPWRITE_STORAGE_BUCKET_ID', 'origin_question_image')


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


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
    # 确保 response 是字符串类型
    if not isinstance(response, str):
        response = str(response)
    
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


def get_llm_provider():
    """获取 LLM Provider"""
    # 使用错题分析器的 LLM Provider
    from workers.mistake_analyzer.core.llm_provider import get_llm_provider as get_provider
    return get_provider()


class QuestionCropperWorker(BaseWorker):
    """题目裁剪 Worker"""
    
    def __init__(self):
        """初始化 Worker"""
        super().__init__()
        self.databases = None
        self.storage = None
        self.llm_provider = None
    
    def _init_services(self):
        """初始化服务"""
        if not self.databases:
            self.databases = get_databases()
        if not self.storage:
            self.storage = get_storage()
        if not self.llm_provider:
            self.llm_provider = get_llm_provider()
    
    async def _process_single_question(
        self,
        question_number: str,
        image: np.ndarray,
        image_base64_with_prefix: str,
        w: int,
        h: int,
        task_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        处理单个题目的裁剪
        
        Args:
            question_number: 题号
            image: 原始图片（numpy数组）
            image_base64_with_prefix: base64编码的图片（带前缀）
            w: 图片宽度
            h: 图片高度
            task_id: 任务ID
            
        Returns:
            Tuple[Optional[str], Optional[str]]: 
                - 成功时返回 (cropped_file_id, None)
                - 失败时返回 (None, error_message)
        """
        try:
            logger.info(f"正在处理题目: {question_number}")
            
            # 1. 使用LLM检测bbox
            prompt = f'请检测图像中的"{question_number}"，覆盖完全题目内容和选项，检测精准，无需识别题目内容。以<bbox>x1 y1 x2 y2</bbox>的形式表示，坐标范围为0-1000（归一化到1000*1000的比例坐标）'
            
            response = await self.llm_provider.chat_with_vision(
                prompt=prompt,
                image_base64=image_base64_with_prefix,
                temperature=0.3,
            )
            
            # 确保 response 是字符串
            if not isinstance(response, str):
                response = str(response)
            
            logger.info(f"LLM响应 ({question_number}): {response}")
            
            # 2. 解析bbox坐标（0-1000归一化）
            x_min, y_min, x_max, y_max = parse_bbox_from_response(response)
            
            # 验证坐标范围
            if not (0 <= x_min < x_max <= 1000 and 0 <= y_min < y_max <= 1000):
                raise ValueError(f"bbox坐标超出范围: ({x_min}, {y_min}, {x_max}, {y_max})")
            
            # 3. 转换为实际像素坐标
            x_min_real = int(x_min * w / 1000)
            y_min_real = int(y_min * h / 1000)
            x_max_real = int(x_max * w / 1000)
            y_max_real = int(y_max * h / 1000)
            
            logger.info(f"原始bbox ({question_number}): ({x_min_real}, {y_min_real}, {x_max_real}, {y_max_real})")
            
            # 4. 扩大10%边距以消除误差
            width = x_max_real - x_min_real
            height = y_max_real - y_min_real
            margin_x = int(width * 0.1)
            margin_y = int(height * 0.1)
            
            x_min_real = max(0, x_min_real - margin_x)
            y_min_real = max(0, y_min_real - margin_y)
            x_max_real = min(w, x_max_real + margin_x)
            y_max_real = min(h, y_max_real + margin_y)
            
            logger.info(f"扩大边距后bbox ({question_number}): ({x_min_real}, {y_min_real}, {x_max_real}, {y_max_real})")
            
            # 5. 裁剪图片
            cropped_image = image[y_min_real:y_max_real, x_min_real:x_max_real]
            
            if cropped_image.size == 0:
                raise ValueError("裁剪后的图片为空")
            
            # 6. 编码为JPEG
            _, encoded_image = cv2.imencode('.jpg', cropped_image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            cropped_bytes = encoded_image.tobytes()
            
            # 7. 上传裁剪后的图片到bucket
            logger.info(f"正在上传裁剪后的图片: {question_number}")
            cropped_file_id = ID.unique()
            cropped_file_name = f"cropped_{question_number.replace(' ', '_')}_{cropped_file_id}.jpg"
            
            # 使用 bucket 的默认权限
            await asyncio.to_thread(
                self.storage.create_file,
                bucket_id=ORIGIN_IMAGE_BUCKET,
                file_id=cropped_file_id,
                file=InputFile.from_bytes(cropped_bytes, filename=cropped_file_name),
                permissions=['read("any")', 'update("users")', 'delete("users")']
            )
            
            logger.info(f"✓ 成功上传裁剪图片 ({question_number}): {cropped_file_id}")
            return (cropped_file_id, None)
            
        except Exception as e:
            error_msg = f"{question_number}: {str(e)}"
            logger.error(f"处理题目 '{question_number}' 失败: {str(e)}", exc_info=True)
            return (None, error_msg)
    
    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理裁剪任务（处理多个题目，并行处理）
        
        Args:
            task_data: 任务数据，包含：
                - task_id: 任务ID
                - user_id: 用户ID
                - image_file_id: 原图文件ID
                - question_numbers: 题号列表
                
        Returns:
            处理结果
        """
        task_id = task_data.get('task_id')
        user_id = task_data.get('user_id')
        image_file_id = task_data.get('image_file_id')
        question_numbers = task_data.get('question_numbers', [])
        
        logger.info(f"收到裁剪任务: task_id={task_id}, questions={question_numbers}, count={len(question_numbers)}")
        
        # 初始化服务
        self._init_services()
        
        cropped_image_ids = []
        failed_questions = []
        progress_lock = asyncio.Lock()
        
        try:
            # 1. 更新状态为 processing
            await self._update_task_status(task_id, 'processing', completed_count=0)
            
            # 2. 下载原图（异步）
            logger.info(f"正在下载图片: {image_file_id}")
            image_bytes = await asyncio.to_thread(
                download_image_from_storage,
                self.storage,
                image_file_id
            )
            
            # 3. 读取图片
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise ValueError("无法解码图片")
            
            h, w = image.shape[:2]
            logger.info(f"图片尺寸: {w}x{h}")
            
            # 4. 转换为base64供LLM使用
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            image_base64_with_prefix = f"data:image/jpeg;base64,{image_base64}"
            
            # 5. 创建并行任务处理所有题目
            async def process_with_progress_update(question_number: str):
                """处理单个题目并更新进度"""
                cropped_file_id, error_msg = await self._process_single_question(
                    question_number=question_number,
                    image=image,
                    image_base64_with_prefix=image_base64_with_prefix,
                    w=w,
                    h=h,
                    task_id=task_id
                )
                
                # 使用锁来安全地更新共享状态
                async with progress_lock:
                    if cropped_file_id:
                        cropped_image_ids.append(cropped_file_id)
                    else:
                        failed_questions.append(error_msg)
                    
                    # 更新进度
                    await self._update_task_status(
                        task_id,
                        'processing',
                        completed_count=len(cropped_image_ids),
                        cropped_image_ids=cropped_image_ids.copy()  # 使用副本避免并发问题
                    )
                
                return cropped_file_id, error_msg
            
            # 6. 并行处理所有题目
            logger.info(f"开始并行处理 {len(question_numbers)} 个题目")
            tasks = [
                process_with_progress_update(question_number)
                for question_number in question_numbers
            ]
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理异常结果
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"任务执行异常: {str(result)}", exc_info=True)
                    failed_questions.append(f"任务异常: {str(result)}")
            
            logger.info(f"并行处理完成: 成功 {len(cropped_image_ids)}, 失败 {len(failed_questions)}")
            
            # 7. 所有题目处理完成，更新最终状态
            if len(cropped_image_ids) == 0:
                # 所有题目都失败了
                await self._update_task_status(
                    task_id,
                    'failed',
                    error=f"所有题目裁剪失败: {', '.join(failed_questions)}"
                )
                raise Exception(f"所有题目裁剪失败: {', '.join(failed_questions)}")
            elif len(cropped_image_ids) < len(question_numbers):
                # 部分成功
                await self._update_task_status(
                    task_id,
                    'completed',
                    completed_count=len(cropped_image_ids),
                    cropped_image_ids=cropped_image_ids,
                    error=f"部分题目失败: {', '.join(failed_questions)}" if failed_questions else None
                )
            else:
                # 全部成功
                await self._update_task_status(
                    task_id,
                    'completed',
                    completed_count=len(cropped_image_ids),
                    cropped_image_ids=cropped_image_ids
                )
            
            return {
                'success': True,
                'task_id': task_id,
                'cropped_image_ids': cropped_image_ids,
                'failed_count': len(failed_questions),
                'message': f'裁剪完成: {len(cropped_image_ids)}/{len(question_numbers)} 成功'
            }
            
        except Exception as e:
            logger.error(f"裁剪任务失败: {str(e)}", exc_info=True)
            # 更新任务状态为 failed
            await self._update_task_status(
                task_id,
                'failed',
                error=str(e),
                cropped_image_ids=cropped_image_ids if cropped_image_ids else None
            )
            raise
    
    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        completed_count: int = None,
        cropped_image_ids: list = None,
        error: str = None
    ):
        """更新任务状态"""
        update_data = {
            'status': status,
        }
        
        if completed_count is not None:
            update_data['completedCount'] = completed_count
        
        if cropped_image_ids is not None:
            update_data['croppedImageIds'] = cropped_image_ids
        
        if error:
            update_data['error'] = error
        
        # 使用 asyncio.to_thread 将同步调用转换为异步
        await asyncio.to_thread(
            self.databases.update_document,
            database_id=DATABASE_ID,
            collection_id=QUESTION_CROPPING_TASKS_COLLECTION,
            document_id=task_id,
            data=update_data
        )


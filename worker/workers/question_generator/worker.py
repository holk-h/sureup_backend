"""
题目生成 Worker

功能：
1. 接收题目生成任务
2. 读取源题目信息
3. 调用 LLM 生成变式题
4. 解析并验证生成结果
5. 写入题目库
6. 更新任务进度

环境变量：
- APPWRITE_ENDPOINT: Appwrite API 端点
- APPWRITE_PROJECT_ID: 项目 ID
- APPWRITE_API_KEY: API Key
- APPWRITE_DATABASE_ID: 数据库 ID
- DOUBAO_API_KEY: 豆包/火山引擎 API Key
- DOUBAO_MODEL: 豆包模型 ID
"""

import os
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.exception import AppwriteException

from ..base import BaseWorker
from .llm_provider import get_llm_provider
from .prompts import SYSTEM_PROMPT, build_variant_prompt


class QuestionGeneratorWorker(BaseWorker):
    """题目生成 Worker"""
    
    def __init__(self):
        """初始化 Worker"""
        super().__init__()
        
        # 初始化 Appwrite 客户端
        self.client = Client()
        self.client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
        self.client.set_project(os.environ.get('APPWRITE_PROJECT_ID'))
        self.client.set_key(os.environ.get('APPWRITE_API_KEY'))
        
        self.databases = Databases(self.client)
        self.database_id = os.environ.get('APPWRITE_DATABASE_ID', 'main')
        
        # 初始化 LLM Provider
        self.llm_provider = get_llm_provider(
            temperature=0.8,  # 需要创造性
            max_tokens=4096
        )
        
        print("[题目生成Worker] 初始化完成")
    
    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        实现 BaseWorker 的 process 方法
        
        Args:
            task_data: 任务数据
            
        Returns:
            处理结果
        """
        return await self.process_task(task_data)
    
    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理题目生成任务
        
        Args:
            task_data: 任务数据，包含：
                - task_id: 任务 ID
                - user_id: 用户 ID
                - task_type: 任务类型（variant）
                - source_question_ids: 源题目 ID 列表
                - variants_per_question: 每题生成的变式数量
                
        Returns:
            处理结果
        """
        
        task_id = task_data.get('task_id')
        user_id = task_data.get('user_id')
        task_type = task_data.get('task_type', 'variant')
        source_question_ids = task_data.get('source_question_ids', [])
        variants_per_question = task_data.get('variants_per_question', 1)
        
        print(f"\n[题目生成Worker] 开始处理任务")
        print(f"  - 任务ID: {task_id}")
        print(f"  - 用户ID: {user_id}")
        print(f"  - 任务类型: {task_type}")
        print(f"  - 源题目数: {len(source_question_ids)}")
        print(f"  - 每题变式数: {variants_per_question}")
        
        generated_question_ids = []
        errors = []
        
        try:
            # 遍历每个源题目
            for idx, source_question_id in enumerate(source_question_ids):
                try:
                    print(f"\n[{idx + 1}/{len(source_question_ids)}] 处理源题目: {source_question_id}")
                    
                    # 获取源题目
                    source_question = self.databases.get_document(
                        database_id=self.database_id,
                        collection_id='questions',
                        document_id=source_question_id
                    )
                    
                    print(f"  - 科目: {source_question.get('subject')}")
                    print(f"  - 类型: {source_question.get('type')}")
                    print(f"  - 难度: {source_question.get('difficulty')}")
                    
                    # 生成变式题
                    variant_questions = await self._generate_variants(
                        source_question=source_question,
                        count=variants_per_question
                    )
                    
                    print(f"  ✓ 成功生成 {len(variant_questions)} 道变式题")
                    
                    # 保存生成的题目
                    for variant_idx, variant_data in enumerate(variant_questions):
                        try:
                            new_question_id = await self._save_question(
                                user_id=user_id,
                                source_question=source_question,
                                variant_data=variant_data
                            )
                            generated_question_ids.append(new_question_id)
                            print(f"    [{variant_idx + 1}] 已保存: {new_question_id}")
                            
                        except Exception as e:
                            error_msg = f"保存变式题失败: {str(e)}"
                            print(f"    ✗ {error_msg}")
                            errors.append(error_msg)
                    
                    # 更新任务进度
                    await self._update_task_progress(
                        task_id=task_id,
                        completed_count=len(generated_question_ids),
                        generated_question_ids=generated_question_ids
                    )
                    
                except Exception as e:
                    error_msg = f"处理源题目 {source_question_id} 失败: {str(e)}"
                    print(f"  ✗ {error_msg}")
                    errors.append(error_msg)
                    continue
            
            # 标记任务完成
            await self._complete_task(
                task_id=task_id,
                generated_question_ids=generated_question_ids,
                errors=errors
            )
            
            print(f"\n[题目生成Worker] 任务完成")
            print(f"  - 成功生成: {len(generated_question_ids)} 题")
            print(f"  - 失败数量: {len(errors)}")
            
            return {
                'success': True,
                'task_id': task_id,
                'generated_count': len(generated_question_ids),
                'generated_question_ids': generated_question_ids,
                'errors': errors
            }
            
        except Exception as e:
            error_msg = f"任务处理失败: {str(e)}"
            print(f"\n[题目生成Worker] ✗ {error_msg}")
            
            # 标记任务失败
            try:
                self.databases.update_document(
                    database_id=self.database_id,
                    collection_id='question_generation_tasks',
                    document_id=task_id,
                    data={
                        'status': 'failed',
                        'error': error_msg,
                        'completedAt': datetime.utcnow().isoformat() + 'Z',
                        'generatedQuestionIds': generated_question_ids
                    }
                )
            except:
                pass
            
            return {
                'success': False,
                'task_id': task_id,
                'error': error_msg,
                'generated_question_ids': generated_question_ids
            }
    
    async def _generate_variants(
        self,
        source_question: Dict[str, Any],
        count: int = 1
    ) -> List[Dict[str, Any]]:
        """
        生成变式题
        
        Args:
            source_question: 源题目数据
            count: 生成数量
            
        Returns:
            变式题列表
        """
        
        # 构建提示词
        prompt = build_variant_prompt(source_question, count)
        
        print(f"  → 调用 LLM 生成变式题...")
        
        # 调用 LLM
        response = await self.llm_provider.chat(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.8,
            max_tokens=4096
        )
        
        print(f"  ← LLM 响应完成，长度: {len(response)} 字符")
        
        # 解析响应
        variants = self._parse_llm_response(response)
        
        if not variants or len(variants) == 0:
            raise ValueError("LLM 未返回有效的变式题")
        
        return variants
    
    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析 LLM 响应（分段标记格式）
        
        Args:
            response: LLM 响应文本
            
        Returns:
            解析后的题目列表
        """
        import re
        
        # 清理响应（移除可能的 markdown 标记）
        response = response.strip()
        if response.startswith('```'):
            lines = response.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response = '\n'.join(lines)
        
        # 按 ##QUESTION## 分割多个题目
        question_blocks = re.split(r'##QUESTION##', response)
        
        validated_data = []
        
        for idx, block in enumerate(question_blocks):
            block = block.strip()
            if not block:
                continue
            
            try:
                # 解析单个题目
                question = self._parse_single_question(block)
                if question and self._validate_question_data(question):
                    validated_data.append(question)
                    print(f"  ✓ 成功解析题目 {idx}: {question['type']}, 难度 {question['difficulty']}")
                else:
                    print(f"  ⚠️ 跳过无效的题目 {idx}")
            except Exception as e:
                print(f"  ✗ 解析题目 {idx} 失败: {str(e)}")
                continue
        
        if not validated_data:
            raise ValueError("未能解析出任何有效题目")
        
        return validated_data
    
    def _parse_single_question(self, block: str) -> Dict[str, Any]:
        """
        解析单个题目的分段标记格式
        
        Args:
            block: 单个题目的文本块
            
        Returns:
            题目数据字典
        """
        import re
        
        question = {}
        
        # 提取 TYPE
        type_match = re.search(r'##TYPE##\s*\n\s*(\w+)', block, re.IGNORECASE)
        if type_match:
            question['type'] = type_match.group(1).strip()
        
        # 提取 DIFFICULTY
        diff_match = re.search(r'##DIFFICULTY##\s*\n\s*(\d+)', block, re.IGNORECASE)
        if diff_match:
            question['difficulty'] = int(diff_match.group(1).strip())
        
        # 提取 CONTENT
        content_match = re.search(r'##CONTENT##\s*\n(.*?)(?=##OPTIONS##|##ANSWER##|##END##|$)', 
                                 block, re.DOTALL | re.IGNORECASE)
        if content_match:
            question['content'] = content_match.group(1).strip()
        
        # 提取 OPTIONS
        options_match = re.search(r'##OPTIONS##\s*\n(.*?)(?=##ANSWER##|##EXPLANATION##|##END##|$)', 
                                 block, re.DOTALL | re.IGNORECASE)
        if options_match:
            options_text = options_match.group(1).strip()
            if options_text:
                # 按行分割选项，过滤空行
                question['options'] = [
                    line.strip() 
                    for line in options_text.split('\n') 
                    if line.strip()
                ]
            else:
                question['options'] = []
        else:
            question['options'] = []
        
        # 提取 ANSWER
        answer_match = re.search(r'##ANSWER##\s*\n(.*?)(?=##EXPLANATION##|##END##|$)', 
                                block, re.DOTALL | re.IGNORECASE)
        if answer_match:
            question['answer'] = answer_match.group(1).strip()
        
        # 提取 EXPLANATION
        explanation_match = re.search(r'##EXPLANATION##\s*\n(.*?)(?=##END##|$)', 
                                     block, re.DOTALL | re.IGNORECASE)
        if explanation_match:
            question['explanation'] = explanation_match.group(1).strip()
        
        return question
    
    def _validate_question_data(self, data: Dict[str, Any]) -> bool:
        """
        验证题目数据格式
        
        Args:
            data: 题目数据
            
        Returns:
            是否有效
        """
        
        # 必需字段
        required_fields = ['content', 'type', 'answer', 'difficulty']
        
        for field in required_fields:
            if field not in data or not data[field]:
                print(f"  ⚠️ 缺少必需字段: {field}")
                return False
        
        # 验证题目类型并规范化（支持两种格式）
        valid_types_map = {
            'choice': 'choice',
            'fillBlank': 'fillBlank',
            'fill_blank': 'fillBlank',
            'shortAnswer': 'shortAnswer',
            'short_answer': 'shortAnswer',
            'essay': 'essay',
            'calculation': 'calculation'
        }
        
        question_type = data['type']
        if question_type not in valid_types_map:
            print(f"  ⚠️ 无效的题目类型: {question_type}")
            return False
        
        # 规范化类型名称
        data['type'] = valid_types_map[question_type]
        
        # 验证难度
        if not isinstance(data['difficulty'], (int, float)) or data['difficulty'] < 1 or data['difficulty'] > 5:
            print(f"  ⚠️ 无效的难度值: {data['difficulty']}")
            return False
        
        # 选择题必须有选项
        if data['type'] == 'choice':
            if 'options' not in data or not isinstance(data['options'], list) or len(data['options']) < 2:
                print(f"  ⚠️ 选择题缺少有效的选项")
                return False
        
        # 确保 explanation 字段存在
        if 'explanation' not in data:
            data['explanation'] = ''
        
        return True
    
    async def _save_question(
        self,
        user_id: str,
        source_question: Dict[str, Any],
        variant_data: Dict[str, Any]
    ) -> str:
        """
        保存生成的题目
        
        Args:
            user_id: 用户 ID
            source_question: 源题目
            variant_data: 变式题数据
            
        Returns:
            新题目 ID
        """
        
        # 继承源题目的属性
        question_data = {
            'subject': source_question.get('subject'),
            'moduleIds': source_question.get('moduleIds', []),
            'knowledgePointIds': source_question.get('knowledgePointIds', []),
            'primaryKnowledgePointIds': source_question.get('primaryKnowledgePointIds', []),
            'type': variant_data['type'],
            'difficulty': int(variant_data['difficulty']),
            'content': variant_data['content'],
            'answer': variant_data['answer'],
            'explanation': variant_data.get('explanation', ''),
            'source': 'ai-gen',  # 标记为 AI 生成
            'createdBy': user_id,
            'isPublic': False,  # 默认私有
            'qualityScore': 5.0,  # 默认质量分
            'feedbackCount': 0
        }
        
        # 添加选项（如果是选择题）
        if variant_data['type'] == 'choice' and 'options' in variant_data:
            question_data['options'] = variant_data['options']
        
        # 添加解题提示（如果有）
        if 'solvingHint' in variant_data:
            question_data['solvingHint'] = variant_data['solvingHint']
        
        # 创建题目文档
        new_question = self.databases.create_document(
            database_id=self.database_id,
            collection_id='questions',
            document_id=ID.unique(),
            data=question_data
        )
        
        return new_question['$id']
    
    async def _update_task_progress(
        self,
        task_id: str,
        completed_count: int,
        generated_question_ids: List[str]
    ):
        """
        更新任务进度
        
        Args:
            task_id: 任务 ID
            completed_count: 已完成数量
            generated_question_ids: 已生成的题目 ID 列表
        """
        
        try:
            self.databases.update_document(
                database_id=self.database_id,
                collection_id='question_generation_tasks',
                document_id=task_id,
                data={
                    'completedCount': completed_count,
                    'generatedQuestionIds': generated_question_ids
                }
            )
        except Exception as e:
            print(f"  ⚠️ 更新任务进度失败: {str(e)}")
    
    async def _complete_task(
        self,
        task_id: str,
        generated_question_ids: List[str],
        errors: List[str]
    ):
        """
        标记任务完成
        
        Args:
            task_id: 任务 ID
            generated_question_ids: 生成的题目 ID 列表
            errors: 错误列表
        """
        
        update_data = {
            'status': 'completed',
            'completedAt': datetime.utcnow().isoformat() + 'Z',
            'completedCount': len(generated_question_ids),
            'generatedQuestionIds': generated_question_ids
        }
        
        # 如果有错误，记录下来
        if errors and len(errors) > 0:
            update_data['error'] = '\n'.join(errors[:5])  # 只记录前5个错误
        
        self.databases.update_document(
            database_id=self.database_id,
            collection_id='question_generation_tasks',
            document_id=task_id,
            data=update_data
        )


# ============ 便捷函数 ============

async def process_question_generation_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理题目生成任务的便捷函数
    
    Args:
        task_data: 任务数据
        
    Returns:
        处理结果
    """
    worker = QuestionGeneratorWorker()
    return await worker.process_task(task_data)


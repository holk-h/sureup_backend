"""
题目服务模块
负责题目的创建、查询和管理
"""
import os
from typing import Dict, List, Optional
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_QUESTIONS = 'questions'


def create_or_find_question(
    databases: Databases,
    subject: str,
    module_ids: List[str],
    knowledge_point_ids: List[str],
    content: str,
    question_type: str,
    difficulty: int,
    options: Optional[List[str]] = None,
    answer: Optional[str] = None,
    explanation: Optional[str] = None,
    image_ids: Optional[List[str]] = None,
    created_by: str = None,
    source: str = 'ocr'
) -> Dict:
    """
    创建新题目
    
    每次都创建新的题目记录，不查找相似题目
    
    三级结构：
    - 学科（subject）：如数学、物理
    - 模块列表（module_ids）：如["微积分", "几何"]（可以有多个）
    - 知识点列表（knowledge_point_ids）：如["定积分", "不定积分"]（可以有多个）
    
    注意：
    - 统一使用 Markdown + LaTeX 公式格式（$$...$$）
    - 只存储ID，名称可以通过ID查询得到
    - 一个题目可以关联多个模块和多个知识点
    - image_ids 存储的是 bucket 中的文件 ID
    """
    
    # 创建新题目
    question_data = {
        'subject': subject,
        'moduleIds': module_ids,                    # 模块ID数组
        'knowledgePointIds': knowledge_point_ids,   # 知识点ID数组
        'type': question_type,
        'difficulty': difficulty,
        'content': content,                         # Markdown 格式（含 LaTeX 公式）
        'options': options or [],
        'answer': answer or '',
        'explanation': explanation or '',           # Markdown 格式（含 LaTeX 公式）
        'imageIds': image_ids or [],                # 题目中提取的图表文件ID（存储在bucket中）
        'source': source,
        'createdBy': created_by,
        'isPublic': False,
        'feedbackCount': 0,
        'qualityScore': 5.0
    }
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        document_id=ID.unique(),
        data=question_data
    )
    
    return doc


def search_similar_questions(
    databases: Databases,
    content: str,
    subject: str,
    threshold: float = 0.8,
    limit: int = 5
) -> List[Dict]:
    """
    搜索相似题目
    
    使用全文搜索来查找相似题目
    TODO: 后续可以使用向量搜索来提高准确度
    """
    
    try:
        # 提取关键词进行搜索
        search_keywords = extract_search_keywords(content)
        
        if not search_keywords:
            return []
        
        # 使用全文搜索
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_QUESTIONS,
            queries=[
                Query.equal('subject', subject),
                Query.search('content', search_keywords),
                Query.limit(limit)
            ]
        )
        
        # TODO: 计算相似度并过滤
        # 这里简单返回搜索结果
        # 实际应该计算每个结果与输入的相似度，只返回超过阈值的
        
        return docs.get('documents', [])
        
    except Exception as e:
        # 如果搜索失败，返回空列表
        print(f"搜索相似题目失败: {str(e)}")
        return []


def get_question(databases: Databases, question_id: str) -> Dict:
    """获取题目详情"""
    doc = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_QUESTIONS,
        document_id=question_id
    )
    return doc


def update_question_stats(
    databases: Databases,
    question_id: str,
    feedback_count_delta: int = 0,
    quality_score: Optional[float] = None
) -> Dict:
    """
    更新题目统计信息
    """
    question = get_question(databases, question_id)
    
    update_data = {}
    
    if feedback_count_delta != 0:
        update_data['feedbackCount'] = question.get('feedbackCount', 0) + feedback_count_delta
    
    if quality_score is not None:
        update_data['qualityScore'] = quality_score
    
    if update_data:
        doc = databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_QUESTIONS,
            document_id=question_id,
            data=update_data
        )
        return doc
    
    return question


def extract_search_keywords(content: str, max_length: int = 100) -> str:
    """
    从题目内容中提取搜索关键词
    
    策略：
    1. 移除标点符号
    2. 提取前N个字符
    3. 或提取关键句子
    """
    import re
    
    # 移除多余的空白字符
    content = re.sub(r'\s+', ' ', content.strip())
    
    # 如果内容较短，直接返回
    if len(content) <= max_length:
        return content
    
    # 否则返回前max_length个字符
    return content[:max_length]


def calculate_similarity(text1: str, text2: str) -> float:
    """
    计算两个文本的相似度
    
    TODO: 实现更高级的相似度算法
    - 余弦相似度
    - 编辑距离
    - 语义相似度（使用embeddings）
    """
    # 简单实现：基于字符重合率
    if not text1 or not text2:
        return 0.0
    
    set1 = set(text1)
    set2 = set(text2)
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    if union == 0:
        return 0.0
    
    return intersection / union


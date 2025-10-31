"""
错题记录服务模块
负责错题记录的创建（包含业务逻辑）

注意：简单的查询、更新操作由 Flutter 端直接通过 Appwrite SDK 操作数据库
这里只保留需要复杂业务逻辑的函数
"""
import os
from datetime import datetime
from typing import Dict, List, Optional
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_MISTAKES = 'mistake_records'


def create_mistake_record(
    databases: Databases,
    user_id: str,
    question_id: str,
    module_ids: List[str],
    knowledge_point_ids: List[str],
    subject: str,
    error_reason: str,
    user_answer: Optional[str] = None,
    note: Optional[str] = None,
    original_image_urls: Optional[List[str]] = None
) -> Dict:
    """
    创建错题记录
    
    三级结构：
    - 学科（subject）：如数学、物理
    - 模块列表（module_ids）：如["微积分", "几何"]（可以有多个）
    - 知识点列表（knowledge_point_ids）：如["定积分", "不定积分"]（可以有多个）
    
    注意：
    - 创建后会触发 stats-updater 函数自动更新统计
    - 只存储ID，名称可以通过ID查询得到
    - 一个错题可以关联多个模块和多个知识点
    """
    
    # 检查是否已存在相同的错题记录
    existing = find_existing_mistake(
        databases=databases,
        user_id=user_id,
        question_id=question_id
    )
    
    if existing:
        # 如果已存在，更新该记录而不是创建新的
        return update_existing_mistake(
            databases=databases,
            mistake_id=existing['$id'],
            user_answer=user_answer,
            note=note,
            error_reason=error_reason
        )
    
    # 创建新记录
    mistake_data = {
        'userId': user_id,
        'questionId': question_id,
        'moduleIds': module_ids,                       # 模块ID数组
        'knowledgePointIds': knowledge_point_ids,      # 知识点ID数组
        'subject': subject,
        'errorReason': error_reason,
        'userAnswer': user_answer or '',
        'note': note or '',
        'originalImageUrls': original_image_urls or [],
        'masteryStatus': 'notStarted',
        'reviewCount': 0,
        'correctCount': 0,
        'lastReviewAt': None,
        'masteredAt': None
    }
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKES,
        document_id=ID.unique(),
        data=mistake_data
    )
    
    return doc


def find_existing_mistake(
    databases: Databases,
    user_id: str,
    question_id: str
) -> Optional[Dict]:
    """
    查找用户是否已有该题目的错题记录
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MISTAKES,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('questionId', question_id),
                Query.limit(1)
            ]
        )
        
        documents = docs.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"查找已有错题失败: {str(e)}")
        return None


def update_existing_mistake(
    databases: Databases,
    mistake_id: str,
    user_answer: Optional[str] = None,
    note: Optional[str] = None,
    error_reason: Optional[str] = None
) -> Dict:
    """
    更新已存在的错题记录
    """
    update_data = {}
    
    if user_answer is not None:
        update_data['userAnswer'] = user_answer
    
    if note is not None:
        # 如果有新笔记，追加而不是替换
        existing = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MISTAKES,
            document_id=mistake_id
        )
        old_note = existing.get('note', '')
        if old_note:
            update_data['note'] = f"{old_note}\n---\n{note}"
        else:
            update_data['note'] = note
    
    if error_reason is not None:
        update_data['errorReason'] = error_reason
    
    # 更新复习次数
    update_data['reviewCount'] = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKES,
        document_id=mistake_id
    ).get('reviewCount', 0) + 1
    
    doc = databases.update_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MISTAKES,
        document_id=mistake_id,
        data=update_data
    )
    
    return doc


# 其他 CRUD 操作（get、list、update、delete）由 Flutter 端直接通过 Appwrite SDK 操作数据库
# 这样可以减少函数调用开销，提高性能


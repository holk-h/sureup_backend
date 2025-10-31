"""
知识点服务模块
负责学科模块和用户知识点的创建和管理

新的三级结构：
- 学科 (subject): 如数学、物理
- 模块 (module): 公有的学科模块，存储在 knowledge_points_library
- 知识点 (knowledge_point): 用户私有的知识点，存储在 user_knowledge_points，关联 moduleId
"""
import os
from typing import Dict, Optional
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_USER_KP = 'user_knowledge_points'
COLLECTION_MODULES = 'knowledge_points_library'  # 改为模块库


def ensure_knowledge_point(
    databases: Databases,
    user_id: str,
    subject: str,
    module_id: str,
    knowledge_point_name: str,
    description: Optional[str] = None
) -> Dict:
    """
    确保用户知识点存在
    
    策略：
    1. 先在用户知识点中查找（同一用户、同一模块、同一名称）
    2. 如果不存在，创建新的用户知识点
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        subject: 学科
        module_id: 模块ID（来自 knowledge_points_library）
        knowledge_point_name: 知识点名称
        description: 描述（可选）
    """
    
    # 1. 查找是否已存在
    existing = find_user_knowledge_point(
        databases=databases,
        user_id=user_id,
        module_id=module_id,
        name=knowledge_point_name
    )
    
    if existing:
        return existing
    
    # 2. 创建新的用户知识点
    return create_user_knowledge_point(
        databases=databases,
        user_id=user_id,
        subject=subject,
        module_id=module_id,
        name=knowledge_point_name,
        description=description
    )


def find_user_knowledge_point(
    databases: Databases,
    user_id: str,
    module_id: str,
    name: str
) -> Optional[Dict]:
    """
    在用户知识点中查找知识点（通过用户ID、模块ID和名称）
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.equal('name', name),
                Query.limit(1)
            ]
        )
        
        documents = docs.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"查找用户知识点失败: {str(e)}")
        return None


def find_module(
    databases: Databases,
    subject: str,
    name: str
) -> Optional[Dict]:
    """
    在公有模块库中查找模块
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=[
                Query.equal('subject', subject),
                Query.equal('name', name),
                Query.limit(1)
            ]
        )
        
        documents = docs.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"查找模块失败: {str(e)}")
        return None


def ensure_module(
    databases: Databases,
    subject: str,
    module_name: str,
    description: Optional[str] = None
) -> Dict:
    """
    确保公有模块存在
    
    模块是公有的学科分类，存储在 knowledge_points_library
    如果不存在，则创建新模块
    
    Args:
        databases: 数据库实例
        subject: 学科
        module_name: 模块名称
        description: 描述（可选）
    """
    # 1. 查找是否已存在
    existing = find_module(
        databases=databases,
        subject=subject,
        name=module_name
    )
    
    if existing:
        return existing
    
    # 2. 创建新模块
    module_data = {
        'subject': subject,
        'name': module_name,
        'description': description or '',
        'order': 0,  # 默认排序
        'usageCount': 0,
        'isActive': True
    }
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_MODULES,
        document_id=ID.unique(),
        data=module_data
    )
    
    return doc


def create_user_knowledge_point(
    databases: Databases,
    user_id: str,
    subject: str,
    module_id: str,
    name: str,
    description: Optional[str] = None
) -> Dict:
    """
    创建用户知识点
    
    知识点是用户私有的，关联到公有的模块
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        subject: 学科
        module_id: 模块ID（来自 knowledge_points_library）
        name: 知识点名称
        description: 描述（可选）
    """
    kp_data = {
        'userId': user_id,
        'subject': subject,
        'moduleId': module_id,
        'name': name,
        'description': description or '',
        'mistakeCount': 0,
        'masteredCount': 0,
        'lastMistakeAt': None
    }
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KP,
        document_id=ID.unique(),
        data=kp_data
    )
    
    return doc


def update_knowledge_point_stats(
    databases: Databases,
    kp_id: str,
    mistake_count_delta: int = 0,
    mastered_count_delta: int = 0
) -> Dict:
    """
    更新知识点统计
    
    注意：
    - 这个函数目前未被使用，保留作为工具函数
    - 实际的统计更新由 stats-updater 函数通过数据库事件自动触发
    - stats-updater 是独立的 Appwrite Function，有自己的实现
    """
    kp = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KP,
        document_id=kp_id
    )
    
    update_data = {}
    
    if mistake_count_delta != 0:
        update_data['mistakeCount'] = max(0, kp.get('mistakeCount', 0) + mistake_count_delta)
    
    if mastered_count_delta != 0:
        update_data['masteredCount'] = max(0, kp.get('masteredCount', 0) + mastered_count_delta)
    
    if mistake_count_delta > 0:
        from datetime import datetime
        update_data['lastMistakeAt'] = datetime.utcnow().isoformat() + 'Z'
    
    if update_data:
        doc = databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            document_id=kp_id,
            data=update_data
        )
        return doc
    
    return kp


def get_modules_by_subject(
    databases: Databases,
    subject: str
) -> list:
    """
    获取指定学科的所有模块
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=[
                Query.equal('subject', subject),
                Query.equal('isActive', True),
                Query.order_asc('order'),
                Query.limit(100)
            ]
        )
        
        return docs.get('documents', [])
        
    except Exception as e:
        print(f"获取模块列表失败: {str(e)}")
        return []


def get_user_knowledge_points_by_module(
    databases: Databases,
    user_id: str,
    module_id: str
) -> list:
    """
    获取用户在指定模块下的所有知识点
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.limit(100)
            ]
        )
        
        return docs.get('documents', [])
        
    except Exception as e:
        print(f"获取知识点列表失败: {str(e)}")
        return []


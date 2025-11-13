"""
Appwrite 辅助函数模块
负责数据库查询和 Appwrite 客户端创建
"""
import os
from typing import Dict, List, Optional
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

from workers.mistake_analyzer.helpers.utils import get_user_profile, get_education_level_from_grade, get_subject_chinese_name


# 常量配置
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_MODULES = 'knowledge_points_library'

# 学科中文映射
SUBJECT_NAMES = {
    'math': '数学',
    'physics': '物理',
    'chemistry': '化学',
    'biology': '生物',
    'chinese': '语文',
    'english': '英语',
    'history': '历史',
    'geography': '地理',
    'politics': '政治'
}


def create_appwrite_client() -> Client:
    """创建 Appwrite Client"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return client


def get_existing_modules(
    subject: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> List[Dict]:
    """
    获取用户学段对应的学科模块列表
    
    Args:
        subject: 学科（英文代码如 'math'）
        user_id: 用户ID（用于获取学段信息）
        databases: Databases 实例（可选）
        
    Returns:
        [{'$id': str, 'name': str, 'description': str}, ...]
    """
    if not databases:
        databases = Databases(create_appwrite_client())
    
    try:
        user_profile = get_user_profile(databases, user_id)
        user_grade = user_profile.get('grade') if user_profile else None
        education_level = get_education_level_from_grade(user_grade)
        
        print(f"用户年级: {user_grade}, 学段: {education_level}")
        
        subject_chinese = get_subject_chinese_name(subject)
        
        queries = [
            Query.equal('subject', subject_chinese),
            Query.equal('educationLevel', education_level),
            Query.equal('isActive', True),
            Query.order_asc('order'),
            Query.limit(100)
        ]
        
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=queries
        )
        
        modules = [
            {
                '$id': doc.get('$id', ''),
                'name': doc.get('name', ''),
                'description': doc.get('description', '')
            }
            for doc in result.get('documents', [])
        ]
        
        print(f"找到 {len(modules)} 个{SUBJECT_NAMES.get(subject, subject)}模块（学段: {education_level}，学科中文: {subject_chinese}）")
        return modules
        
    except Exception as e:
        print(f"获取学科模块失败: {str(e)}")
        return []


def get_existing_knowledge_points_by_module(
    module_id: str,
    user_id: str,
    databases: Optional[Databases] = None
) -> List[str]:
    """
    获取用户在指定模块下已有的知识点名称列表
    
    Args:
        module_id: 模块ID
        user_id: 用户ID
        databases: Databases 实例（可选）
        
    Returns:
        知识点名称列表
    """
    if not databases:
        databases = Databases(create_appwrite_client())
    
    try:
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='user_knowledge_points',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.limit(100)
            ]
        )
        
        return [doc.get('name', '') for doc in result.get('documents', []) if doc.get('name')]
        
    except Exception as e:
        print(f"获取用户知识点失败: {str(e)}")
        return []


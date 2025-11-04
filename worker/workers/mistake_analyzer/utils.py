"""
工具函数模块
"""
import os
import json
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage


def parse_request_body(req) -> dict:
    """解析请求体"""
    try:
        if hasattr(req, 'body') and req.body:
            if isinstance(req.body, str):
                return json.loads(req.body)
            return req.body
        return {}
    except json.JSONDecodeError:
        return {}


def get_user_id(req) -> str:
    """从请求中获取用户ID"""
    # 从 JWT token 或请求头中获取用户ID
    # Appwrite 会自动处理身份验证并在请求中提供用户信息
    if hasattr(req, 'headers'):
        # 尝试从多个可能的来源获取用户ID
        user_id = req.headers.get('x-appwrite-user-id')
        if user_id:
            return user_id
    
    # 尝试从环境变量获取（仅用于测试）
    import os
    return os.environ.get('APPWRITE_FUNCTION_USER_ID', '')


def success_response(data=None, message="Success", code=200):
    """构建成功响应"""
    response = {
        'success': True,
        'message': message,
        'code': code
    }
    if data is not None:
        response['data'] = data
    return response


def error_response(message="Error", code=400):
    """构建错误响应"""
    return {
        'success': False,
        'message': message,
        'code': code
    }


def validate_subject(subject: str) -> bool:
    """验证学科是否有效"""
    valid_subjects = ['math', 'physics', 'chemistry', 'biology', 'chinese', 'english', 'history', 'geography', 'politics']
    return subject in valid_subjects


def validate_error_reason(reason: str) -> bool:
    """验证错误原因是否有效"""
    valid_reasons = [
        'conceptError',      # 概念错误
        'carelessness',      # 粗心大意
        'calculationError',  # 计算错误
        'methodError',       # 方法错误
        'incompleteAnswer',  # 答案不完整
        'misunderstanding',  # 理解错误
        'timeConstrain',     # 时间不够
        'other'              # 其他
    ]
    return reason in valid_reasons


def validate_mastery_status(status: str) -> bool:
    """验证掌握状态是否有效"""
    valid_statuses = ['notStarted', 'learning', 'reviewing', 'mastered']
    return status in valid_statuses


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


def get_user_profile(databases: Databases, user_id: str) -> dict:
    """获取用户档案信息"""
    from appwrite.query import Query
    
    DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
    
    try:
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        documents = result.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"获取用户档案失败: {str(e)}")
        return None


def get_education_level_from_grade(grade: int) -> str:
    """
    根据年级确定教育阶段（返回中文，与数据库一致）
    
    Args:
        grade: 年级 (1-12)
        
    Returns:
        educationLevel: '小学' (1-6), '初中' (7-9), '高中' (10-12)
    """
    if grade is None or grade < 1:
        return '初中'  # 默认初中
    
    if 1 <= grade <= 6:
        return '小学'
    elif 7 <= grade <= 9:
        return '初中'
    elif 10 <= grade <= 12:
        return '高中'
    else:
        return '初中'  # 默认初中


def get_subject_chinese_name(subject_code: str) -> str:
    """
    将学科英文代码转换为中文名称（用于数据库查询）
    
    Args:
        subject_code: 英文代码如 'math', 'physics'
        
    Returns:
        中文名称如 '数学', '物理'
    """
    subject_mapping = {
        'math': '数学',
        'physics': '物理',
        'chemistry': '化学',
        'biology': '生物',
        'chinese': '语文',
        'english': '英语',
        'history': '历史',
        'geography': '地理',
        'politics': '政治',
    }
    return subject_mapping.get(subject_code, subject_code)


"""
工具函数模块
"""
import json


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


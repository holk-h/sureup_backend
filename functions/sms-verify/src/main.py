"""
短信验证函数
支持多个短信服务商：火山引擎、阿里云
使用模块化架构，可通过环境变量切换服务商
验证验证码并处理登录/注册
"""
import os
import sys
import json
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.users import Users
from appwrite.id import ID
from appwrite.query import Query

# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from providers.base import SMSProviderFactory
from providers.volc_provider import VolcSMSProvider  # 导入以注册
from providers.aliyun_provider import AliyunSMSProvider  # 导入以注册

# 常量
CODE_EXPIRY_SECONDS = 300  # 验证码有效期：5分钟
SESSION_TOKEN_EXPIRY = 31536000  # Session token有效期：1年


def _parse_request_body(context):
    """解析请求体"""
    try:
        if isinstance(context.req.body, dict):
            return context.req.body
        elif isinstance(context.req.body, str):
            return json.loads(context.req.body) if context.req.body else {}
        return {}
    except Exception as e:
        context.error(f'解析请求参数失败: {str(e)}')
        return None


def _validate_params(phone, code):
    """验证参数有效性"""
    phone = str(phone).strip() if phone else ''
    code = str(code).strip() if code else ''
    
    if not phone or phone == 'None' or not code or code == 'None':
        return None, None
    
    return phone, code


def _normalize_phone(phone):
    """标准化手机号格式
    Returns:
        (phone_with_plus, phone_number): 分别用于Appwrite和短信服务商
    """
    if phone.startswith('+'):
        phone_with_plus = phone
        phone_number = phone.replace('+86', '').replace('+', '')
    else:
        phone_with_plus = f'+86{phone}'
        phone_number = phone
    return phone_with_plus, phone_number


def _init_appwrite_client(context):
    """初始化Appwrite客户端"""
    endpoint = os.environ.get('APPWRITE_ENDPOINT')
    project_id = os.environ.get('APPWRITE_PROJECT_ID')
    api_key = os.environ.get('APPWRITE_API_KEY')
    
    if not all([endpoint, project_id, api_key]):
        context.log('缺少Appwrite配置')
        return None
    
    client = Client()
    client.set_endpoint(endpoint)
    client.set_project(project_id)
    client.set_key(api_key)
    
    return client


def main(context):
    """验证短信验证码并处理登录/注册"""
    
    # 1. 解析和验证请求参数
    payload = _parse_request_body(context)
    if payload is None:
        return context.res.json({
            'success': False,
            'message': '无效的请求参数'
        }, 400)
    
    phone, code = _validate_params(payload.get('phone'), payload.get('code'))
    if not phone or not code:
        return context.res.json({
            'success': False,
            'message': '请提供有效的手机号和验证码'
        }, 400)
    
    context.log(f'收到验证请求，手机号: {phone}, 验证码: {code}')
    
    # 2. 标准化手机号格式
    phone_with_plus, phone_number = _normalize_phone(phone)
    
    # 3. 验证验证码
    sms_provider = os.environ.get('SMS_PROVIDER', 'aliyun').lower()
    context.log(f'使用短信服务商: {sms_provider}')
    
    try:
        if code == '010101':
            context.log('使用测试验证码，直接通过验证')
        elif not _verify_sms_code(sms_provider, phone_number, code, context):
            return context.res.json({
                'success': False,
                'message': '验证码错误或已过期'
            }, 401)
        
        # 4. 初始化Appwrite客户端
        client = _init_appwrite_client(context)
        if not client:
            return context.res.json({
                'success': False,
                'message': 'Appwrite服务配置错误'
            }, 500)
        
        users_service = Users(client)
        databases = Databases(client)
        
        # 5. 查找或创建用户
        user, is_new_user = _find_or_create_user(users_service, phone_with_plus, phone_number, context)
        if not user:
            return context.res.json({
                'success': False,
                'message': '用户处理失败，请重试'
            }, 500)
        
        # 6. 检查用户档案是否存在
        has_profile = _check_user_profile(databases, user['$id'], context)
        
        # 7. 创建Session token并返回结果
        return _create_session_response(users_service, user, is_new_user, has_profile, context)
        
    except Exception as e:
        context.error(f'验证异常: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '验证失败，请重试'
        }, 500)


def _verify_sms_code(provider_name: str, phone: str, code: str, context) -> bool:
    """验证短信验证码"""
    if provider_name == 'aliyun':
        context.log('阿里云验证码，查表验证')
        return _verify_aliyun_code(phone, code, context)
    else:
        context.log('火山引擎验证码，API验证')
        provider = _create_volc_provider(context)
        if not provider:
            return False
        verify_result = provider.verify_code(phone, code)
        return verify_result.get('success', False)


def _find_or_create_user(users_service, phone_with_plus: str, phone_number: str, context):
    """查找或创建用户"""
    try:
        context.log(f'查找用户，手机号: {phone_with_plus}')
        user_list = users_service.list(
            queries=[Query.equal('phone', phone_with_plus)]
        )
        
        if user_list['total'] > 0:
            user = user_list['users'][0]
            context.log(f'用户已存在，用户ID: {user["$id"]}')
            return user, False
        
        # 创建新用户
        user_id = ID.unique()
        context.log(f'创建新用户，ID: {user_id}, 手机号: {phone_with_plus}')
        user = users_service.create(
            user_id=user_id,
            phone=phone_with_plus,
            name=f'用户{phone_number[-4:]}'
        )
        context.log(f'创建新用户成功: {user["$id"]}')
        return user, True
        
    except Exception as e:
        context.error(f'用户处理失败: {str(e)}')
        return None, False


def _check_user_profile(databases, user_id: str, context) -> bool:
    """检查用户档案是否存在"""
    try:
        database_id = os.environ.get('APPWRITE_DATABASE_ID', 'main')
        users_collection_id = os.environ.get('APPWRITE_USERS_COLLECTION_ID', 'profiles')
        
        databases.get_document(
            database_id=database_id,
            collection_id=users_collection_id,
            document_id=user_id
        )
        context.log(f'用户档案已存在: {user_id}')
        return True
    except Exception as e:
        context.log(f'用户档案不存在: {user_id}, 原因: {str(e)}')
        return False


def _create_session_response(users_service, user: dict, is_new_user: bool, has_profile: bool, context):
    """创建Session token并返回响应"""
    base_data = {
        'userId': user['$id'],
        'phone': user.get('phone'),
        'name': user.get('name'),
        'isNewUser': is_new_user,
        'hasProfile': has_profile
    }
    
    try:
        token_response = users_service.create_token(
            user_id=user['$id'],
            length=64,
            expire=SESSION_TOKEN_EXPIRY
        )
        base_data['sessionToken'] = token_response['secret']
        context.log(f'创建 Session Token 成功: {user["$id"]}')
    except Exception as e:
        context.log(f'创建 Session Token 失败: {str(e)}')
    
    return context.res.json({
        'success': True,
        'message': '验证成功',
        'data': base_data
    })


def _verify_aliyun_code(phone: str, code: str, context) -> bool:
    """阿里云验证码查表验证"""
    try:
        client = _init_appwrite_client(context)
        if not client:
            context.log('Appwrite配置不完整，无法验证验证码')
            return False
        
        databases = Databases(client)
        database_id = os.environ.get('APPWRITE_DATABASE_ID', 'main')
        
        # 从数据库查询验证码
        try:
            document = databases.get_document(
                database_id=database_id,
                collection_id='sms_verification_codes',
                document_id=phone
            )
            
            stored_code = document.get('code')
            created_at = document.get('createdAt')
            
            # 检查验证码是否过期
            current_time = datetime.now(timezone.utc)
            context.log(f'验证码时间检查: 手机号={phone}, 创建时间={created_at}, 当前UTC时间={current_time.isoformat()}')
            
            is_expired = _is_code_expired(created_at, context)
            is_valid = stored_code == code
            
            # 无论验证结果如何，都删除验证码（一次性使用）
            if is_expired or is_valid:
                _delete_verification_code(databases, database_id, phone)
            
            if is_expired:
                context.log(f'验证码已过期: {phone}')
                return False
            
            if is_valid:
                context.log(f'验证码验证成功: {phone}')
                return True
            
            context.log(f'验证码不匹配: {phone}')
            return False
                
        except Exception as e:
            context.log(f'查询验证码失败: {phone}, 错误: {str(e)}')
            return False
            
    except Exception as e:
        context.error(f'验证码验证异常: {str(e)}')
        return False


def _delete_verification_code(databases, database_id: str, phone: str):
    """删除验证码记录"""
    try:
        databases.delete_document(
            database_id=database_id,
            collection_id='sms_verification_codes',
            document_id=phone
        )
    except Exception:
        pass


def _is_code_expired(created_at: str, context) -> bool:
    """检查验证码是否过期"""
    try:
        # 解析创建时间（处理带时区的时间）
        if created_at.endswith('Z'):
            created_time = datetime.fromisoformat(created_at[:-1]).replace(tzinfo=timezone.utc)
        elif '+' in created_at or created_at.endswith('+00:00'):
            created_time = datetime.fromisoformat(created_at)
        else:
            created_time = datetime.fromisoformat(created_at).replace(tzinfo=timezone.utc)
        
        # 获取当前UTC时间
        current_time = datetime.now(timezone.utc)
        
        # 计算时间差并检查是否过期
        time_diff_seconds = (current_time - created_time).total_seconds()
        is_expired = time_diff_seconds > CODE_EXPIRY_SECONDS
        
        context.log(f'时间过期检查: 创建时间={created_time.isoformat()}, 当前时间={current_time.isoformat()}, 时间差={time_diff_seconds}秒, 是否过期={is_expired}')
        
        return is_expired
    except Exception as e:
        context.log(f'时间解析失败: {created_at}, 错误: {str(e)}')
        return True  # 解析失败认为已过期


def _create_volc_provider(context):
    """创建火山引擎短信服务商实例"""
    try:
        config = {
            'access_key': os.environ.get('VOLC_ACCESS_KEY'),
            'secret_key': os.environ.get('VOLC_SECRET_KEY'),
            'sms_account': os.environ.get('VOLC_SMS_ACCOUNT'),
            'template_id': os.environ.get('VOLC_SMS_TEMPLATE_ID'),
            'sign_name': os.environ.get('VOLC_SMS_SIGN_NAME'),
        }
        
        if not all(config.values()):
            context.log('火山引擎配置不完整')
            return None
        
        return SMSProviderFactory.create_provider('volc', config)
    except Exception as e:
        context.error(f'创建火山引擎提供商失败: {str(e)}')
        return None
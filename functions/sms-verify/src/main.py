"""
火山引擎短信验证函数
使用 CheckSmsVerifyCode API 验证验证码并处理登录/注册
使用官方SDK: volcengine-python-sdk
"""
import os
import json
from volcengine.ApiInfo import ApiInfo
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo
from volcengine.base.Service import Service
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.users import Users
from appwrite.id import ID
from appwrite.exception import AppwriteException
from appwrite.query import Query

def main(context):
    """验证短信验证码并处理登录/注册"""
    
    # 解析请求参数
    try:
        # context.req.body 可能已经是dict，也可能是string
        if isinstance(context.req.body, dict):
            payload = context.req.body
        elif isinstance(context.req.body, str):
            payload = json.loads(context.req.body) if context.req.body else {}
        else:
            payload = {}
    except Exception as e:
        context.error(f'解析请求参数失败: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '无效的请求参数'
        }, 400)
    
    phone = payload.get('phone', '')
    code = payload.get('code', '')
    
    context.log(f'收到验证请求，手机号: {phone}, 验证码: {code}')
    
    # 验证参数
    if not phone or not code:
        return context.res.json({
            'success': False,
            'message': '请提供手机号和验证码'
        }, 400)
    
    # 确保phone是字符串类型
    phone = str(phone) if phone else ''
    code = str(code) if code else ''
    
    # 再次验证参数（防止None转换为'None'字符串）
    if not phone or phone == 'None' or not code or code == 'None':
        return context.res.json({
            'success': False,
            'message': '请提供有效的手机号和验证码'
        }, 400)
    
    # 标准化手机号格式
    # phone_with_plus: 用于Appwrite（必须带+）
    # phone_number: 用于火山引擎（不带+）
    if phone.startswith('+'):
        phone_with_plus = phone
        phone_number = phone.replace('+86', '').replace('+', '')
    else:
        phone_with_plus = f'+86{phone}'
        phone_number = phone
    
    # 火山引擎配置
    access_key = os.environ.get('VOLC_ACCESS_KEY')
    secret_key = os.environ.get('VOLC_SECRET_KEY')
    sms_account = os.environ.get('VOLC_SMS_ACCOUNT')
    
    if not all([access_key, secret_key, sms_account]):
        context.log('缺少火山引擎配置')
        return context.res.json({
            'success': False,
            'message': '服务配置错误'
        }, 500)
    
    try:
        # 1. 调用火山引擎API验证验证码
        verify_result = _verify_code_with_volc(
            phone_number, 
            code, 
            sms_account,
            access_key, 
            secret_key,
            context
        )
        
        # 验证结果：0-成功，1-错误，2-过期
        if verify_result != '0':
            error_msg = '验证码错误' if verify_result == '1' else '验证码已过期'
            return context.res.json({
                'success': False,
                'message': error_msg
            }, 401)
        
        # 2. 初始化Appwrite客户端
        appwrite_endpoint = os.environ.get('APPWRITE_ENDPOINT')
        appwrite_project_id = os.environ.get('APPWRITE_PROJECT_ID')
        appwrite_api_key = os.environ.get('APPWRITE_API_KEY')
        
        if not all([appwrite_endpoint, appwrite_project_id, appwrite_api_key]):
            context.log('缺少Appwrite配置')
            return context.res.json({
                'success': False,
                'message': 'Appwrite服务配置错误'
            }, 500)
        
        client = Client()
        client.set_endpoint(appwrite_endpoint)
        client.set_project(appwrite_project_id)
        client.set_key(appwrite_api_key)
        
        users_service = Users(client)
        databases = Databases(client)
        
        # 3. 查找或创建用户
        user = None
        is_new_user = False
        
        # 第一步：尝试通过手机号查找用户
        context.log(f'查找用户，手机号: {phone_with_plus}')
        try:
            # 使用正确的Query语法查询用户
            user_list = users_service.list(
                queries=[Query.equal('phone', phone_with_plus)]
            )
            context.log(f'查找到 {user_list["total"]} 个用户')
            
            if user_list['total'] > 0:
                user = user_list['users'][0]
                is_new_user = False
                context.log(f'用户已存在，用户ID: {user["$id"]}')
            else:
                context.log('用户不存在，准备创建新用户')
        except Exception as find_error:
            context.log(f'查找用户异常: {str(find_error)}，准备创建新用户')
        
        # 第二步：如果用户不存在，创建新用户
        if user is None:
            try:
                user_id = ID.unique()
                context.log(f'创建新用户，ID: {user_id}, 手机号: {phone_with_plus}')
                user = users_service.create(
                    user_id=user_id,
                    phone=phone_with_plus,
                    name=f'用户{phone_number[-4:]}'
                )
                is_new_user = True
                context.log(f'创建新用户成功: {user["$id"]}')
            except AppwriteException as create_error:
                error_message = str(create_error)
                context.log(f'创建用户失败: {error_message}')
                
                # 如果错误是"用户已存在"，再次尝试查找用户
                if 'already exists' in error_message:
                    context.log('用户已存在，再次尝试查找...')
                    try:
                        user_list = users_service.list(
                            queries=[Query.equal('phone', phone_with_plus)]
                        )
                        if user_list['total'] > 0:
                            user = user_list['users'][0]
                            is_new_user = False
                            context.log(f'找到已存在用户: {user["$id"]}')
                        else:
                            context.error('用户应该存在但查找失败')
                            return context.res.json({
                                'success': False,
                                'message': '用户状态异常，请重试'
                            }, 500)
                    except Exception as retry_error:
                        context.error(f'再次查找用户失败: {str(retry_error)}')
                        return context.res.json({
                            'success': False,
                            'message': '登录失败，请重试'
                        }, 500)
                else:
                    # 其他创建错误
                    context.error(f'创建用户失败: {error_message}')
                    return context.res.json({
                        'success': False,
                        'message': '创建用户失败'
                    }, 500)
        
        # 4. 为用户创建JWT token（用于前端会话）
        # 注意：这里需要使用Server SDK创建自定义token
        # 或者返回用户ID让前端通过其他方式建立会话
        
        # 确保用户对象存在
        if not user:
            context.error('用户对象为空')
            return context.res.json({
                'success': False,
                'message': '用户创建或查找失败'
            }, 500)
        
        # 5. 检查用户档案是否存在（不自动创建，由前端创建）
        has_profile = False
        database_id = os.environ.get('APPWRITE_DATABASE_ID', 'main')
        users_collection_id = os.environ.get('APPWRITE_USERS_COLLECTION_ID', 'profiles')  # 默认为profiles
        
        try:
            # 尝试获取用户档案
            profile = databases.get_document(
                database_id=database_id,
                collection_id=users_collection_id,
                document_id=user['$id']
            )
            has_profile = True
            context.log(f'用户档案已存在: {user["$id"]}')
        except Exception as e:
            # 档案不存在，由前端创建
            context.log(f'用户档案不存在: {user["$id"]}, 原因: {str(e)}')
            has_profile = False
        
        # 6. 创建用户 Session token（用于前端长期会话）
        try:
            # 创建Session token - 有效期更长（默认1年）
            # 使用 create_token 而不是 create_jwt，这样前端可以用token创建session
            token_response = users_service.create_token(
                user_id=user['$id'],
                length=64,  # token长度
                expire=31536000  # 1年有效期（秒）
            )
            session_token = token_response['secret']
            context.log(f'创建 Session Token 成功: {user["$id"]}')
            
            # 返回结果（包含 Session token）
            return context.res.json({
                'success': True,
                'message': '验证成功',
                'data': {
                    'userId': user['$id'],
                    'phone': user.get('phone'),
                    'name': user.get('name'),
                    'isNewUser': is_new_user,
                    'hasProfile': has_profile,
                    'sessionToken': session_token  # Session token（1年有效期）
                }
            })
        except Exception as token_error:
            context.log(f'创建 Session Token 失败: {str(token_error)}')
            # 即使创建token失败，也返回基本信息
            return context.res.json({
                'success': True,
                'message': '验证成功',
                'data': {
                    'userId': user['$id'],
                    'phone': user.get('phone'),
                    'name': user.get('name'),
                    'isNewUser': is_new_user,
                    'hasProfile': has_profile
                }
            })
        
    except Exception as e:
        context.error(f'验证异常: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '验证失败，请重试'
        }, 500)


def _verify_code_with_volc(phone, code, sms_account, access_key, secret_key, context):
    """
    调用火山引擎API验证验证码
    返回验证结果：'0'-成功，'1'-错误，'2'-过期
    """
    try:
        # 初始化火山引擎SMS服务
        service = _get_sms_service(access_key, secret_key)
        
        # 构造验证请求
        body = {
            'SmsAccount': sms_account,
            'PhoneNumber': phone,
            'Scene': '登录注册',  # 必须与发送时的Scene一致
            'Code': code
        }
        
        # 调用校验验证码API
        response_raw = service.json('CheckSmsVerifyCode', {}, json.dumps(body))
        
        # 解析响应（可能是字符串）
        if isinstance(response_raw, str):
            response = json.loads(response_raw)
        elif isinstance(response_raw, bytes):
            response = json.loads(response_raw.decode('utf-8'))
        else:
            response = response_raw
        
        context.log(f'验证API响应: {json.dumps(response, ensure_ascii=False)}')
        
        # 检查响应
        if 'ResponseMetadata' in response:
            metadata = response['ResponseMetadata']
            
            # 检查是否有错误
            if 'Error' in metadata:
                error = metadata['Error']
                error_code = error.get('Code', '')
                error_msg = error.get('Message', '验证失败')
                
                context.log(f'验证码验证失败: {error_code} - {error_msg}')
                return '1'  # 返回错误状态
        
        # 获取验证结果
        # Result: "0"-成功, "1"-错误, "2"-过期
        result = response.get('Result', '1')
        
        context.log(f'验证码验证结果: {result}')
        return result
        
    except Exception as e:
        context.error(f'验证码验证异常: {str(e)}')
        return '1'  # 异常时返回错误状态


def _get_sms_service(access_key, secret_key):
    """
    初始化火山引擎SMS服务
    使用官方SDK
    """
    # API信息
    api_info = {
        'CheckSmsVerifyCode': ApiInfo('POST', '/', {'Action': 'CheckSmsVerifyCode', 'Version': '2020-01-01'}, {}, {}),
    }
    
    # 服务信息
    service_info = ServiceInfo(
        'sms.volcengineapi.com',
        {},
        Credentials(access_key, secret_key, 'volcSMS', 'cn-north-1'),
        10,
        10,
        'https'
    )
    
    # 创建服务实例
    service = Service(service_info, api_info)
    return service


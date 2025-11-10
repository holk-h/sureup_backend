"""
苹果登录验证函数
验证 Apple Sign In 的 identityToken，处理登录/注册
"""
import os
import json
import jwt
import requests
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.users import Users
from appwrite.id import ID
from appwrite.query import Query

# 常量
SESSION_TOKEN_EXPIRY = 31536000  # Session token有效期：1年
APPLE_PUBLIC_KEYS_URL = 'https://appleid.apple.com/auth/keys'


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


def _validate_params(identity_token, user_identifier):
    """验证参数有效性"""
    identity_token = str(identity_token).strip() if identity_token else ''
    user_identifier = str(user_identifier).strip() if user_identifier else ''
    
    if not identity_token or identity_token == 'None':
        return None, None
    if not user_identifier or user_identifier == 'None':
        return None, None
    
    return identity_token, user_identifier


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


def _get_apple_public_keys(context):
    """获取苹果公钥"""
    try:
        response = requests.get(APPLE_PUBLIC_KEYS_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        context.error(f'获取苹果公钥失败: {str(e)}')
        return None


def _verify_identity_token(identity_token, context):
    """验证 Apple Identity Token
    
    Returns:
        dict: 包含用户信息的 payload，如果验证失败则返回 None
    """
    try:
        # 获取苹果公钥
        apple_keys = _get_apple_public_keys(context)
        if not apple_keys:
            return None
        
        # 解码 token header 以获取 kid
        try:
            unverified_header = jwt.get_unverified_header(identity_token)
        except jwt.DecodeError as e:
            context.log(f'无法解码 token header: {str(e)}')
            return None
        
        kid = unverified_header.get('kid')
        if not kid:
            context.log('Token header 中缺少 kid 字段')
            return None
        
        # 查找对应的公钥
        public_key = None
        for key in apple_keys.get('keys', []):
            if key.get('kid') == kid:
                try:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                except Exception as e:
                    context.log(f'创建公钥失败: {str(e)}')
                    return None
                break
        
        if not public_key:
            context.log('未找到匹配的苹果公钥')
            return None
        
        # 验证 token
        client_id = os.environ.get('APPLE_CLIENT_ID')
        if not client_id:
            context.log('缺少 APPLE_CLIENT_ID 配置')
            return None
        
        context.log(f'期望的 APPLE_CLIENT_ID: {client_id}')
        
        # 先不验证 audience，解码 token 看看里面的内容
        try:
            unverified_payload = jwt.decode(
                identity_token,
                public_key,
                algorithms=['RS256'],
                options={'verify_signature': True, 'verify_exp': True, 'verify_aud': False}
            )
            context.log(f'Token 中的 audience (aud): {unverified_payload.get("aud")}')
            context.log(f'Token 中的 issuer (iss): {unverified_payload.get("iss")}')
            context.log(f'Token 中的 sub: {unverified_payload.get("sub")}')
        except Exception as e:
            context.log(f'解码 token 失败: {str(e)}')
        
        # 正式验证 token（包括 audience）
        payload = jwt.decode(
            identity_token,
            public_key,
            algorithms=['RS256'],
            audience=client_id,
            issuer='https://appleid.apple.com',  # 验证 issuer
            options={'verify_exp': True}
        )
        
        # 验证必需字段
        if not payload.get('sub'):
            context.log('Token 中缺少 sub 字段')
            return None
        
        context.log(f'Apple Identity Token 验证成功，用户 sub: {payload.get("sub")}')
        return payload
        
    except jwt.ExpiredSignatureError:
        context.log('Identity Token 已过期')
        return None
    except jwt.InvalidTokenError as e:
        context.log(f'Identity Token 无效: {str(e)}')
        return None
    except Exception as e:
        context.error(f'验证 Identity Token 异常: {str(e)}')
        return None


def _find_or_create_user(users_service, apple_user_id, email, given_name, family_name, context):
    """查找或创建用户"""
    try:
        # 先尝试通过 labels 查找用户（我们会存储 apple_user_id）
        context.log(f'查找用户，Apple User ID: {apple_user_id}')
        
        # 搜索带有 apple_id 标签的用户
        try:
            user_list = users_service.list(
                queries=[Query.equal('labels', f'apple_id:{apple_user_id}')]
            )
            
            if user_list['total'] > 0:
                user = user_list['users'][0]
                context.log(f'用户已存在，用户ID: {user["$id"]}')
                return user, False
        except Exception as e:
            context.log(f'通过 Apple ID 查找用户失败: {str(e)}')
        
        # 如果提供了 email，尝试通过 email 查找
        if email:
            try:
                user_list = users_service.list(
                    queries=[Query.equal('email', email)]
                )
                
                if user_list['total'] > 0:
                    user = user_list['users'][0]
                    context.log(f'通过 email 找到已存在用户: {user["$id"]}')
                    
                    # 更新用户标签以包含 apple_id
                    try:
                        existing_labels = user.get('labels', [])
                        if f'apple_id:{apple_user_id}' not in existing_labels:
                            existing_labels.append(f'apple_id:{apple_user_id}')
                            users_service.update_labels(user['$id'], existing_labels)
                            context.log('已更新用户的 Apple ID 标签')
                    except Exception as e:
                        context.log(f'更新用户标签失败: {str(e)}')
                    
                    return user, False
            except Exception as e:
                context.log(f'通过 email 查找用户失败: {str(e)}')
        
        # 创建新用户
        user_id = ID.unique()
        
        # 构建用户名
        if given_name or family_name:
            name = f'{family_name or ""}{given_name or ""}'.strip()
            # 确保不为空
            if not name:
                name = f'Apple用户{user_id[-4:]}'
        else:
            name = f'Apple用户{user_id[-4:]}'
        
        context.log(f'创建新用户，ID: {user_id}, Email: {email}, Name: {name}')
        
        # 根据是否有 email 决定创建方式
        create_kwargs = {
            'user_id': user_id,
            'name': name,
        }
        
        # 只有当 email 存在且不为空时才添加
        if email and email.strip():
            create_kwargs['email'] = email
        
        user = users_service.create(**create_kwargs)
        
        # 添加 apple_id 标签
        try:
            users_service.update_labels(user_id, [f'apple_id:{apple_user_id}'])
            context.log('已添加 Apple ID 标签')
        except Exception as e:
            context.log(f'添加 Apple ID 标签失败: {str(e)}')
        
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
        'email': user.get('email'),
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
        
        return context.res.json({
            'success': True,
            'message': '验证成功',
            'data': base_data
        })
    except Exception as e:
        context.error(f'创建 Session Token 失败: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '创建会话失败，请重试'
        }, 500)


def main(context):
    """验证苹果登录并处理登录/注册"""
    
    # 1. 解析和验证请求参数
    payload = _parse_request_body(context)
    if payload is None:
        return context.res.json({
            'success': False,
            'message': '无效的请求参数'
        }, 400)
    
    identity_token = payload.get('identityToken')
    user_identifier = payload.get('userIdentifier')
    email = payload.get('email')  # 可选，首次登录时苹果会提供
    given_name = payload.get('givenName')  # 可选
    family_name = payload.get('familyName')  # 可选
    
    identity_token, user_identifier = _validate_params(identity_token, user_identifier)
    if not identity_token or not user_identifier:
        return context.res.json({
            'success': False,
            'message': '请提供有效的身份令牌'
        }, 400)
    
    context.log(f'收到苹果登录请求，User Identifier: {user_identifier}')
    
    try:
        # 2. 验证 Identity Token
        token_payload = _verify_identity_token(identity_token, context)
        if not token_payload:
            return context.res.json({
                'success': False,
                'message': '身份验证失败'
            }, 401)
        
        # 从 token 中提取信息
        apple_user_id = token_payload.get('sub')  # 苹果用户唯一标识
        token_email = token_payload.get('email')  # Token 中的 email
        
        # 优先使用客户端传来的 email（首次登录时提供），否则使用 token 中的
        final_email = email if email else token_email
        
        context.log(f'Token 验证成功，Apple User ID: {apple_user_id}, Email: {final_email}')
        
        # 3. 初始化Appwrite客户端
        client = _init_appwrite_client(context)
        if not client:
            return context.res.json({
                'success': False,
                'message': 'Appwrite服务配置错误'
            }, 500)
        
        users_service = Users(client)
        databases = Databases(client)
        
        # 4. 查找或创建用户
        user, is_new_user = _find_or_create_user(
            users_service, 
            apple_user_id, 
            final_email,
            given_name,
            family_name,
            context
        )
        if not user:
            return context.res.json({
                'success': False,
                'message': '用户处理失败，请重试'
            }, 500)
        
        # 5. 检查用户档案是否存在
        has_profile = _check_user_profile(databases, user['$id'], context)
        
        # 6. 创建Session token并返回结果
        return _create_session_response(users_service, user, is_new_user, has_profile, context)
        
    except Exception as e:
        context.error(f'验证异常: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '验证失败，请重试'
        }, 500)


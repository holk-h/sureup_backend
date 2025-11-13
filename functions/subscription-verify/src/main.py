"""
订阅验证 Function

功能：
1. 验证 iOS App Store 收据
2. 验证 Android Google Play 收据
3. 创建/更新订阅记录
4. 更新用户档案订阅状态

环境变量：
- APPWRITE_ENDPOINT: Appwrite API 端点
- APPWRITE_PROJECT_ID: 项目 ID
- APPWRITE_API_KEY: API Key
- APPWRITE_DATABASE_ID: 数据库 ID
- APPLE_SHARED_SECRET: Apple 共享密钥（用于验证收据）
- GOOGLE_SERVICE_ACCOUNT_JSON: Google Play 服务账号 JSON（用于验证 Android 收据）
"""

import os
import json
import base64
import httpx
import jwt
from datetime import datetime, timezone, timedelta
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://api.delvetech.cn/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def decode_jws_payload(jws_token: str) -> dict:
    """
    解码 Apple JWS (JSON Web Signature) payload
    
    注意：此函数仅解码 payload，不验证签名！
    生产环境应该验证签名或使用 App Store Server API。
    
    Args:
        jws_token: JWS 格式的 token
        
    Returns:
        解码后的 payload 字典
    """
    try:
        # JWS 格式：header.payload.signature
        # 使用 jwt.decode 的 verify_signature=False 来跳过签名验证（仅用于测试！）
        decoded = jwt.decode(jws_token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        raise ValueError(f"无法解码 JWS: {str(e)}")


def verify_apple_jws_receipt(jws_token: str) -> dict:
    """
    验证 Apple StoreKit 2 JWS 格式收据（简化版）
    
    StoreKit 2 返回的是 JWS (JSON Web Signature) 格式，而非旧的 base64 收据。
    
    完整实现需要：
    1. 下载 Apple 的根证书和中间证书
    2. 验证 JWS 签名链
    3. 或使用 App Store Server API 验证交易
    
    当前实现：解析 JWS payload（不验证签名）用于测试
    
    Args:
        jws_token: JWS 格式的交易数据
        
    Returns:
        验证结果字典
    """
    try:
        payload = decode_jws_payload(jws_token)
        
        # JWS payload 包含交易信息
        # 参考：https://developer.apple.com/documentation/appstoreserverapi/jwstransaction
        
        transaction_id = payload.get('transactionId')
        original_transaction_id = payload.get('originalTransactionId')
        product_id = payload.get('productId')
        purchase_date_ms = payload.get('purchaseDate')  # 毫秒时间戳
        expires_date_ms = payload.get('expiresDate')  # 毫秒时间戳（订阅类型）
        
        if not all([transaction_id, product_id, purchase_date_ms]):
            return {'success': False, 'error': 'JWS 缺少必要字段'}
        
        # 如果没有过期时间（非订阅类型），设置为 30 天后
        if not expires_date_ms:
            expires_date_ms = purchase_date_ms + (30 * 24 * 60 * 60 * 1000)
        
        return {
            'success': True,
            'platform': 'ios',
            'transaction_id': transaction_id,
            'original_transaction_id': original_transaction_id or transaction_id,
            'product_id': product_id,
            'purchase_date_ms': purchase_date_ms,
            'expires_date_ms': expires_date_ms,
            'auto_renew_status': True,  # JWS 中的自动续订状态可以从其他字段获取
            'raw_payload': payload
        }
        
    except Exception as e:
        return {'success': False, 'error': f'JWS 验证失败: {str(e)}'}


def verify_apple_receipt(receipt_data: str, shared_secret: str, sandbox: bool = False) -> dict:
    """
    验证 Apple App Store 收据
    
    Args:
        receipt_data: Base64 编码的收据数据
        shared_secret: App 专用共享密钥
        sandbox: 是否使用沙盒环境
        
    Returns:
        验证结果字典
    """
    # 选择验证 URL
    if sandbox:
        url = "https://sandbox.itunes.apple.com/verifyReceipt"
    else:
        url = "https://buy.itunes.apple.com/verifyReceipt"
    
    payload = {
        "receipt-data": receipt_data,
        "password": shared_secret,
        "exclude-old-transactions": True
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
        
        status = result.get('status')
        
        # Status 0 表示成功
        if status == 0:
            # 获取最新的收据信息
            latest_receipt_info = result.get('latest_receipt_info', [])
            if latest_receipt_info:
                latest = latest_receipt_info[-1]  # 最新的订阅信息
                
                return {
                    'success': True,
                    'platform': 'ios',
                    'transaction_id': latest.get('transaction_id'),
                    'original_transaction_id': latest.get('original_transaction_id'),
                    'product_id': latest.get('product_id'),
                    'purchase_date_ms': int(latest.get('purchase_date_ms', 0)),
                    'expires_date_ms': int(latest.get('expires_date_ms', 0)),
                    'auto_renew_status': result.get('auto_renew_status') == '1',
                    'raw_response': result
                }
            else:
                return {'success': False, 'error': '收据中没有订阅信息'}
        
        # Status 21007 表示收据来自沙盒，但发送到了生产环境，需要重试
        elif status == 21007 and not sandbox:
            return verify_apple_receipt(receipt_data, shared_secret, sandbox=True)
        
        else:
            error_messages = {
                21000: "App Store 无法读取你提供的 JSON 对象",
                21002: "收据数据格式错误",
                21003: "收据无法被验证",
                21004: "你提供的共享密钥与账户的共享密钥不一致",
                21005: "收据服务器当前不可用",
                21006: "收据有效，但订阅已过期",
                21008: "收据来自生产环境，但发送到了沙盒环境",
                21010: "此收据无法被验证",
            }
            error_msg = error_messages.get(status, f"验证失败，状态码: {status}")
            return {'success': False, 'error': error_msg, 'status': status}
    
    except Exception as e:
        return {'success': False, 'error': f"Apple 收据验证异常: {str(e)}"}


def verify_google_receipt(product_id: str, purchase_token: str, package_name: str) -> dict:
    """
    验证 Google Play 收据
    
    简化版实现，仅返回成功状态
    完整实现需要 Google Play Developer API 和 OAuth 认证
    
    Args:
        product_id: 产品 ID
        purchase_token: 购买令牌
        package_name: 应用包名
        
    Returns:
        验证结果字典
    """
    # TODO: 实现完整的 Google Play 验证
    # 需要：
    # 1. 使用服务账号 JSON 获取访问令牌
    # 2. 调用 Google Play Developer API
    # 3. 解析订阅状态和过期时间
    
    # 简化版：暂时直接返回成功（生产环境必须实现完整验证！）
    print(f"警告：Google Play 验证尚未完整实现")
    print(f"产品 ID: {product_id}, Token: {purchase_token[:20]}...")
    
    # 临时返回 30 天订阅
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    expires_ms = now_ms + (30 * 24 * 60 * 60 * 1000)  # 30 天后过期
    
    return {
        'success': True,
        'platform': 'android',
        'transaction_id': purchase_token,
        'original_transaction_id': purchase_token,
        'product_id': product_id,
        'purchase_date_ms': now_ms,
        'expires_date_ms': expires_ms,
        'auto_renew_status': True,
        'warning': '使用临时验证，生产环境请实现完整的 Google Play API 验证'
    }


def create_or_update_subscription(databases: Databases, user_id: str, verification_result: dict) -> dict:
    """
    创建或更新订阅记录
    """
    transaction_id = verification_result['transaction_id']
    
    # 检查是否已存在此交易 ID（防重放）
    existing = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id='subscriptions',
        queries=[
            Query.equal('transactionId', transaction_id),
            Query.limit(1)
        ]
    )
    
    # 转换时间戳为 ISO 格式
    purchase_date = datetime.fromtimestamp(
        verification_result['purchase_date_ms'] / 1000, 
        tz=timezone.utc
    ).isoformat()
    
    expiry_date = datetime.fromtimestamp(
        verification_result['expires_date_ms'] / 1000,
        tz=timezone.utc
    ).isoformat()
    
    subscription_data = {
        'userId': user_id,
        'platform': verification_result['platform'],
        'productId': verification_result['product_id'],
        'status': 'active',
        'transactionId': transaction_id,
        'originalTransactionId': verification_result.get('original_transaction_id'),
        'purchaseDate': purchase_date,
        'expiryDate': expiry_date,
        'autoRenew': verification_result.get('auto_renew_status', True),
        'receiptData': json.dumps(verification_result.get('raw_response', {}))
    }
    
    if existing['total'] > 0:
        # 更新现有订阅
        subscription = databases.update_document(
            database_id=DATABASE_ID,
            collection_id='subscriptions',
            document_id=existing['documents'][0]['$id'],
            data=subscription_data
        )
    else:
        # 创建新订阅
        subscription = databases.create_document(
            database_id=DATABASE_ID,
            collection_id='subscriptions',
            document_id=ID.unique(),
            data=subscription_data
        )
    
    return subscription


def update_user_profile_subscription(databases: Databases, user_id: str, expiry_date: str):
    """
    更新用户档案的订阅状态（激活）
    """
    # 获取用户档案
    profiles = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id='profiles',
        queries=[
            Query.equal('userId', user_id),
            Query.limit(1)
        ]
    )
    
    if profiles['total'] > 0:
        profile = profiles['documents'][0]
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id='profiles',
            document_id=profile['$id'],
            data={
                'subscriptionStatus': 'active',
                'subscriptionExpiryDate': expiry_date
            }
        )
        return True
    return False


def update_user_profile_expired(databases: Databases, user_id: str, expiry_date: str):
    """
    更新用户档案的订阅状态（已过期）
    """
    # 获取用户档案
    profiles = databases.list_documents(
        database_id=DATABASE_ID,
        collection_id='profiles',
        queries=[
            Query.equal('userId', user_id),
            Query.limit(1)
        ]
    )
    
    if profiles['total'] > 0:
        profile = profiles['documents'][0]
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id='profiles',
            document_id=profile['$id'],
            data={
                'subscriptionStatus': 'expired',
                'subscriptionExpiryDate': expiry_date
            }
        )
        return True
    return False


def check_existing_valid_subscription(databases: Databases, user_id: str, transaction_id: str) -> dict | None:
    """
    检查是否已存在有效的订阅记录（防止重复验证）
    
    Args:
        databases: 数据库服务
        user_id: 用户 ID
        transaction_id: 交易 ID（用于快速查找）
        
    Returns:
        如果存在有效订阅，返回订阅记录；否则返回 None
    """
    try:
        # 先尝试通过 transactionId 查找（最快）
        if transaction_id:
            existing = databases.list_documents(
                database_id=DATABASE_ID,
                collection_id='subscriptions',
                queries=[
                    Query.equal('transactionId', transaction_id),
                    Query.equal('userId', user_id),
                    Query.limit(1)
                ]
            )
            
            if existing['total'] > 0:
                subscription = existing['documents'][0]
                expiry_date_str = subscription['expiryDate']
                expiry_date = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
                
                # 检查是否仍然有效（未过期）
                if expiry_date > datetime.now(timezone.utc):
                    return subscription
        
        # 如果没有找到或已过期，返回 None
        return None
    except Exception as e:
        print(f"⚠️ 检查现有订阅时出错: {e}")
        return None


def main(context):
    """
    主函数：处理订阅验证请求
    
    请求格式：
    {
        "userId": "用户 ID",
        "platform": "ios" | "android",
        "receiptData": "收据数据"  (iOS: base64 编码的收据)
        "productId": "产品 ID"     (Android)
        "purchaseToken": "购买令牌" (Android)
        "packageName": "应用包名"   (Android)
        "transactionId": "交易 ID"  (可选，用于快速缓存检查)
    }
    """
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        if isinstance(req.body, dict):
            body = req.body
        elif isinstance(req.body, str):
            body = json.loads(req.body) if req.body else {}
        else:
            body = {}
        
        user_id = body.get('userId')
        platform = body.get('platform')
        transaction_id = body.get('transactionId')  # 用于缓存检查
        
        if not user_id:
            return res.json({'success': False, 'error': '缺少 userId'})
        
        if not platform or platform not in ['ios', 'android']:
            return res.json({'success': False, 'error': 'platform 必须是 ios 或 android'})
        
        context.log(f"[订阅验证] 用户: {user_id}, 平台: {platform}, 交易ID: {transaction_id}")
        
        # 初始化数据库
        databases = get_databases()
        
        # 🚀 优化：首先检查是否已存在有效订阅（缓存检查）
        if transaction_id:
            existing_subscription = check_existing_valid_subscription(databases, user_id, transaction_id)
            if existing_subscription:
                context.log(f"[订阅验证] ✅ 找到缓存的有效订阅，跳过 Apple 验证")
                return res.json({
                    'success': True,
                    'subscription': {
                        'id': existing_subscription['$id'],
                        'productId': existing_subscription['productId'],
                        'expiryDate': existing_subscription['expiryDate'],
                        'autoRenew': existing_subscription.get('autoRenew', True),
                        'isExpired': False
                    },
                    'message': '订阅有效（来自缓存）',
                    'cached': True,
                    'isExpired': False
                })
            else:
                context.log(f"[订阅验证] 未找到有效缓存，执行完整验证")
        
        # 根据平台验证收据
        if platform == 'ios':
            receipt_data = body.get('receiptData')
            if not receipt_data:
                return res.json({'success': False, 'error': '缺少 receiptData'})
            
            # 检测收据格式：JWS (StoreKit 2) 还是 base64 (StoreKit 1)
            # JWS 格式包含两个点 (.)，例如：header.payload.signature
            is_jws = receipt_data.count('.') == 2
            
            if is_jws:
                context.log("[订阅验证] 检测到 JWS 格式收据 (StoreKit 2)")
                verification_result = verify_apple_jws_receipt(receipt_data)
            else:
                context.log("[订阅验证] 检测到传统 base64 格式收据 (StoreKit 1)")
                shared_secret = os.environ.get('APPLE_SHARED_SECRET')
                if not shared_secret:
                    return res.json({'success': False, 'error': '服务器配置错误：缺少 APPLE_SHARED_SECRET'})
                
                verification_result = verify_apple_receipt(receipt_data, shared_secret)
            
        else:  # android
            product_id = body.get('productId')
            purchase_token = body.get('purchaseToken')
            package_name = body.get('packageName')
            
            if not all([product_id, purchase_token, package_name]):
                return res.json({'success': False, 'error': 'Android 验证需要 productId, purchaseToken, packageName'})
            
            verification_result = verify_google_receipt(product_id, purchase_token, package_name)
        
        # 检查验证结果
        if not verification_result.get('success'):
            context.error(f"验证失败: {verification_result.get('error')}")
            return res.json({
                'success': False,
                'error': verification_result.get('error'),
                'details': verification_result
            })
        
        context.log(f"[订阅验证] 验证成功，交易 ID: {verification_result['transaction_id']}")
        
        # 🚀 检查订阅是否已过期
        expires_date_ms = verification_result['expires_date_ms']
        expiry_datetime = datetime.fromtimestamp(expires_date_ms / 1000, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        is_expired = expiry_datetime <= now_utc
        
        if is_expired:
            context.log(f"⚠️ [订阅验证] 订阅已过期: {expiry_datetime} (当前时间: {now_utc})")
            # 过期订阅：记录到数据库但不激活用户档案
            subscription = create_or_update_subscription(databases, user_id, verification_result)
            
            # 将用户档案设置为过期状态
            expiry_date = subscription['expiryDate']
            update_user_profile_expired(databases, user_id, expiry_date)
            
            return res.json({
                'success': True,
                'subscription': {
                    'id': subscription['$id'],
                    'productId': subscription['productId'],
                    'expiryDate': expiry_date,
                    'autoRenew': subscription.get('autoRenew', False),
                    'isExpired': True
                },
                'message': '订阅已过期',
                'isExpired': True
            })
        else:
            context.log(f"✅ [订阅验证] 订阅有效: 过期时间 {expiry_datetime}")
            # 有效订阅：正常处理
            subscription = create_or_update_subscription(databases, user_id, verification_result)
            
            # 更新用户档案为活跃状态
            expiry_date = subscription['expiryDate']
            update_user_profile_subscription(databases, user_id, expiry_date)
            
            context.log(f"[订阅验证] 订阅记录已更新，过期时间: {expiry_date}")
            
            return res.json({
                'success': True,
                'subscription': {
                    'id': subscription['$id'],
                    'productId': subscription['productId'],
                    'expiryDate': expiry_date,
                    'autoRenew': subscription['autoRenew'],
                    'isExpired': False
                },
                'message': '订阅已激活'
            })
        
    except Exception as e:
        context.error(f"订阅验证异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return res.json({
            'success': False,
            'error': f"服务器错误: {str(e)}"
        })


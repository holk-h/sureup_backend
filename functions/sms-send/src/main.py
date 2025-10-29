"""
火山引擎短信发送函数
使用 SendSmsVerifyCode API 发送验证码到指定手机号
使用官方SDK: volcengine-python-sdk
"""
import os
import json
from volcengine.ApiInfo import ApiInfo
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo
from volcengine.base.Service import Service

def main(context):
    """发送短信验证码"""
    
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
    
    context.log(f'收到请求，手机号: {phone}')
    
    # 验证手机号
    if not phone:
        return context.res.json({
            'success': False,
            'message': '请提供手机号'
        }, 400)
    
    # 去掉+86前缀（火山引擎支持带或不带+86）
    phone_number = phone.replace('+86', '') if phone.startswith('+86') else phone
    
    # 火山引擎配置
    access_key = os.environ.get('VOLC_ACCESS_KEY')
    secret_key = os.environ.get('VOLC_SECRET_KEY')
    sms_account = os.environ.get('VOLC_SMS_ACCOUNT')
    template_id = os.environ.get('VOLC_SMS_TEMPLATE_ID')
    sign_name = os.environ.get('VOLC_SMS_SIGN_NAME')
    
    if not all([access_key, secret_key, sms_account, template_id, sign_name]):
        context.log('缺少火山引擎配置')
        return context.res.json({
            'success': False,
            'message': '服务配置错误'
        }, 500)
    
    try:
        # 初始化火山引擎SMS服务
        service = _get_sms_service(access_key, secret_key)
        
        # 构造请求参数
        body = {
            'SmsAccount': sms_account,
            'Sign': sign_name,
            'TemplateID': template_id,
            'PhoneNumber': phone_number,
            'Scene': '登录注册',  # 验证码使用场景
            'CodeType': 6,  # 6位验证码
            'ExpireTime': 300,  # 5分钟有效期
            'TryCount': 3,  # 允许尝试3次
        }
        
        # 调用发送验证码API
        response_raw = service.json('SendSmsVerifyCode', {}, json.dumps(body))
        
        # 解析响应（可能是字符串）
        if isinstance(response_raw, str):
            response = json.loads(response_raw)
        elif isinstance(response_raw, bytes):
            response = json.loads(response_raw.decode('utf-8'))
        else:
            response = response_raw
        
        context.log(f'API响应: {json.dumps(response, ensure_ascii=False)}')
        
        # 检查响应
        if 'ResponseMetadata' in response:
            metadata = response['ResponseMetadata']
            
            # 检查是否有错误
            if 'Error' in metadata:
                error = metadata['Error']
                error_code = error.get('Code', '')
                error_msg = error.get('Message', '发送失败')
                
                context.log(f'发送短信失败: {error_code} - {error_msg}')
                
                # 处理常见错误
                user_msg = _get_user_friendly_error(error_code, error_msg)
                
                return context.res.json({
                    'success': False,
                    'message': user_msg
                }, 500)
        
        # 获取结果
        result = response.get('Result', {})
        message_ids = result.get('MessageID', [])
        message_id = message_ids[0] if message_ids else ''
        
        context.log(f'验证码已发送到 {phone_number}, MessageID: {message_id}')
        
        return context.res.json({
            'success': True,
            'message': '验证码已发送',
            'data': {
                'phone': phone,
                'messageId': message_id
            }
        })
        
    except Exception as e:
        context.error(f'发送短信异常: {str(e)}')
        return context.res.json({
            'success': False,
            'message': '发送验证码失败，请稍后重试'
        }, 500)


def _get_sms_service(access_key, secret_key):
    """
    初始化火山引擎SMS服务
    使用官方SDK
    """
    # API信息
    api_info = {
        'SendSmsVerifyCode': ApiInfo('POST', '/', {'Action': 'SendSmsVerifyCode', 'Version': '2020-01-01'}, {}, {}),
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


def _get_user_friendly_error(error_code, error_msg):
    """将错误码转换为用户友好的错误信息"""
    error_map = {
        'RE:0000': '服务暂时不可用，请稍后重试',
        'RE:0001': '短信服务未开通',
        'RE:0002': '服务异常，请联系客服',
        'RE:0003': '服务配置错误',
        'RE:0004': '短信签名错误',
        'RE:0005': '短信模板错误',
        'RE:0006': '手机号格式错误',
        'RE:0007': 'IP校验失败',
        'RE:0009': '请求参数错误',
        'RE:0010': '服务欠费，请联系管理员',
        'RE:0011': '不支持该地区发送',
        'RE:0012': '不支持的发送类型',
        'RE:0013': '发送量超过限制',
        'RE:0500': '服务异常，请稍后重试',
    }
    
    return error_map.get(error_code, f'发送失败: {error_msg}')


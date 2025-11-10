"""
短信发送函数
支持多个短信服务商：火山引擎、阿里云
使用模块化架构，可通过环境变量切换服务商
"""
import os
import sys
import json
from appwrite.client import Client
from appwrite.services.databases import Databases

# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from providers.base import SMSProviderFactory
from providers.volc_provider import VolcSMSProvider  # 导入以注册
from providers.aliyun_provider import AliyunSMSProvider  # 导入以注册


def _parse_request_body(body):
    """解析请求体"""
    if isinstance(body, dict):
        return body
    if isinstance(body, str) and body:
        return json.loads(body)
    return {}


def main(context):
    """发送短信验证码"""
    
    # 解析请求参数
    try:
        payload = _parse_request_body(context.req.body)
        phone = payload.get('phone', '')
    except Exception as e:
        context.error(f'解析请求参数失败: {str(e)}')
        return context.res.json({'success': False, 'message': '无效的请求参数'}, 400)
    
    # 验证手机号
    if not phone:
        return context.res.json({'success': False, 'message': '请提供手机号'}, 400)
    
    context.log(f'收到请求，手机号: {phone}')
    
    # 获取短信服务商配置
    sms_provider = os.environ.get('SMS_PROVIDER', 'aliyun').lower()
    context.log(f'使用短信服务商: {sms_provider}')
    
    try:
        # 创建短信服务商实例并发送验证码
        provider = _create_sms_provider(sms_provider, context)
        result = provider.send_verification_code(phone)
        
        if result['success']:
            context.log(f'验证码已发送到 {phone}, MessageID: {result.get("message_id", "")}')
            return context.res.json({
                'success': True,
                'message': result['message'],
                'data': {
                    'phone': phone,
                    'messageId': result.get('message_id', '')
                }
            })
        else:
            context.log(f'发送短信失败: {result["message"]}')
            return context.res.json({'success': False, 'message': result['message']}, 500)
            
    except Exception as e:
        context.error(f'发送短信异常: {str(e)}')
        return context.res.json({'success': False, 'message': '发送验证码失败，请稍后重试'}, 500)


def _get_volc_config():
    """获取火山引擎配置"""
    config = {
        'access_key': os.environ.get('VOLC_ACCESS_KEY'),
        'secret_key': os.environ.get('VOLC_SECRET_KEY'),
        'sms_account': os.environ.get('VOLC_SMS_ACCOUNT'),
        'template_id': os.environ.get('VOLC_SMS_TEMPLATE_ID'),
        'sign_name': os.environ.get('VOLC_SMS_SIGN_NAME'),
    }
    
    if not all(config.values()):
        raise ValueError('火山引擎配置不完整')
    
    return config


def _get_aliyun_config(context):
    """获取阿里云配置"""
    config = {
        'access_key_id': os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID'),
        'access_key_secret': os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET'),
        'sign_name': os.environ.get('ALIYUN_SMS_SIGN_NAME'),
        'template_code': os.environ.get('ALIYUN_SMS_TEMPLATE_CODE'),
    }
    
    # 日志输出配置状态（不包含敏感信息）
    context.log(f'阿里云配置: access_key_id={"已配置" if config["access_key_id"] else "未配置"}, '
                f'sign_name={config["sign_name"] or "未配置"}, '
                f'template_code={config["template_code"] or "未配置"}')
    
    # 添加数据库客户端用于存储验证码
    _add_appwrite_config(config, context)
    
    return config


def _add_appwrite_config(config, context):
    """添加 Appwrite 数据库配置"""
    appwrite_endpoint = os.environ.get('APPWRITE_ENDPOINT')
    appwrite_project_id = os.environ.get('APPWRITE_PROJECT_ID')
    appwrite_api_key = os.environ.get('APPWRITE_API_KEY')
    
    if all([appwrite_endpoint, appwrite_project_id, appwrite_api_key]):
        client = Client()
        client.set_endpoint(appwrite_endpoint)
        client.set_project(appwrite_project_id)
        client.set_key(appwrite_api_key)
        
        config['database_client'] = Databases(client)
        config['database_id'] = os.environ.get('APPWRITE_DATABASE_ID', 'main')
        config['verification_codes_collection_id'] = 'sms_verification_codes'
    else:
        context.log('Appwrite配置不完整，验证码将无法存储')


def _create_sms_provider(provider_name: str, context):
    """创建短信服务商实例"""
    
    config_getters = {
        'volc': lambda: _get_volc_config(),
        'aliyun': lambda: _get_aliyun_config(context)
    }
    
    if provider_name not in config_getters:
        raise ValueError(f'不支持的短信服务商: {provider_name}')
    
    config = config_getters[provider_name]()
    return SMSProviderFactory.create_provider(provider_name, config)
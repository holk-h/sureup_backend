"""
火山引擎短信服务商实现
"""
import json
from typing import Dict, Any
from volcengine.ApiInfo import ApiInfo
from volcengine.Credentials import Credentials
from volcengine.ServiceInfo import ServiceInfo
from volcengine.base.Service import Service
try:
    from .base import SMSProvider, SMSProviderFactory
except ImportError:
    from base import SMSProvider, SMSProviderFactory


class VolcSMSProvider(SMSProvider):
    """火山引擎短信服务商"""
    
    def validate_config(self) -> None:
        """验证火山引擎配置"""
        required_keys = ['access_key', 'secret_key', 'sms_account', 'template_id', 'sign_name']
        for key in required_keys:
            if not self.config.get(key):
                raise ValueError(f'火山引擎配置缺少必要参数: {key}')
    
    def send_verification_code(self, phone: str) -> Dict[str, Any]:
        """
        发送验证码
        使用火山引擎 SendSmsVerifyCode API
        """
        try:
            # 标准化手机号
            phone_number = self.normalize_phone(phone)
            
            # 初始化服务
            service = self._get_sms_service()
            
            # 构造请求参数
            body = {
                'SmsAccount': self.config['sms_account'],
                'Sign': self.config['sign_name'],
                'TemplateID': self.config['template_id'],
                'PhoneNumber': phone_number,
                'Scene': '登录注册',  # 验证码使用场景
                'CodeType': 6,  # 6位验证码
                'ExpireTime': 300,  # 5分钟有效期
                'TryCount': 3,  # 允许尝试3次
            }
            
            # 调用发送验证码API
            response_raw = service.json('SendSmsVerifyCode', {}, json.dumps(body))
            
            # 解析响应
            response = self._parse_response(response_raw)
            
            # 检查响应
            if 'ResponseMetadata' in response:
                metadata = response['ResponseMetadata']
                
                # 检查是否有错误
                if 'Error' in metadata:
                    error = metadata['Error']
                    error_code = error.get('Code', '')
                    error_msg = error.get('Message', '发送失败')
                    
                    return {
                        'success': False,
                        'message': self._get_user_friendly_error(error_code, error_msg),
                        'error_code': error_code
                    }
            
            # 获取结果
            result = response.get('Result', {})
            message_ids = result.get('MessageID', [])
            message_id = message_ids[0] if message_ids else ''
            
            return {
                'success': True,
                'message': '验证码已发送',
                'message_id': message_id
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'发送验证码失败: {str(e)}',
                'error_code': 'SEND_ERROR'
            }
    
    def verify_code(self, phone: str, code: str) -> Dict[str, Any]:
        """
        验证验证码
        使用火山引擎 CheckSmsVerifyCode API
        """
        try:
            # 标准化手机号
            phone_number = self.normalize_phone(phone)
            
            # 初始化服务
            service = self._get_sms_service()
            
            # 构造验证请求
            body = {
                'SmsAccount': self.config['sms_account'],
                'PhoneNumber': phone_number,
                'Scene': '登录注册',  # 必须与发送时的Scene一致
                'Code': code
            }
            
            # 调用校验验证码API
            response_raw = service.json('CheckSmsVerifyCode', {}, json.dumps(body))
            
            # 解析响应
            response = self._parse_response(response_raw)
            
            # 检查响应
            if 'ResponseMetadata' in response:
                metadata = response['ResponseMetadata']
                
                # 检查是否有错误
                if 'Error' in metadata:
                    error = metadata['Error']
                    error_code = error.get('Code', '')
                    error_msg = error.get('Message', '验证失败')
                    
                    return {
                        'success': False,
                        'message': f'验证失败: {error_msg}',
                        'error_code': error_code
                    }
            
            # 获取验证结果
            # Result: "0"-成功, "1"-错误, "2"-过期
            result = response.get('Result', '1')
            
            if result == '0':
                return {
                    'success': True,
                    'message': '验证成功'
                }
            elif result == '2':
                return {
                    'success': False,
                    'message': '验证码已过期',
                    'error_code': 'CODE_EXPIRED'
                }
            else:
                return {
                    'success': False,
                    'message': '验证码错误',
                    'error_code': 'CODE_INVALID'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'验证失败: {str(e)}',
                'error_code': 'VERIFY_ERROR'
            }
    
    def _get_sms_service(self):
        """初始化火山引擎SMS服务"""
        # API信息
        api_info = {
            'SendSmsVerifyCode': ApiInfo('POST', '/', {'Action': 'SendSmsVerifyCode', 'Version': '2020-01-01'}, {}, {}),
            'CheckSmsVerifyCode': ApiInfo('POST', '/', {'Action': 'CheckSmsVerifyCode', 'Version': '2020-01-01'}, {}, {}),
        }
        
        # 服务信息
        service_info = ServiceInfo(
            'sms.volcengineapi.com',
            {},
            Credentials(self.config['access_key'], self.config['secret_key'], 'volcSMS', 'cn-north-1'),
            10,
            10,
            'https'
        )
        
        # 创建服务实例
        return Service(service_info, api_info)
    
    def _parse_response(self, response_raw):
        """解析API响应"""
        if isinstance(response_raw, str):
            return json.loads(response_raw)
        elif isinstance(response_raw, bytes):
            return json.loads(response_raw.decode('utf-8'))
        else:
            return response_raw
    
    def _get_user_friendly_error(self, error_code: str, error_msg: str) -> str:
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


# 注册火山引擎提供商
SMSProviderFactory.register_provider('volc', VolcSMSProvider)

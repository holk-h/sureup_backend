"""
阿里云短信服务商实现
"""
import json
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
from alibabacloud_tea_util import models as util_models
try:
    from .base import SMSProvider, SMSProviderFactory
except ImportError:
    from base import SMSProvider, SMSProviderFactory


class AliyunSMSProvider(SMSProvider):
    """阿里云短信服务商"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = self._create_client()
        # 数据库相关配置（用于存储验证码）
        self.database_client = None
        if 'database_client' in config:
            self.database_client = config['database_client']
    
    def validate_config(self) -> None:
        """验证阿里云配置"""
        # 不进行配置验证，用户已确认配置正确
        pass
    
    def send_verification_code(self, phone: str) -> Dict[str, Any]:
        """
        发送验证码
        使用阿里云短信API
        """
        try:
            # 标准化手机号
            phone_number = self.normalize_phone(phone)
            
            # 生成6位验证码
            code = self._generate_verification_code()
            
            # 构造发送请求
            send_sms_request = dysmsapi_models.SendSmsRequest(
                sign_name=self.config['sign_name'],
                template_code=self.config['template_code'],
                phone_numbers=phone_number,
                template_param=json.dumps({'code': code})
            )
            
            runtime = util_models.RuntimeOptions()
            
            # 发送短信
            response = self.client.send_sms_with_options(send_sms_request, runtime)
            
            # 检查响应
            if response.status_code == 200 and response.body:
                body = response.body
                if body.code == 'OK':
                    # 发送成功，存储验证码到数据库
                    if self.database_client:
                        self._store_verification_code(phone_number, code)
                    
                    return {
                        'success': True,
                        'message': '验证码已发送',
                        'message_id': body.biz_id
                    }
                else:
                    return {
                        'success': False,
                        'message': self._get_user_friendly_error(body.code, body.message),
                        'error_code': body.code
                    }
            else:
                return {
                    'success': False,
                    'message': '发送失败，请稍后重试',
                    'error_code': 'HTTP_ERROR'
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
        从数据库中查询并验证
        """
        try:
            # 标准化手机号
            phone_number = self.normalize_phone(phone)
            
            if not self.database_client:
                return {
                    'success': False,
                    'message': '验证服务不可用',
                    'error_code': 'SERVICE_UNAVAILABLE'
                }
            
            # 从数据库查询验证码
            stored_code_info = self._get_verification_code(phone_number)
            
            if not stored_code_info:
                return {
                    'success': False,
                    'message': '验证码不存在或已过期',
                    'error_code': 'CODE_NOT_FOUND'
                }
            
            stored_code = stored_code_info.get('code')
            created_at = stored_code_info.get('created_at')
            
            # 检查验证码是否过期（5分钟有效期）
            if self._is_code_expired(created_at):
                # 删除过期的验证码
                self._delete_verification_code(phone_number)
                return {
                    'success': False,
                    'message': '验证码已过期',
                    'error_code': 'CODE_EXPIRED'
                }
            
            # 验证验证码
            if stored_code == code:
                # 验证成功，删除验证码
                self._delete_verification_code(phone_number)
                return {
                    'success': True,
                    'message': '验证成功'
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
    
    def _create_client(self) -> DysmsapiClient:
        """创建阿里云短信客户端"""
        # 使用环境变量或配置的凭据
        if 'access_key_id' in self.config and 'access_key_secret' in self.config:
            # 使用显式配置的凭据
            config = open_api_models.Config(
                access_key_id=self.config['access_key_id'],
                access_key_secret=self.config['access_key_secret']
            )
        else:
            # 使用默认凭据链（环境变量等）
            credential = CredentialClient()
            config = open_api_models.Config(credential=credential)
        
        # 设置端点
        config.endpoint = 'dysmsapi.aliyuncs.com'
        
        return DysmsapiClient(config)
    
    def _generate_verification_code(self, length: int = 6) -> str:
        """生成验证码"""
        return ''.join(random.choices(string.digits, k=length))
    
    def _store_verification_code(self, phone: str, code: str) -> None:
        """存储验证码到数据库"""
        if not self.database_client:
            return
        
        try:
            # 删除旧的验证码（如果存在）
            self._delete_verification_code(phone)
            
            # 存储新的验证码
            from datetime import timezone
            current_time = datetime.now(timezone.utc)
            document_data = {
                'phone': phone,
                'code': code,
                'createdAt': current_time.isoformat(),
                'expiresAt': (current_time + timedelta(minutes=5)).isoformat()
            }
            
            self.database_client.create_document(
                database_id=self.config.get('database_id', 'main'),
                collection_id=self.config.get('verification_codes_collection_id', 'sms_verification_codes'),
                document_id=phone,  # 使用手机号作为文档ID
                data=document_data
            )
        except Exception as e:
            # 存储失败不影响短信发送
            print(f'存储验证码失败: {str(e)}')
    
    def _get_verification_code(self, phone: str) -> Optional[Dict[str, Any]]:
        """从数据库获取验证码"""
        if not self.database_client:
            return None
        
        try:
            document = self.database_client.get_document(
                database_id=self.config.get('database_id', 'main'),
                collection_id=self.config.get('verification_codes_collection_id', 'sms_verification_codes'),
                document_id=phone
            )
            
            return {
                'code': document.get('code'),
                'created_at': document.get('createdAt'),
                'expires_at': document.get('expiresAt')
            }
        except Exception:
            return None
    
    def _delete_verification_code(self, phone: str) -> None:
        """删除验证码"""
        if not self.database_client:
            return
        
        try:
            self.database_client.delete_document(
                database_id=self.config.get('database_id', 'main'),
                collection_id=self.config.get('verification_codes_collection_id', 'sms_verification_codes'),
                document_id=phone
            )
        except Exception:
            # 删除失败不影响业务流程
            pass
    
    def _is_code_expired(self, created_at: str) -> bool:
        """检查验证码是否过期"""
        try:
            # 解析创建时间
            if created_at.endswith('Z'):
                created_time = datetime.fromisoformat(created_at[:-1])
            else:
                created_time = datetime.fromisoformat(created_at)
            
            # 检查是否超过5分钟
            expiry_time = created_time + timedelta(minutes=5)
            return datetime.utcnow() > expiry_time
        except Exception:
            # 解析失败认为已过期
            return True
    
    def _get_user_friendly_error(self, error_code: str, error_msg: str) -> str:
        """将错误码转换为用户友好的错误信息"""
        error_map = {
            'OK': '发送成功',
            'isp.RAM_PERMISSION_DENY': '权限不足，请联系管理员',
            'isv.OUT_OF_SERVICE': '业务停机，请联系管理员',
            'isv.PRODUCT_UN_SUBSCRIPT': '未开通云通信产品',
            'isv.PRODUCT_UNSUBSCRIBE': '产品未开通',
            'isv.ACCOUNT_NOT_EXISTS': '账户不存在',
            'isv.ACCOUNT_ABNORMAL': '账户异常',
            'isv.SMS_TEMPLATE_ILLEGAL': '短信模板不合法',
            'isv.SMS_SIGNATURE_ILLEGAL': '短信签名不合法',
            'isv.INVALID_PARAMETERS': '参数异常',
            'isv.MOBILE_NUMBER_ILLEGAL': '手机号码格式错误',
            'isv.MOBILE_COUNT_OVER_LIMIT': '手机号码数量超过限制',
            'isv.TEMPLATE_MISSING_PARAMETERS': '模板缺少变量',
            'isv.BUSINESS_LIMIT_CONTROL': '业务限流',
            'isv.INVALID_JSON_PARAM': 'JSON参数不合法',
            'isv.BLACK_KEY_CONTROL_LIMIT': '黑名单管控',
            'isv.PARAM_LENGTH_LIMIT': '参数超出长度限制',
            'isv.PARAM_NOT_SUPPORT_URL': '不支持URL',
            'isv.AMOUNT_NOT_ENOUGH': '账户余额不足',
            'isv.TEMPLATE_PARAMS_ILLEGAL': '模板变量里包含非法关键字',
        }
        
        return error_map.get(error_code, f'发送失败: {error_msg}')


# 注册阿里云提供商
SMSProviderFactory.register_provider('aliyun', AliyunSMSProvider)

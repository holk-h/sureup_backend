"""
短信服务商基类
定义统一的接口规范
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class SMSProvider(ABC):
    """短信服务商基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化短信服务商
        
        Args:
            config: 配置参数字典
        """
        self.config = config
        self.validate_config()
    
    @abstractmethod
    def validate_config(self) -> None:
        """
        验证配置参数
        子类必须实现此方法来验证必要的配置参数
        
        Raises:
            ValueError: 当配置参数无效时
        """
        pass
    
    @abstractmethod
    def send_verification_code(self, phone: str) -> Dict[str, Any]:
        """
        发送验证码
        
        Args:
            phone: 手机号码（不带+86前缀）
            
        Returns:
            Dict[str, Any]: 发送结果
            {
                'success': bool,
                'message': str,
                'message_id': Optional[str],
                'error_code': Optional[str]
            }
        """
        pass
    
    @abstractmethod
    def verify_code(self, phone: str, code: str) -> Dict[str, Any]:
        """
        验证验证码
        
        Args:
            phone: 手机号码（不带+86前缀）
            code: 验证码
            
        Returns:
            Dict[str, Any]: 验证结果
            {
                'success': bool,
                'message': str,
                'error_code': Optional[str]
            }
        """
        pass
    
    def normalize_phone(self, phone: str) -> str:
        """
        标准化手机号格式
        
        Args:
            phone: 原始手机号
            
        Returns:
            str: 标准化后的手机号（不带+86前缀）
        """
        if not phone:
            return ''
        
        # 移除所有空格和特殊字符
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # 移除+86前缀
        if phone.startswith('+86'):
            phone = phone[3:]
        elif phone.startswith('86') and len(phone) == 13:
            phone = phone[2:]
        
        return phone
    
    def get_phone_with_country_code(self, phone: str) -> str:
        """
        获取带国家代码的手机号
        
        Args:
            phone: 手机号
            
        Returns:
            str: 带+86前缀的手机号
        """
        normalized_phone = self.normalize_phone(phone)
        return f'+86{normalized_phone}'


class SMSProviderFactory:
    """短信服务商工厂类"""
    
    _providers = {}
    
    @classmethod
    def register_provider(cls, name: str, provider_class):
        """注册短信服务商"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create_provider(cls, name: str, config: Dict[str, Any]) -> SMSProvider:
        """
        创建短信服务商实例
        
        Args:
            name: 服务商名称
            config: 配置参数
            
        Returns:
            SMSProvider: 服务商实例
            
        Raises:
            ValueError: 当服务商不存在时
        """
        if name not in cls._providers:
            raise ValueError(f'未知的短信服务商: {name}')
        
        provider_class = cls._providers[name]
        return provider_class(config)
    
    @classmethod
    def get_available_providers(cls) -> list:
        """获取可用的服务商列表"""
        return list(cls._providers.keys())

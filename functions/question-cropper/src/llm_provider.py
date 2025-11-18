"""
通用 LLM 提供商模块
支持多个 LLM 提供商：豆包（Doubao）、ChatGPT、Gemini

使用示例：
    # 文本对话
    provider = get_llm_provider()
    response = provider.chat("你好，请帮我分析这道题")
    
    # 视觉分析（图片 + 文本）
    response = provider.chat_with_vision(
        prompt="分析这张图片中的数学题",
        image_url="https://example.com/image.jpg"
    )
    
    # 或使用 base64
    response = provider.chat_with_vision(
        prompt="分析这张图片中的数学题",
        image_base64="data:image/jpeg;base64,/9j/4AAQ..."
    )

环境变量配置：
    LLM_PROVIDER=doubao  # 或 openai, gemini
    
    # 豆包配置
    DOUBAO_API_KEY=your_api_key
    DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
    DOUBAO_MODEL=doubao-pro-32k  # 或其他模型
    
    # OpenAI 配置
    OPENAI_API_KEY=your_api_key
    OPENAI_API_BASE=https://api.openai.com/v1  # 可选
    OPENAI_MODEL=gpt-4o  # 或 gpt-4-turbo-preview, gpt-4-vision-preview
    
    # Gemini 配置
    GEMINI_API_KEY=your_api_key
    GEMINI_MODEL=gemini-1.5-pro  # 或 gemini-1.5-flash
"""

import os
import json
import base64
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import requests


class LLMProvider(ABC):
    """LLM 提供商基类"""
    
    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.timeout = kwargs.get('timeout', 60)
        self.max_retries = kwargs.get('max_retries', 3)
        self.retry_delay = kwargs.get('retry_delay', 1)
    
    @abstractmethod
    def chat(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        文本对话
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数（0-1）
            max_tokens: 最大 token 数
            
        Returns:
            LLM 的响应文本
        """
        pass
    
    @abstractmethod
    def chat_with_vision(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        视觉对话（多模态）
        
        注意：image_url 和 image_base64 只需提供一个
        
        Args:
            prompt: 用户提示词
            image_url: 图片 URL（二选一）
            image_base64: 图片 base64 编码（二选一，需包含 data:image/...;base64, 前缀）
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
            
        Returns:
            LLM 的响应文本
        """
        pass
    
    def _retry_request(self, request_func, *args, **kwargs):
        """带重试机制的请求"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return request_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))  # 指数退避
                continue
        raise last_error
    
    @staticmethod
    def _download_image_to_base64(image_url: str) -> str:
        """下载图片并转换为 base64"""
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # 获取 content type
            content_type = response.headers.get('content-type', 'image/jpeg')
            
            # 转换为 base64
            image_data = base64.b64encode(response.content).decode('utf-8')
            return f"data:{content_type};base64,{image_data}"
        except Exception as e:
            raise ValueError(f"下载图片失败: {str(e)}")


class DoubaoProvider(LLMProvider):
    """
    豆包（字节跳动）LLM 提供商
    
    API 文档: https://www.volcengine.com/docs/82379/1099475
    """
    
    def __init__(self, api_key: str, model: str = "doubao-pro-32k", endpoint: str = None, **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.endpoint = endpoint or os.environ.get(
            'DOUBAO_ENDPOINT',
            'https://ark.cn-beijing.volces.com/api/v3'
        )
    
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """豆包文本对话"""
        
        def _make_request():
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            # 添加其他参数
            payload.update(kwargs)
            
            response = requests.post(
                f"{self.endpoint}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._retry_request(_make_request)
    
    def chat_with_vision(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """豆包视觉对话"""
        
        if not image_url and not image_base64:
            raise ValueError("必须提供 image_url 或 image_base64")
        
        def _make_request():
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # 构建包含图片的消息
            content = [{"type": "text", "text": prompt}]
            
            if image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            elif image_base64:
                # 确保有正确的前缀
                if not image_base64.startswith('data:'):
                    image_base64 = f"data:image/jpeg;base64,{image_base64}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_base64}
                })
            
            messages.append({"role": "user", "content": content})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            payload.update(kwargs)
            
            response = requests.post(
                f"{self.endpoint}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._retry_request(_make_request)


class ChatGPTProvider(LLMProvider):
    """
    OpenAI ChatGPT 提供商
    
    API 文档: https://platform.openai.com/docs/api-reference/chat
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o", api_base: str = None, **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.api_base = api_base or os.environ.get(
            'OPENAI_API_BASE',
            'https://api.openai.com/v1'
        )
    
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """ChatGPT 文本对话"""
        
        def _make_request():
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            payload.update(kwargs)
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._retry_request(_make_request)
    
    def chat_with_vision(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """ChatGPT 视觉对话"""
        
        if not image_url and not image_base64:
            raise ValueError("必须提供 image_url 或 image_base64")
        
        def _make_request():
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # 构建包含图片的消息
            content = [{"type": "text", "text": prompt}]
            
            if image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            elif image_base64:
                # 确保有正确的前缀
                if not image_base64.startswith('data:'):
                    image_base64 = f"data:image/jpeg;base64,{image_base64}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_base64}
                })
            
            messages.append({"role": "user", "content": content})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            payload.update(kwargs)
            
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
        
        return self._retry_request(_make_request)


class GeminiProvider(LLMProvider):
    """
    Google Gemini 提供商
    
    API 文档: https://ai.google.dev/api/rest
    """
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.api_base = "https://generativelanguage.googleapis.com/v1beta"
    
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Gemini 文本对话"""
        
        def _make_request():
            # Gemini 使用不同的消息格式
            contents = []
            
            # System prompt 作为第一条消息
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                })
                contents.append({
                    "role": "model",
                    "parts": [{"text": "好的，我明白了。"}]
                })
            
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                }
            }
            
            if max_tokens:
                payload["generationConfig"]["maxOutputTokens"] = max_tokens
            
            response = requests.post(
                f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
        
        return self._retry_request(_make_request)
    
    def chat_with_vision(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Gemini 视觉对话"""
        
        if not image_url and not image_base64:
            raise ValueError("必须提供 image_url 或 image_base64")
        
        def _make_request():
            # 如果是 URL，需要下载并转换为 base64
            if image_url:
                image_base64_data = self._download_image_to_base64(image_url)
            else:
                image_base64_data = image_base64
            
            # 提取纯 base64 数据（去掉前缀）
            if ',' in image_base64_data:
                mime_type, base64_data = image_base64_data.split(',', 1)
                # 提取 mime type
                if 'image/' in mime_type:
                    mime = mime_type.split(';')[0].replace('data:', '')
                else:
                    mime = 'image/jpeg'
            else:
                base64_data = image_base64_data
                mime = 'image/jpeg'
            
            contents = []
            
            # System prompt
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                })
                contents.append({
                    "role": "model",
                    "parts": [{"text": "好的，我明白了。"}]
                })
            
            # 用户消息（文本 + 图片）
            parts = [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64_data
                    }
                }
            ]
            
            contents.append({
                "role": "user",
                "parts": parts
            })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                }
            }
            
            if max_tokens:
                payload["generationConfig"]["maxOutputTokens"] = max_tokens
            
            response = requests.post(
                f"{self.api_base}/models/{self.model}:generateContent?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
        
        return self._retry_request(_make_request)


# ============ 工厂函数 ============

def get_llm_provider(
    provider_name: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """
    获取 LLM 提供商实例
    
    Args:
        provider_name: 提供商名称 (doubao/openai/gemini)，不提供则从环境变量读取
        **kwargs: 传递给提供商的额外参数
        
    Returns:
        LLMProvider 实例
        
    环境变量：
        LLM_PROVIDER: 默认提供商 (doubao/openai/gemini)
        
        DOUBAO_API_KEY, DOUBAO_MODEL, DOUBAO_ENDPOINT
        OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_BASE
        GEMINI_API_KEY, GEMINI_MODEL
    """
    
    # 确定使用哪个提供商
    provider_name = provider_name or os.environ.get('LLM_PROVIDER', 'doubao').lower()
    
    if provider_name in ['doubao', 'bytedance']:
        api_key = kwargs.get('api_key') or os.environ.get('DOUBAO_API_KEY')
        if not api_key:
            raise ValueError("需要提供 DOUBAO_API_KEY")
        
        model = kwargs.get('model') or os.environ.get('DOUBAO_MODEL', 'doubao-pro-32k')
        endpoint = kwargs.get('endpoint') or os.environ.get('DOUBAO_ENDPOINT')
        
        return DoubaoProvider(
            api_key=api_key,
            model=model,
            endpoint=endpoint,
            **{k: v for k, v in kwargs.items() if k not in ['api_key', 'model', 'endpoint']}
        )
    
    elif provider_name in ['openai', 'chatgpt', 'gpt']:
        api_key = kwargs.get('api_key') or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("需要提供 OPENAI_API_KEY")
        
        model = kwargs.get('model') or os.environ.get('OPENAI_MODEL', 'gpt-4o')
        api_base = kwargs.get('api_base') or os.environ.get('OPENAI_API_BASE')
        
        return ChatGPTProvider(
            api_key=api_key,
            model=model,
            api_base=api_base,
            **{k: v for k, v in kwargs.items() if k not in ['api_key', 'model', 'api_base']}
        )
    
    elif provider_name == 'gemini':
        api_key = kwargs.get('api_key') or os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("需要提供 GEMINI_API_KEY")
        
        model = kwargs.get('model') or os.environ.get('GEMINI_MODEL', 'gemini-1.5-pro')
        
        return GeminiProvider(
            api_key=api_key,
            model=model,
            **{k: v for k, v in kwargs.items() if k not in ['api_key', 'model']}
        )
    
    else:
        raise ValueError(f"不支持的 LLM 提供商: {provider_name}。支持的提供商: doubao, openai, gemini")


# ============ 便捷函数 ============

def chat(prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
    """便捷的文本对话函数"""
    provider = get_llm_provider()
    return provider.chat(prompt, system_prompt=system_prompt, **kwargs)


def chat_with_vision(
    prompt: str,
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """
    便捷的视觉对话函数
    
    注意：image_url 和 image_base64 只需提供一个
    """
    provider = get_llm_provider()
    return provider.chat_with_vision(
        prompt,
        image_url=image_url,
        image_base64=image_base64,
        system_prompt=system_prompt,
        **kwargs
    )


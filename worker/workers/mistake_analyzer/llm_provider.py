"""
火山引擎 LLM 提供商模块
基于火山引擎官方 ARK SDK 实现，支持推理和多模态分析

使用示例：
    # 文本对话
    provider = get_llm_provider()
    response = await provider.chat("你好，请帮我分析这道题")
    
    # 视觉分析（图片 + 文本）
    response = await provider.chat_with_vision(
        prompt="分析这张图片中的数学题",
        image_url="https://example.com/image.jpg"
    )
    
    # 启用思考模式（深度分析）
    response = await provider.chat(
        prompt="分析这道题",
        thinking={"type": "enabled"},
        reasoning_effort="high"
    )

环境变量配置（兼容豆包配置）：
    # 火山引擎配置
    DOUBAO_API_KEY=your_api_key              # API Key
    DOUBAO_MODEL=your_endpoint_id            # 推理接入点 ID
    DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3  # API 端点
    
    # 高级参数
    VOLC_TEMPERATURE=0.7                     # 温度（默认 0.7）
    VOLC_TOP_P=0.9                           # Top-P 采样（默认 0.9）
    VOLC_MAX_TOKENS=4096                     # 最大生成 token 数（默认 4096）

API 文档:
    - 推理服务: https://www.volcengine.com/docs/82379/1449737
    - 多模态: https://www.volcengine.com/docs/82379/1399009
"""

import os
import json
import base64
import asyncio
from typing import Dict, List, Optional, Any, Union

try:
    from volcenginesdkarkruntime import Ark
except ImportError:
    # 兼容性处理：如果没有安装 SDK，使用 httpx
    import httpx
    Ark = None


class VolcengineLLMProvider:
    """
    火山引擎 LLM 提供商
    
    基于火山引擎官方 ARK SDK 实现，支持：
    - 文本对话
    - 多模态（视觉）分析
    - 深度思考模式（通过 thinking + reasoning_effort 参数）
    - 流式输出（可选）
    """
    
    def __init__(
        self,
        api_key: str,
        endpoint_id: str,
        endpoint: str = "https://ark.cn-beijing.volces.com/api/v3",
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 1,
        **kwargs
    ):
        """
        初始化火山引擎 LLM 提供商
        
        Args:
            api_key: 火山引擎 API Key
            endpoint_id: 推理接入点 ID（作为 model 参数）
            endpoint: API 端点地址
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.endpoint_id = endpoint_id
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 初始化 ARK 客户端
        if Ark:
            self.client = Ark(
                api_key=api_key,
                base_url=endpoint,
                timeout=timeout
            )
        else:
            self.client = None
            print("⚠️ 火山引擎 SDK 未安装，将使用 HTTP 方式调用")
        
        # 默认参数
        self.default_temperature = kwargs.get('temperature', 0.7)
        self.default_top_p = kwargs.get('top_p', 0.9)
        self.default_max_tokens = kwargs.get('max_tokens', 4096)
        self.default_stream = kwargs.get('stream', False)
        
        # 额外参数
        self.extra_params = {k: v for k, v in kwargs.items() 
                            if k not in ['temperature', 'top_p', 'max_tokens', 
                                        'stream', 'timeout', 'max_retries', 'retry_delay']}
    
    async def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        文本对话（异步）
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数（0-1），控制随机性
            top_p: Top-P 采样参数（0-1）
            max_tokens: 最大生成 token 数
            thinking: 思考模式配置，例如 {"type": "enabled"} 或 {"type": "disabled"}
                     - "enabled": 启用深度思考
                     - "disabled": 禁用深度思考
                     - "auto": 模型自行判断
            reasoning_effort: 推理深度（"minimal", "low", "medium", "high"）
                     - "minimal": 关闭思考，直接回答
                     - "low": 轻量思考，侧重快速响应
                     - "medium": 均衡模式，兼顾速度与深度
                     - "high": 深度分析，处理复杂问题
            stream: 是否使用流式输出
            **kwargs: 其他模型参数
            
        Returns:
            LLM 的响应文本
            
        注意：
            - thinking["type"]="enabled" 时才能使用 reasoning_effort="low/medium/high"
            - thinking["type"]="disabled" 时，reasoning_effort 只能为 "minimal"
        """
        
        if self.client and Ark:
            # 使用官方 SDK
            return await self._chat_with_sdk(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                stream=stream,
                **kwargs
            )
        else:
            # 降级到 HTTP 方式
            return await self._chat_with_http(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                stream=stream,
                **kwargs
            )
    
    async def _chat_with_sdk(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """使用火山引擎 SDK 进行文本对话"""
        
        async def _make_request():
            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # 构建参数
            params = {
                "model": self.endpoint_id,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "top_p": top_p if top_p is not None else self.default_top_p,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "stream": stream,
            }
            
            # 添加思考模式参数
            if thinking is not None:
                params["thinking"] = thinking
            
            if reasoning_effort is not None:
                params["reasoning_effort"] = reasoning_effort
            
            # 添加其他参数
            params.update(kwargs)
            params.update(self.extra_params)
            
            # 在事件循环中调用同步的 SDK
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(**params)
            )
            
            # 提取响应内容
            content = response.choices[0].message.content
            
            # 记录思考 token 使用（如果有）
            if hasattr(response, 'usage') and hasattr(response.usage, 'reasoning_tokens'):
                reasoning_tokens = response.usage.reasoning_tokens
                if reasoning_tokens > 0:
                    print(f"[推理模式] 使用了 {reasoning_tokens} 个推理 tokens")
            
            return content
        
        return await self._retry_request(_make_request)
    
    async def chat_with_vision(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        视觉对话（多模态，异步）
        
        注意：image_url 和 image_base64 只需提供一个
        
        Args:
            prompt: 用户提示词
            image_url: 图片 URL（二选一）
            image_base64: 图片 base64 编码（二选一，需包含 data:image/...;base64, 前缀）
            system_prompt: 系统提示词
            temperature: 温度参数
            top_p: Top-P 采样参数
            max_tokens: 最大生成 token 数
            thinking: 思考模式配置，例如 {"type": "enabled"}
            reasoning_effort: 推理深度（"minimal", "low", "medium", "high"）
            stream: 是否使用流式输出
            **kwargs: 其他模型参数
            
        Returns:
            LLM 的响应文本
        """
        
        if not image_url and not image_base64:
            raise ValueError("必须提供 image_url 或 image_base64")
        
        if self.client and Ark:
            # 使用官方 SDK
            return await self._chat_with_vision_sdk(
                prompt=prompt,
                image_url=image_url,
                image_base64=image_base64,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                stream=stream,
                **kwargs
            )
        else:
            # 降级到 HTTP 方式
            return await self._chat_with_vision_http(
                prompt=prompt,
                image_url=image_url,
                image_base64=image_base64,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                stream=stream,
                **kwargs
            )
    
    async def _chat_with_vision_sdk(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """使用火山引擎 SDK 进行视觉对话"""
        
        async def _make_request():
            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # 构建包含图片的消息内容
            content = [{"type": "text", "text": prompt}]
            
            if image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            elif image_base64:
                # 确保有正确的前缀
                formatted_image = image_base64
                if not formatted_image.startswith('data:'):
                    formatted_image = f"data:image/jpeg;base64,{formatted_image}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": formatted_image}
                })
            
            messages.append({"role": "user", "content": content})
            
            # 构建参数
            params = {
                "model": self.endpoint_id,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "top_p": top_p if top_p is not None else self.default_top_p,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "stream": stream,
            }
            
            # 添加思考模式参数
            if thinking is not None:
                params["thinking"] = thinking
            
            if reasoning_effort is not None:
                params["reasoning_effort"] = reasoning_effort
            
            # 添加其他参数
            params.update(kwargs)
            params.update(self.extra_params)
            
            # 在事件循环中调用同步的 SDK
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(**params)
            )
            
            # 提取响应内容
            content = response.choices[0].message.content
            
            # 记录思考 token 使用（如果有）
            if hasattr(response, 'usage') and hasattr(response.usage, 'reasoning_tokens'):
                reasoning_tokens = response.usage.reasoning_tokens
                if reasoning_tokens > 0:
                    print(f"[推理模式] 使用了 {reasoning_tokens} 个推理 tokens")
            
            return content
        
        return await self._retry_request(_make_request)
    
    # ============ HTTP 降级方案 ============
    
    async def _chat_with_http(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """使用 HTTP 方式进行文本对话（降级方案）"""
        
        async def _make_request():
            import httpx
            
            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.endpoint_id,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "top_p": top_p if top_p is not None else self.default_top_p,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "stream": stream,
            }
            
            # 添加思考模式参数
            if thinking is not None:
                payload["thinking"] = thinking
            
            if reasoning_effort is not None:
                payload["reasoning_effort"] = reasoning_effort
            
            payload.update(kwargs)
            payload.update(self.extra_params)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.endpoint}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            usage = result.get('usage', {})
            reasoning_tokens = usage.get('reasoning_tokens', 0)
            if reasoning_tokens > 0:
                print(f"[推理模式] 使用了 {reasoning_tokens} 个推理 tokens")
            
            return content
        
        return await self._retry_request(_make_request)
    
    async def _chat_with_vision_http(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """使用 HTTP 方式进行视觉对话（降级方案）"""
        
        async def _make_request():
            import httpx
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            content = [{"type": "text", "text": prompt}]
            
            if image_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            elif image_base64:
                formatted_image = image_base64
                if not formatted_image.startswith('data:'):
                    formatted_image = f"data:image/jpeg;base64,{formatted_image}"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": formatted_image}
                })
            
            messages.append({"role": "user", "content": content})
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.endpoint_id,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "top_p": top_p if top_p is not None else self.default_top_p,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "stream": stream,
            }
            
            # 添加思考模式参数
            if thinking is not None:
                payload["thinking"] = thinking
            
            if reasoning_effort is not None:
                payload["reasoning_effort"] = reasoning_effort
            
            payload.update(kwargs)
            payload.update(self.extra_params)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.endpoint}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            usage = result.get('usage', {})
            reasoning_tokens = usage.get('reasoning_tokens', 0)
            if reasoning_tokens > 0:
                print(f"[推理模式] 使用了 {reasoning_tokens} 个推理 tokens")
            
            return content
        
        return await self._retry_request(_make_request)
    
    async def _retry_request(self, request_func, *args, **kwargs):
        """带重试机制的异步请求"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await request_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                # 对于某些错误不重试
                error_msg = str(e).lower()
                if '401' in error_msg or '403' in error_msg or '404' in error_msg:
                    raise
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"[重试] 请求出错: {str(e)}，{delay}秒后重试... (尝试 {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
                continue
        raise last_error


# ============ 工厂函数 ============

def get_llm_provider(**kwargs) -> VolcengineLLMProvider:
    """
    获取火山引擎 LLM 提供商实例
    
    Args:
        **kwargs: 传递给提供商的额外参数，会覆盖环境变量
        
    Returns:
        VolcengineLLMProvider 实例
    """
    
    # 从环境变量或 kwargs 获取配置（兼容两种命名）
    api_key = (
        kwargs.get('api_key') or 
        os.environ.get('VOLC_API_KEY') or 
        os.environ.get('DOUBAO_API_KEY')
    )
    endpoint_id = (
        kwargs.get('endpoint_id') or 
        os.environ.get('VOLC_ENDPOINT_ID') or 
        os.environ.get('DOUBAO_MODEL')
    )
    endpoint = (
        kwargs.get('endpoint') or 
        os.environ.get('VOLC_ENDPOINT') or 
        os.environ.get('DOUBAO_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3')
    )
    
    # 验证必需参数
    if not api_key:
        raise ValueError("需要提供 VOLC_API_KEY 或 DOUBAO_API_KEY")
    if not endpoint_id:
        raise ValueError("需要提供 VOLC_ENDPOINT_ID 或 DOUBAO_MODEL")
    
    # 可选参数
    timeout = kwargs.get('timeout') or int(os.environ.get('VOLC_TIMEOUT', '120'))
    max_retries = kwargs.get('max_retries') or int(os.environ.get('VOLC_MAX_RETRIES', '3'))
    retry_delay = kwargs.get('retry_delay') or int(os.environ.get('VOLC_RETRY_DELAY', '1'))
    
    # 默认模型参数
    temperature = kwargs.get('temperature') or float(os.environ.get('VOLC_TEMPERATURE', '0.7'))
    top_p = kwargs.get('top_p') or float(os.environ.get('VOLC_TOP_P', '0.9'))
    max_tokens = kwargs.get('max_tokens') or int(os.environ.get('VOLC_MAX_TOKENS', '4096'))
    stream = kwargs.get('stream') or os.environ.get('VOLC_STREAM', 'false').lower() == 'true'
    
    return VolcengineLLMProvider(
        api_key=api_key,
        endpoint_id=endpoint_id,
        endpoint=endpoint,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stream=stream,
        **{k: v for k, v in kwargs.items() if k not in [
            'api_key', 'endpoint_id', 'endpoint',
            'timeout', 'max_retries', 'retry_delay', 'temperature', 'top_p',
            'max_tokens', 'stream'
        ]}
    )


# ============ 便捷函数 ============

async def chat(prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
    """便捷的文本对话函数（异步）"""
    provider = get_llm_provider()
    return await provider.chat(prompt, system_prompt=system_prompt, **kwargs)


async def chat_with_vision(
    prompt: str,
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """
    便捷的视觉对话函数（异步）
    
    注意：image_url 和 image_base64 只需提供一个
    """
    provider = get_llm_provider()
    return await provider.chat_with_vision(
        prompt,
        image_url=image_url,
        image_base64=image_base64,
        system_prompt=system_prompt,
        **kwargs
    )

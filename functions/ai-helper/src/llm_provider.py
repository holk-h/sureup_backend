"""
火山引擎 LLM 提供商模块
基于火山引擎官方 ARK SDK 实现，支持推理和多模态分析
"""

import os
import json
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
        if self.client and Ark:
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
    ) -> Union[str, Any]:
        async def _make_request():
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            params = {
                "model": self.endpoint_id,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "top_p": top_p if top_p is not None else self.default_top_p,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "stream": stream,
            }
            
            if thinking is not None:
                params["thinking"] = thinking
            
            if reasoning_effort is not None:
                params["reasoning_effort"] = reasoning_effort
            
            params.update(kwargs)
            params.update(self.extra_params)
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(**params)
            )
            
            content = response.choices[0].message.content
            return content
        
        return await self._retry_request(_make_request)
    
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
        async def _make_request():
            import httpx
            
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
            return content
        
        return await self._retry_request(_make_request)
    
    async def _retry_request(self, request_func, *args, **kwargs):
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await request_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                if '401' in error_msg or '403' in error_msg or '404' in error_msg:
                    raise
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                continue
        raise last_error


def get_llm_provider(**kwargs) -> VolcengineLLMProvider:
    api_key = (
        kwargs.get('api_key') or 
        os.environ.get('DOUBAO_API_KEY') or 
        os.environ.get('VOLC_API_KEY')
    )
    endpoint_id = (
        kwargs.get('endpoint_id') or 
        os.environ.get('DOUBAO_MODEL') or 
        os.environ.get('VOLC_ENDPOINT_ID')
    )
    endpoint = (
        kwargs.get('endpoint') or 
        os.environ.get('DOUBAO_ENDPOINT') or 
        os.environ.get('VOLC_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3')
    )
    
    if not api_key or not endpoint_id:
        raise ValueError("Missing API Key or Endpoint ID (DOUBAO_API_KEY/DOUBAO_MODEL)")
    
    return VolcengineLLMProvider(
        api_key=api_key,
        endpoint_id=endpoint_id,
        endpoint=endpoint,
        **kwargs
    )


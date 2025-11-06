"""
测试流式输出功能

用于验证火山引擎 LLM 流式 API 是否正常工作
"""
import os
import sys
import asyncio
from pathlib import Path

# 添加 mistake_analyzer 路径以导入 llm_provider
mistake_analyzer_path = Path(__file__).parent.parent / 'mistake_analyzer'
sys.path.insert(0, str(mistake_analyzer_path))

from llm_provider import get_llm_provider


async def test_stream_output():
    """测试流式输出"""
    print("=" * 60)
    print("测试火山引擎流式输出")
    print("=" * 60)
    print()
    
    # 初始化 LLM Provider
    provider = get_llm_provider()
    
    # 简单的测试 prompt
    prompt = """请简要介绍一下什么是错题本，以及如何有效使用错题本。
    
要求：
- 分 3-4 段回答
- 每段 2-3 句话
- 使用 Markdown 格式
- 包含 emoji
"""
    
    print("开始流式生成...\n")
    print("-" * 60)
    
    # 调用流式 API
    stream_response = await provider.chat(
        prompt=prompt,
        temperature=0.7,
        max_tokens=1000,
        stream=True
    )
    
    # 处理流式响应
    accumulated_content = ''
    chunk_count = 0
    
    try:
        with stream_response:
            for chunk in stream_response:
                chunk_count += 1
                
                # 提取增量内容
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                        accumulated_content += delta.content
                        # 实时打印（不换行）
                        print(delta.content, end='', flush=True)
        
        print("\n")
        print("-" * 60)
        print(f"\n✅ 流式输出完成！")
        print(f"   - 接收到 {chunk_count} 个 chunk")
        print(f"   - 总内容长度: {len(accumulated_content)} 字符")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n\n❌ 流式输出失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_update_frequency():
    """测试 0.5 秒更新频率"""
    print("=" * 60)
    print("测试 0.5 秒更新频率")
    print("=" * 60)
    print()
    
    provider = get_llm_provider()
    
    prompt = """请写一篇 200 字左右的短文，主题是：学习的意义。

要求：
- 分段描述
- 使用 Markdown 格式
"""
    
    print("开始流式生成（模拟数据库更新）...\n")
    print("-" * 60)
    
    stream_response = await provider.chat(
        prompt=prompt,
        temperature=0.7,
        max_tokens=500,
        stream=True
    )
    
    accumulated_content = ''
    last_update_time = asyncio.get_event_loop().time()
    update_interval = 0.5  # 0.5 秒更新一次
    update_count = 0
    
    try:
        with stream_response:
            for chunk in stream_response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content is not None:
                        accumulated_content += delta.content
                        print(delta.content, end='', flush=True)
                        
                        # 检查是否需要"更新数据库"
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_update_time >= update_interval:
                            update_count += 1
                            print(f"\n[📝 模拟数据库更新 #{update_count}，内容长度: {len(accumulated_content)}]", end='')
                            last_update_time = current_time
        
        # 最后一次更新
        update_count += 1
        print(f"\n[📝 模拟数据库更新 #{update_count}（最终），内容长度: {len(accumulated_content)}]")
        
        print("\n")
        print("-" * 60)
        print(f"\n✅ 测试完成！")
        print(f"   - 总共 {update_count} 次数据库更新")
        print(f"   - 平均更新间隔: {update_interval} 秒")
        print(f"   - 最终内容长度: {len(accumulated_content)} 字符")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print()
    print("🧪 开始测试流式输出功能")
    print()
    
    # 测试 1: 基本流式输出
    result1 = await test_stream_output()
    
    if result1:
        # 测试 2: 更新频率
        await asyncio.sleep(2)  # 间隔一下
        result2 = await test_update_frequency()
        
        if result2:
            print()
            print("=" * 60)
            print("🎉 所有测试通过！")
            print("=" * 60)
            print()
            print("说明：")
            print("  - 流式输出功能正常")
            print("  - 0.5 秒更新频率合理")
            print("  - 可以应用到生产环境")
            print()
        else:
            print("\n⚠️ 部分测试失败")
    else:
        print("\n⚠️ 基本测试失败，跳过后续测试")


if __name__ == '__main__':
    # 检查环境变量
    required_vars = ['DOUBAO_API_KEY', 'DOUBAO_MODEL']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ 缺少必需的环境变量: {', '.join(missing_vars)}")
        print()
        print("请设置以下环境变量：")
        print("  export DOUBAO_API_KEY='your_api_key'")
        print("  export DOUBAO_MODEL='your_model_endpoint_id'")
        print()
        sys.exit(1)
    
    # 运行测试
    asyncio.run(main())


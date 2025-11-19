import json
import os
import sys
import asyncio

# 添加当前目录到 Python 路径，确保可以导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_provider import get_llm_provider

# Appwrite Function Entrypoint
async def main(context):
    """
    AI Helper Function
    
    Supported actions:
    - polish_note: Polish a user's note/remark.
    """
    
    # Initialize response
    if context.req.method == 'OPTIONS':
        return context.res.send('', 200, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        })

    try:
        # Parse request body
        body = json.loads(context.req.body)
        action = body.get('action')
        
        if action == 'polish_note':
            return await handle_polish_note(context, body)
        else:
            return context.res.json({
                'error': 'Invalid action'
            }, 400)
            
    except Exception as e:
        context.error(f"Error: {str(e)}")
        return context.res.json({
            'error': str(e)
        }, 500)

async def handle_polish_note(context, body):
    note = body.get('note')
    if not note:
        return context.res.json({'error': 'Note content is required'}, 400)
        
    try:
        provider = get_llm_provider()
        
        prompt = f"""
请帮我润色以下错题笔记，使其更加简洁、清晰，并总结成一句话。
保留核心信息，去除冗余词汇。

原始笔记：
{note}

润色后的笔记（仅输出润色后的内容，不要包含其他解释）：
"""
        
        polished_note = await provider.chat(prompt)
        
        # Clean up response (remove quotes if any)
        polished_note = polished_note.strip().strip('"').strip("'")
        
        return context.res.json({
            'original': note,
            'polished': polished_note
        })
        
    except Exception as e:
        context.error(f"LLM Error: {str(e)}")
        return context.res.json({'error': 'Failed to polish note'}, 500)


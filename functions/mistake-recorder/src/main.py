"""
L1: mistake-recorder
错题记录器 - 处理特殊的错题创建业务逻辑

⚠️ 新架构说明:
- 拍照错题: Flutter 上传图片到 bucket -> 创建 mistake_record (analysisStatus: "pending") -> mistake-analyzer 自动触发分析
- 重新分析: Flutter 更新 analysisStatus 为 "pending" -> mistake-analyzer 自动触发分析
- 练习错题: 调用本函数的 createFromQuestion 接口

本函数提供的接口:
1. createFromQuestion - 从已有题目创建错题记录（练习中做错的题目）

注意：简单的 CRUD 操作由 Flutter 端直接通过 Appwrite SDK 操作数据库
"""
import os
import json
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.id import ID

from mistake_service import create_mistake_record
from knowledge_point_service import ensure_knowledge_point
from utils import success_response, error_response, parse_request_body, get_user_id


# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
STORAGE_BUCKET_ID = os.environ.get('APPWRITE_STORAGE_BUCKET_ID', 'mistake-images')


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def get_storage() -> Storage:
    """Initialize Storage service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Storage(client)


def handle_create_from_question(body: dict, user_id: str) -> dict:
    """
    从已有题目创建错题记录
    适用于练习中做错的题目
    
    直接写入数据库，只返回ID
    """
    databases = get_databases()
    
    question_id = body.get('questionId')
    error_reason = body.get('errorReason', 'conceptError')
    user_answer = body.get('userAnswer')
    note = body.get('note')
    
    if not question_id:
        raise ValueError("需要提供 questionId")
    
    # 1. 获取题目信息
    from appwrite.query import Query
    question = databases.get_document(
        database_id=DATABASE_ID,
        collection_id='questions',
        document_id=question_id
    )
    
    # 2. 从题目中获取模块和知识点信息
    question_module_ids = question.get('moduleIds', [])
    question_kp_ids = question.get('knowledgePointIds', [])
    
    if not question_module_ids:
        raise ValueError("题目缺少模块信息")
    if not question_kp_ids:
        raise ValueError("题目缺少知识点信息")
    
    # 2.1 获取模块信息（模块是公有的，直接使用）
    # 验证模块是否存在
    module_ids = []
    for module_id in question_module_ids:
        try:
            module = databases.get_document(
                database_id=DATABASE_ID,
                collection_id='knowledge_points_library',
                document_id=module_id
            )
            module_ids.append(module_id)
        except Exception as e:
            print(f"获取模块失败: {str(e)}")
            continue
    
    if not module_ids:
        raise ValueError("无法获取题目的模块信息")
    
    # 2.2 获取所有知识点的详细信息（确保用户有这些知识点）
    user_kp_ids = []
    
    for kp_id in question_kp_ids:
        try:
            # 获取知识点信息
            kp = databases.get_document(
                database_id=DATABASE_ID,
                collection_id='user_knowledge_points',
                document_id=kp_id
            )
            
            # 如果是其他用户的知识点，需要为当前用户创建
            if kp.get('userId') != user_id:
                # 为当前用户创建知识点（关联到同一个模块）
                user_kp = ensure_knowledge_point(
                    databases=databases,
                    user_id=user_id,
                    subject=question['subject'],
                    module_id=kp['moduleId'],  # 使用原知识点的模块ID
                    knowledge_point_name=kp['name']
                )
                user_kp_ids.append(user_kp['$id'])
            else:
                user_kp_ids.append(kp_id)
                
        except Exception as e:
            print(f"获取知识点失败: {str(e)}")
            continue
    
    if not user_kp_ids:
        raise ValueError("无法获取题目的知识点信息")
    
    # 3. 创建错题记录（三级结构）
    mistake_record = create_mistake_record(
        databases=databases,
        user_id=user_id,
        question_id=question_id,
        module_ids=module_ids,              # 模块ID数组
        knowledge_point_ids=user_kp_ids,    # 知识点ID数组
        subject=question['subject'],
        error_reason=error_reason,
        user_answer=user_answer,
        note=note,
        original_image_urls=[]
    )
    
    # 只返回ID
    return {
        'mistakeId': mistake_record['$id'],
        'questionId': question_id,
        'moduleIds': module_ids,
        'knowledgePointIds': user_kp_ids
    }


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        action = body.get('action', 'uploadMistake')
        
        # 获取用户ID
        user_id = get_user_id(req)
        if not user_id:
            return res.json(error_response("未授权：需要用户登录", 401))
        
        # 路由到不同的处理函数
        if action == 'createFromQuestion':
            # 从已有题目创建错题记录
            result = handle_create_from_question(body, user_id)
            return res.json(success_response(result, "错题记录创建成功"))
            
        else:
            return res.json(error_response(f"未知操作: {action}。简单的 CRUD 操作请直接使用 Appwrite SDK"))
            
    except ValueError as e:
        return res.json(error_response(str(e), 400))
    except Exception as e:
        context.log(f"Error: {str(e)}")
        return res.json(error_response(f"服务器错误: {str(e)}", 500))

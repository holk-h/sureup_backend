"""
掌握度聚合器 - 监听 review_states 更新，自动计算知识点、模块和学科级别的掌握度

触发时机：当 review_states 表的记录被更新时（用户完成每日任务后）

功能：
1. 更新该知识点在 user_knowledge_points 表的 masteryScore
2. 计算该知识点所属模块的平均掌握度
3. 计算该知识点所属学科的平均掌握度
4. 更新用户 profiles 表的 subjectMasteryScores（JSON格式）
"""

import os
import json
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query


# 环境配置
APPWRITE_ENDPOINT = os.environ.get('APPWRITE_FUNCTION_API_ENDPOINT', 'https://api.delvetech.cn/v1')
APPWRITE_PROJECT_ID = os.environ.get('APPWRITE_FUNCTION_PROJECT_ID')
APPWRITE_API_KEY = os.environ.get('APPWRITE_API_KEY')
DATABASE_ID = 'main'


def main(context):
    """
    主函数：处理 review_states 创建/更新事件
    """
    try:
        # 解析事件数据 - context.req.body 在事件触发器中已经是字典对象
        event_data = context.req.body if isinstance(context.req.body, dict) else {}
        context.log(f"📥 收到事件: {event_data}")
        
        # 获取更新的 review_state 数据
        user_id = event_data.get('userId')
        knowledge_point_id = event_data.get('knowledgePointId')
        mastery_score = event_data.get('masteryScore', 0)
        
        if not user_id or not knowledge_point_id:
            context.log("⚠️ 缺少必要参数")
            return context.res.json({
                'success': False,
                'message': '缺少必要参数'
            })
        
        context.log(f"✓ 用户: {user_id}, 知识点: {knowledge_point_id}, 掌握度: {mastery_score}")
        
        # 初始化 Appwrite 客户端
        client = Client()
        client.set_endpoint(APPWRITE_ENDPOINT)
        client.set_project(APPWRITE_PROJECT_ID)
        client.set_key(APPWRITE_API_KEY)
        
        databases = Databases(client)
        
        # 1. 更新知识点的 masteryScore
        update_knowledge_point_mastery(
            databases,
            user_id,
            knowledge_point_id,
            mastery_score,
            context
        )
        
        # 2. 聚合计算模块和学科掌握度
        aggregate_mastery_scores(
            databases,
            user_id,
            knowledge_point_id,
            context
        )
        
        return context.res.json({
            'success': True,
            'message': '掌握度聚合完成'
        })
        
    except Exception as e:
        context.error(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return context.res.json({
            'success': False,
            'message': f'处理失败: {str(e)}'
        }, 500)


def update_knowledge_point_mastery(
    databases: Databases,
    user_id: str,
    knowledge_point_id: str,
    mastery_score: int,
    context
):
    """
    更新 user_knowledge_points 表的 masteryScore 字段
    """
    try:
        context.log(f"🔄 更新知识点掌握度: {knowledge_point_id} -> {mastery_score}")
        
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id='user_knowledge_points',
            document_id=knowledge_point_id,
            data={
                'masteryScore': mastery_score
            }
        )
        
        context.log(f"✓ 知识点掌握度已更新")
        
    except Exception as e:
        context.log(f"⚠️ 更新知识点掌握度失败: {str(e)}")


def aggregate_mastery_scores(
    databases: Databases,
    user_id: str,
    knowledge_point_id: str,
    context
):
    """
    聚合计算模块和学科级别的掌握度
    """
    try:
        # 1. 获取该知识点的详细信息（获取 moduleId 和 subject）
        kp = databases.get_document(
            database_id=DATABASE_ID,
            collection_id='user_knowledge_points',
            document_id=knowledge_point_id
        )
        
        module_id = kp.get('moduleId')
        subject = kp.get('subject')
        
        context.log(f"✓ 知识点所属 - 模块: {module_id}, 学科: {subject}")
        
        # 2. 查询该用户该学科的所有知识点和它们的 review_states
        subject_kps = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='user_knowledge_points',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('subject', subject),
                Query.limit(500)
            ]
        )
        
        # 3. 获取所有知识点的 masteryScore（从 review_states）
        kp_ids = [kp['$id'] for kp in subject_kps['documents']]
        
        # 批量查询 review_states
        review_states_map = {}
        for kp_id in kp_ids:
            try:
                rs_list = databases.list_documents(
                    database_id=DATABASE_ID,
                    collection_id='review_states',
                    queries=[
                        Query.equal('userId', user_id),
                        Query.equal('knowledgePointId', kp_id),
                        Query.limit(1)
                    ]
                )
                
                if rs_list['documents']:
                    review_states_map[kp_id] = rs_list['documents'][0].get('masteryScore', 0)
            except Exception as e:
                context.log(f"⚠️ 查询 review_state 失败: {kp_id} - {str(e)}")
                continue
        
        context.log(f"✓ 查询到 {len(review_states_map)} 个知识点的复习状态")
        
        # 4. 计算学科平均掌握度（只统计有 review_states 的知识点）
        if review_states_map:
            subject_avg_mastery = sum(review_states_map.values()) / len(review_states_map)
            subject_avg_mastery = round(subject_avg_mastery)
            
            context.log(f"✓ 学科 {subject} 平均掌握度: {subject_avg_mastery}")
            
            # 5. 更新用户 profiles 表的 subjectMasteryScores
            update_user_subject_mastery(
                databases,
                user_id,
                subject,
                subject_avg_mastery,
                context
            )
        else:
            context.log(f"⚠️ 学科 {subject} 没有有效的复习状态数据")
        
    except Exception as e:
        context.log(f"⚠️ 聚合掌握度失败: {str(e)}")
        import traceback
        traceback.print_exc()


def update_user_subject_mastery(
    databases: Databases,
    user_id: str,
    subject: str,
    avg_mastery: int,
    context
):
    """
    更新用户 profiles 表的 subjectMasteryScores 字段
    
    格式: {"数学": 75, "物理": 60, "化学": 80}
    """
    try:
        # 1. 获取当前用户档案
        profiles = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if not profiles['documents']:
            context.log(f"⚠️ 用户档案不存在: {user_id}")
            return
        
        profile = profiles['documents'][0]
        profile_id = profile['$id']
        
        # 2. 解析现有的 subjectMasteryScores
        subject_scores_str = profile.get('subjectMasteryScores')
        
        if subject_scores_str:
            try:
                subject_scores = json.loads(subject_scores_str)
            except:
                subject_scores = {}
        else:
            subject_scores = {}
        
        # 3. 更新该学科的掌握度
        subject_scores[subject] = avg_mastery
        
        # 4. 保存回数据库
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id='profiles',
            document_id=profile_id,
            data={
                'subjectMasteryScores': json.dumps(subject_scores, ensure_ascii=False)
            }
        )
        
        context.log(f"✓ 用户学科掌握度已更新: {subject} -> {avg_mastery}")
        context.log(f"✓ 所有学科掌握度: {subject_scores}")
        
    except Exception as e:
        context.log(f"⚠️ 更新用户学科掌握度失败: {str(e)}")
        import traceback
        traceback.print_exc()


#!/usr/bin/env python3
"""
稳了！数据库初始化脚本

使用Appwrite Server SDK初始化数据库结构
运行前请确保：
1. 已安装 appwrite: pip install appwrite
2. 配置了正确的 APPWRITE_ENDPOINT 和 APPWRITE_API_KEY
"""

import os
import sys
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.id import ID
from appwrite.permission import Permission
from appwrite.role import Role

# ============================================================================
# 配置
# ============================================================================

APPWRITE_ENDPOINT = os.getenv('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1')
APPWRITE_PROJECT_ID = os.getenv('APPWRITE_PROJECT_ID', '')
APPWRITE_API_KEY = os.getenv('APPWRITE_API_KEY', '')

DATABASE_ID = 'main'
DATABASE_NAME = '稳了！主数据库'

# Collection列表（v2.0设计）
COLLECTIONS = [
    'profiles',
    'user_knowledge_points',
    'knowledge_points_library',
    'questions',
    'mistake_records',
    'practice_sessions',
    'practice_answers',
    'question_feedbacks',
    'weekly_reports',
    'daily_tasks',
]

# ============================================================================
# 初始化客户端
# ============================================================================

def init_client():
    """初始化Appwrite客户端"""
    if not APPWRITE_PROJECT_ID or not APPWRITE_API_KEY:
        print("❌ 错误：请设置环境变量 APPWRITE_PROJECT_ID 和 APPWRITE_API_KEY")
        sys.exit(1)
    
    client = Client()
    client.set_endpoint(APPWRITE_ENDPOINT)
    client.set_project(APPWRITE_PROJECT_ID)
    client.set_key(APPWRITE_API_KEY)
    
    return client

# ============================================================================
# 数据库创建
# ============================================================================

def create_database(databases: Databases):
    """创建数据库"""
    try:
        db = databases.create(
            database_id=DATABASE_ID,
            name=DATABASE_NAME
        )
        print(f"✅ 数据库创建成功: {db['name']}")
        return db
    except Exception as e:
        if 'already exists' in str(e).lower():
            print(f"ℹ️  数据库已存在: {DATABASE_NAME}")
        else:
            print(f"❌ 数据库创建失败: {e}")
            raise

# ============================================================================
# Collection 创建函数
# ============================================================================

def create_profiles_collection(databases: Databases):
    """创建 profiles（用户档案）集合"""
    collection_id = 'profiles'
    collection_name = '用户档案'
    
    try:
        # 创建集合
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'name', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'avatar', 2000, required=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'grade', required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'focusSubjects', 2000, required=False, array=True)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalMistakes', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'masteredMistakes', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalPracticeSessions', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'continuousDays', required=False, default=0)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'lastActiveAt', required=False)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_unique', 'unique', ['userId'])
        databases.create_index(DATABASE_ID, collection_id, 'grade_idx', 'key', ['grade'])
        databases.create_index(DATABASE_ID, collection_id, 'lastActiveAt_idx', 'key', ['lastActiveAt'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_user_knowledge_points_collection(databases: Databases):
    """创建 user_knowledge_points（用户知识点树）集合"""
    collection_id = 'user_knowledge_points'
    collection_name = '用户知识点树'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subject', 20, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'name', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'parentId', 36, required=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'level', required=False, default=1)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'description', 500, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'color', 20, required=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'mistakeCount', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'masteredCount', required=False, default=0)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'lastMistakeAt', required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'createdFrom', 20, required=False, default='ai')
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_subject_idx', 'key', ['userId', 'subject'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_parentId_idx', 'key', ['userId', 'parentId'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_name_idx', 'key', ['userId', 'name'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_lastMistake_idx', 'key', ['userId', 'lastMistakeAt'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_knowledge_points_library_collection(databases: Databases):
    """创建 knowledge_points_library（全局知识点库）集合"""
    collection_id = 'knowledge_points_library'
    collection_name = '全局知识点库'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=False
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subject', 20, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'name', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'parentId', 36, required=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'level', required=False, default=1)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'description', 500, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'aliases', 2000, required=False, array=True)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'usageCount', required=False, default=0)
        databases.create_boolean_attribute(DATABASE_ID, collection_id, 'isVerified', required=False, default=False)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'subject_level_idx', 'key', ['subject', 'level'])
        databases.create_index(DATABASE_ID, collection_id, 'subject_name_idx', 'key', ['subject', 'name'])
        databases.create_index(DATABASE_ID, collection_id, 'name_fulltext', 'fulltext', ['name'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_questions_collection(databases: Databases):
    """创建 questions（题目库）集合"""
    collection_id = 'questions'
    collection_name = '题目库'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subject', 20, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'knowledgePointId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'knowledgePointName', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'type', 20, required=True)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'difficulty', required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'content', 5000, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'options', 2000, required=False, array=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'answer', 1000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'explanation', 5000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'imageIds', 2000, required=False, array=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'source', 20, required=False, default='ocr')
        databases.create_string_attribute(DATABASE_ID, collection_id, 'createdBy', 36, required=False)
        databases.create_boolean_attribute(DATABASE_ID, collection_id, 'isPublic', required=False, default=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'feedbackCount', required=False, default=0)
        databases.create_float_attribute(DATABASE_ID, collection_id, 'qualityScore', required=False, default=5.0)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'subject_kp_idx', 'key', ['subject', 'knowledgePointId'])
        databases.create_index(DATABASE_ID, collection_id, 'createdBy_idx', 'key', ['createdBy'])
        databases.create_index(DATABASE_ID, collection_id, 'isPublic_idx', 'key', ['isPublic'])
        databases.create_index(DATABASE_ID, collection_id, 'content_fulltext', 'fulltext', ['content'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_mistake_records_collection(databases: Databases):
    """创建 mistake_records（错题记录）集合"""
    collection_id = 'mistake_records'
    collection_name = '错题记录'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'questionId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userKnowledgePointId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subject', 20, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'knowledgePointName', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'errorReason', 30, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'note', 1000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userAnswer', 1000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'masteryStatus', 20, required=False, default='notStarted')
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'reviewCount', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'correctCount', required=False, default=0)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'originalImageUrls', 2000, required=False, array=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'lastReviewAt', required=False)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'masteredAt', required=False)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_createdAt_idx', 'key', ['userId', '$createdAt'], orders=['ASC', 'DESC'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_subject_idx', 'key', ['userId', 'subject'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_kpId_idx', 'key', ['userId', 'userKnowledgePointId'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_status_idx', 'key', ['userId', 'masteryStatus'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_lastReview_idx', 'key', ['userId', 'lastReviewAt'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_practice_sessions_collection(databases: Databases):
    """创建 practice_sessions（练习会话）集合"""
    collection_id = 'practice_sessions'
    collection_name = '练习会话'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'type', 30, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subject', 20, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userKnowledgePointId', 36, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'title', 100, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'subtitle', 200, required=False)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalQuestions', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'completedQuestions', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'correctQuestions', required=False, default=0)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'startedAt', required=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'completedAt', required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'status', 20, required=False, default='in_progress')
        databases.create_string_attribute(DATABASE_ID, collection_id, 'aiSummary', 1000, required=False)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_startedAt_idx', 'key', ['userId', 'startedAt'], orders=['ASC', 'DESC'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_status_idx', 'key', ['userId', 'status'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_type_idx', 'key', ['userId', 'type'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_practice_answers_collection(databases: Databases):
    """创建 practice_answers（答题记录）集合"""
    collection_id = 'practice_answers'
    collection_name = '答题记录'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'sessionId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'questionId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'mistakeRecordId', 36, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userAnswer', 1000, required=False)
        databases.create_boolean_attribute(DATABASE_ID, collection_id, 'isCorrect', required=True)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'timeSpent', required=False, default=0)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'answeredAt', required=True)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'sessionId_idx', 'key', ['sessionId'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_answeredAt_idx', 'key', ['userId', 'answeredAt'])
        databases.create_index(DATABASE_ID, collection_id, 'mistakeRecordId_idx', 'key', ['mistakeRecordId'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_question_feedbacks_collection(databases: Databases):
    """创建 question_feedbacks（题目反馈）集合"""
    collection_id = 'question_feedbacks'
    collection_name = '题目反馈'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'questionId', 36, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'feedbackType', 30, required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'description', 1000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'suggestedFix', 1000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'status', 20, required=False, default='pending')
        databases.create_string_attribute(DATABASE_ID, collection_id, 'resolvedBy', 36, required=False)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'resolvedAt', required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'resolution', 500, required=False)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'questionId_idx', 'key', ['questionId'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_createdAt_idx', 'key', ['userId', '$createdAt'])
        databases.create_index(DATABASE_ID, collection_id, 'status_idx', 'key', ['status'])
        databases.create_index(DATABASE_ID, collection_id, 'feedbackType_idx', 'key', ['feedbackType'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_weekly_reports_collection(databases: Databases):
    """创建 weekly_reports（周报）集合"""
    collection_id = 'weekly_reports'
    collection_name = '周报'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'weekStart', required=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'weekEnd', required=True)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalMistakes', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalReviews', required=False, default=0)
        databases.create_integer_attribute(DATABASE_ID, collection_id, 'totalPracticeSessions', required=False, default=0)
        databases.create_float_attribute(DATABASE_ID, collection_id, 'practiceCompletionRate', required=False, default=0.0)
        databases.create_float_attribute(DATABASE_ID, collection_id, 'overallAccuracy', required=False, default=0.0)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'topMistakePoints', 5000, required=False)  # JSON string
        databases.create_string_attribute(DATABASE_ID, collection_id, 'errorReasonDistribution', 2000, required=False)  # JSON string
        databases.create_string_attribute(DATABASE_ID, collection_id, 'aiSummary', 2000, required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'suggestions', 2000, required=False, array=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'generatedAt', required=True)
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_weekStart_idx', 'unique', ['userId', 'weekStart'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")


def create_daily_tasks_collection(databases: Databases):
    """创建 daily_tasks（每日任务）集合"""
    collection_id = 'daily_tasks'
    collection_name = '每日任务'
    
    try:
        collection = databases.create_collection(
            database_id=DATABASE_ID,
            collection_id=collection_id,
            name=collection_name,
            permissions=[
                Permission.read(Role.any()),
            ],
            document_security=True
        )
        print(f"✅ 集合创建成功: {collection_name}")
        
        # 创建属性
        databases.create_string_attribute(DATABASE_ID, collection_id, 'userId', 36, required=True)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'taskDate', required=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'questionIds', 2000, required=True, array=True)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'taskType', 30, required=True)
        databases.create_boolean_attribute(DATABASE_ID, collection_id, 'isCompleted', required=False, default=False)
        databases.create_datetime_attribute(DATABASE_ID, collection_id, 'completedAt', required=False)
        databases.create_string_attribute(DATABASE_ID, collection_id, 'metadata', 2000, required=False)  # JSON string
        print(f"  ✅ 属性创建完成")
        
        # 创建索引
        databases.create_index(DATABASE_ID, collection_id, 'userId_taskDate_idx', 'unique', ['userId', 'taskDate'])
        databases.create_index(DATABASE_ID, collection_id, 'userId_completed_idx', 'key', ['userId', 'isCompleted'])
        print(f"  ✅ 索引创建完成")
        
    except Exception as e:
        print(f"❌ 创建 {collection_name} 失败: {e}")

# ============================================================================
# Storage Buckets 创建
# ============================================================================

def create_storage_buckets(storage: Storage):
    """创建存储桶"""
    
    # 1. 错题拍照原图
    try:
        bucket = storage.create_bucket(
            bucket_id='mistake-images',
            name='错题拍照原图',
            permissions=[
                Permission.read(Role.any()),
            ],
            file_security=True,
            enabled=True,
            maximum_file_size=10485760,  # 10MB
            allowed_file_extensions=[],
            compression='gzip',
            encryption=True,
            antivirus=True
        )
        print(f"✅ 存储桶创建成功: 错题拍照原图")
    except Exception as e:
        if 'already exists' in str(e).lower():
            print(f"ℹ️  存储桶已存在: 错题拍照原图")
        else:
            print(f"❌ 创建存储桶失败: {e}")
    
    # 2. 题目图片
    try:
        bucket = storage.create_bucket(
            bucket_id='question-images',
            name='题目图片',
            permissions=[
                Permission.read(Role.any()),
            ],
            file_security=False,
            enabled=True,
            maximum_file_size=5242880,  # 5MB
            allowed_file_extensions=[],
            compression='gzip',
            encryption=True,
            antivirus=True
        )
        print(f"✅ 存储桶创建成功: 题目图片")
    except Exception as e:
        if 'already exists' in str(e).lower():
            print(f"ℹ️  存储桶已存在: 题目图片")
        else:
            print(f"❌ 创建存储桶失败: {e}")

# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    print("\n" + "="*60)
    print("稳了！数据库初始化脚本")
    print("="*60 + "\n")
    
    # 初始化客户端
    print("📡 连接到 Appwrite...")
    client = init_client()
    databases = Databases(client)
    storage = Storage(client)
    print("✅ 连接成功\n")
    
    # 创建数据库
    print("📂 创建数据库...")
    create_database(databases)
    print()
    
    # 创建集合
    print("📋 创建集合...\n")
    
    collections = [
        ("1/10", create_profiles_collection),
        ("2/10", create_user_knowledge_points_collection),
        ("3/10", create_knowledge_points_library_collection),
        ("4/10", create_questions_collection),
        ("5/10", create_mistake_records_collection),
        ("6/10", create_practice_sessions_collection),
        ("7/10", create_practice_answers_collection),
        ("8/10", create_question_feedbacks_collection),
        ("9/10", create_weekly_reports_collection),
        ("10/10", create_daily_tasks_collection),
    ]
    
    for progress, create_func in collections:
        print(f"[{progress}] ", end="")
        create_func(databases)
        print()
    
    # 创建存储桶
    print("🗂️  创建存储桶...\n")
    create_storage_buckets(storage)
    print()
    
    # 完成
    print("="*60)
    print("✅ 数据库初始化完成！")
    print("="*60)
    print("\n📝 提示：")
    print("  1. 请在 Appwrite Console 中配置 Collection 权限")
    print("  2. 建议预置一些常见知识点数据")
    print("  3. 可以开始开发云函数和前端集成了\n")


if __name__ == '__main__':
    main()


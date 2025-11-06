"""
知识点服务模块
负责学科模块和用户知识点的创建和管理

新的三级结构：
- 学科 (subject): 如数学、物理
- 模块 (module): 公有的学科模块，存储在 knowledge_points_library
- 知识点 (knowledge_point): 用户私有的知识点，存储在 user_knowledge_points，关联 moduleId
"""
import os
from typing import Dict, Optional
from datetime import datetime, date
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_USER_KP = 'user_knowledge_points'
COLLECTION_MODULES = 'knowledge_points_library'  # 改为模块库
COLLECTION_REVIEW_STATES = 'review_states'


def ensure_knowledge_point(
    databases: Databases,
    user_id: str,
    subject: str,
    module_id: str,
    knowledge_point_name: str,
    description: Optional[str] = None,
    importance: str = 'normal'
) -> Dict:
    """
    确保用户知识点存在
    
    策略：
    1. 先在用户知识点中查找（同一用户、同一模块、同一名称）
    2. 如果不存在，创建新的用户知识点
    3. 如果已存在但 importance 不同，更新 importance
    4. 确保有对应的复习状态记录
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        subject: 学科
        module_id: 模块ID（来自 knowledge_points_library）
        knowledge_point_name: 知识点名称
        description: 描述（可选）
        importance: 重要程度 (high/basic/normal)，默认 'normal'
    """
    
    # 1. 查找是否已存在
    existing = find_user_knowledge_point(
        databases=databases,
        user_id=user_id,
        module_id=module_id,
        name=knowledge_point_name
    )
    
    if existing:
        # 确保已存在的知识点也有复习状态（可能是旧数据）
        _ensure_review_state(databases, user_id, existing['$id'])
        
        # 如果 importance 不同，更新它（因为 LLM 可能重新评估了重要度）
        existing_importance = existing.get('importance', 'normal')
        if existing_importance != importance:
            print(f"更新知识点 '{knowledge_point_name}' 的重要度: {existing_importance} -> {importance}")
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_USER_KP,
                document_id=existing['$id'],
                data={'importance': importance}
            )
            existing['importance'] = importance
        
        return existing
    
    # 2. 创建新的用户知识点（内部会自动创建复习状态）
    return create_user_knowledge_point(
        databases=databases,
        user_id=user_id,
        subject=subject,
        module_id=module_id,
        name=knowledge_point_name,
        description=description,
        importance=importance
    )


def find_user_knowledge_point(
    databases: Databases,
    user_id: str,
    module_id: str,
    name: str
) -> Optional[Dict]:
    """
    在用户知识点中查找知识点（通过用户ID、模块ID和名称）
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.equal('name', name),
                Query.limit(1)
            ]
        )
        
        documents = docs.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"查找用户知识点失败: {str(e)}")
        return None


def find_module(
    databases: Databases,
    subject: str,
    name: str,
    education_level: Optional[str] = None
) -> Optional[Dict]:
    """
    在公有模块库中查找模块
    
    Args:
        databases: 数据库实例
        subject: 学科（英文代码如 'math'，会自动转换为中文）
        name: 模块名称
        education_level: 教育阶段（可选）
    """
    try:
        # 将学科英文代码转换为中文（数据库中存储的是中文）
        from workers.mistake_analyzer.utils import get_subject_chinese_name
        subject_chinese = get_subject_chinese_name(subject)
        
        queries = [
            Query.equal('subject', subject_chinese),
            Query.equal('name', name)
        ]
        
        # 如果指定了教育阶段，添加过滤
        if education_level:
            queries.append(Query.equal('educationLevel', education_level))
        
        queries.append(Query.limit(1))
        
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=queries
        )
        
        documents = docs.get('documents', [])
        return documents[0] if documents else None
        
    except Exception as e:
        print(f"查找模块失败: {str(e)}")
        return None


def ensure_module(
    databases: Databases,
    subject: str,
    module_name: str,
    user_id: str,
    description: Optional[str] = None
) -> Dict:
    """
    从现有模块中查找匹配的模块
    
    不创建新模块，只从 knowledge_points_library 中查找
    如果找不到，返回"未分类"模块作为兜底
    
    Args:
        databases: 数据库实例
        subject: 学科
        module_name: 模块名称
        user_id: 用户ID（用于确定学段）
        description: 描述（未使用，保留参数兼容性）
    
    Returns:
        找到的模块文档，如果找不到则返回"未分类"模块
    """
    # 获取用户学段信息
    from workers.mistake_analyzer.utils import get_user_profile, get_education_level_from_grade
    
    user_profile = get_user_profile(databases, user_id)
    user_grade = user_profile.get('grade') if user_profile else None
    education_level = get_education_level_from_grade(user_grade)
    
    # 1. 先查找用户学段对应的精确匹配模块
    existing = find_module(
        databases=databases,
        subject=subject,
        name=module_name,
        education_level=education_level
    )
    
    if existing:
        print(f"✓ 找到匹配模块: {module_name}（{subject}, {education_level}）")
        return existing
    
    # 2. 如果不存在，再查找其他学段的同名模块
    existing_any = find_module(
        databases=databases,
        subject=subject,
        name=module_name,
        education_level=None
    )
    
    if existing_any:
        print(f"⚠ 找到跨学段同名模块: {module_name}，学段为 {existing_any.get('educationLevel')}（用户学段: {education_level}）")
        return existing_any
    
    # 3. 都找不到，查找"未分类"模块作为兜底
    print(f"⚠ 未找到模块 '{module_name}'，使用'未分类'模块作为兜底")
    
    uncategorized = find_module(
        databases=databases,
        subject=subject,
        name='未分类',
        education_level=education_level
    )
    
    if uncategorized:
        print(f"✓ 使用未分类模块（{subject}, {education_level}）")
        return uncategorized
    
    # 4. 如果连"未分类"都没有，尝试不限学段查找
    uncategorized_any = find_module(
        databases=databases,
        subject=subject,
        name='未分类',
        education_level=None
    )
    
    if uncategorized_any:
        print(f"✓ 使用跨学段未分类模块（{subject}）")
        return uncategorized_any
    
    # 5. 理论上不应该到这里，因为应该有预设的"未分类"模块
    raise ValueError(f"错误：找不到学科 {subject} 的任何模块，包括'未分类'模块。请检查 knowledge_points_library 数据。")


def create_user_knowledge_point(
    databases: Databases,
    user_id: str,
    subject: str,
    module_id: str,
    name: str,
    description: Optional[str] = None,
    importance: str = 'normal'
) -> Dict:
    """
    创建用户知识点
    
    知识点是用户私有的，关联到公有的模块
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        subject: 学科
        module_id: 模块ID（来自 knowledge_points_library）
        name: 知识点名称
        description: 描述（可选）
        importance: 重要程度 (high/basic/normal)，默认 'normal'
    """
    kp_data = {
        'userId': user_id,
        'subject': subject,
        'moduleId': module_id,
        'name': name,
        'description': description or '',
        'importance': importance,
        'mistakeCount': 0,
        'masteredCount': 0,
        'lastMistakeAt': None
    }
    
    doc = databases.create_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KP,
        document_id=ID.unique(),
        data=kp_data
    )
    
    # 创建对应的复习状态记录
    _ensure_review_state(databases, user_id, doc['$id'])
    
    return doc


def add_question_to_knowledge_point(
    databases: Databases,
    kp_id: str,
    question_id: str
) -> Dict:
    """
    将题目ID添加到知识点的 questionIds 列表中
    
    Args:
        databases: 数据库实例
        kp_id: 知识点ID
        question_id: 题目ID
    
    Returns:
        更新后的知识点文档
    """
    try:
        # 获取现有知识点
        kp = databases.get_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            document_id=kp_id
        )
        
        # 获取现有的 questionIds 列表
        existing_question_ids = kp.get('questionIds', []) or []
        
        # 如果题目ID已存在，不重复添加
        if question_id in existing_question_ids:
            print(f"题目 {question_id} 已在知识点 {kp_id} 中")
            return kp
        
        # 添加新的题目ID
        updated_question_ids = existing_question_ids + [question_id]
        
        # 更新知识点
        doc = databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            document_id=kp_id,
            data={'questionIds': updated_question_ids}
        )
        
        print(f"✓ 已将题目 {question_id} 添加到知识点 {kp['name']}（总计 {len(updated_question_ids)} 道题）")
        return doc
        
    except Exception as e:
        print(f"添加题目到知识点失败: {str(e)}")
        raise


def update_knowledge_point_stats(
    databases: Databases,
    kp_id: str,
    mistake_count_delta: int = 0,
    mastered_count_delta: int = 0
) -> Dict:
    """
    更新知识点统计
    
    注意：
    - 这个函数目前未被使用，保留作为工具函数
    - 实际的统计更新由 stats-updater 函数通过数据库事件自动触发
    - stats-updater 是独立的 Appwrite Function，有自己的实现
    """
    kp = databases.get_document(
        database_id=DATABASE_ID,
        collection_id=COLLECTION_USER_KP,
        document_id=kp_id
    )
    
    update_data = {}
    
    if mistake_count_delta != 0:
        update_data['mistakeCount'] = max(0, kp.get('mistakeCount', 0) + mistake_count_delta)
    
    if mastered_count_delta != 0:
        update_data['masteredCount'] = max(0, kp.get('masteredCount', 0) + mastered_count_delta)
    
    if mistake_count_delta > 0:
        from datetime import datetime
        update_data['lastMistakeAt'] = datetime.utcnow().isoformat() + 'Z'
    
    if update_data:
        doc = databases.update_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            document_id=kp_id,
            data=update_data
        )
        return doc
    
    return kp


def get_modules_by_subject(
    databases: Databases,
    subject: str,
    education_level: Optional[str] = None
) -> list:
    """
    获取指定学科的所有模块
    
    Args:
        databases: 数据库实例
        subject: 学科（英文代码如 'math'，会自动转换为中文）
        education_level: 教育阶段（可选），如果指定则只返回对应学段的模块
    """
    try:
        # 将学科英文代码转换为中文（数据库中存储的是中文）
        from workers.mistake_analyzer.utils import get_subject_chinese_name
        subject_chinese = get_subject_chinese_name(subject)
        
        queries = [
            Query.equal('subject', subject_chinese),
            Query.equal('isActive', True)
        ]
        
        # 如果指定了教育阶段，添加过滤
        if education_level:
            queries.append(Query.equal('educationLevel', education_level))
        
        queries.extend([
            Query.order_asc('order'),
            Query.limit(100)
        ])
        
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MODULES,
            queries=queries
        )
        
        return docs.get('documents', [])
        
    except Exception as e:
        print(f"获取模块列表失败: {str(e)}")
        return []


def get_user_knowledge_points_by_module(
    databases: Databases,
    user_id: str,
    module_id: str
) -> list:
    """
    获取用户在指定模块下的所有知识点
    """
    try:
        docs = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_USER_KP,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('moduleId', module_id),
                Query.limit(100)
            ]
        )
        
        return docs.get('documents', [])
        
    except Exception as e:
        print(f"获取知识点列表失败: {str(e)}")
        return []


def _ensure_review_state(
    databases: Databases,
    user_id: str,
    knowledge_point_id: str
) -> Optional[Dict]:
    """
    确保知识点有对应的复习状态记录
    
    如果已存在则返回，不存在则创建新的复习状态记录
    
    Args:
        databases: 数据库实例
        user_id: 用户ID
        knowledge_point_id: 知识点ID
        
    Returns:
        复习状态记录文档，失败返回 None
    """
    try:
        # 1. 检查是否已存在
        existing = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_REVIEW_STATES,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('knowledgePointId', knowledge_point_id),
                Query.limit(1)
            ]
        )
        
        if existing['documents']:
            print(f"✓ 复习状态已存在: {knowledge_point_id}")
            return existing['documents'][0]
        
        # 2. 创建新的复习状态记录
        today = date.today().isoformat()
        
        review_state_data = {
            'userId': user_id,
            'knowledgePointId': knowledge_point_id,
            'status': 'newLearning',  # 新学习状态
            'masteryScore': 0,
            'currentInterval': 1,  # 1天后复习
            'nextReviewDate': today,  # 今天就可以复习（新错题）
            'lastReviewDate': None,
            'totalReviews': 0,
            'consecutiveCorrect': 0,
            'totalCorrect': 0,
            'totalWrong': 0,
            'isActive': True
        }
        
        doc = databases.create_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_REVIEW_STATES,
            document_id=ID.unique(),
            data=review_state_data
        )
        
        print(f"✓ 创建复习状态: {knowledge_point_id}，下次复习日期: {today}")
        return doc
        
    except Exception as e:
        print(f"⚠️ 创建复习状态失败: {str(e)}")
        return None


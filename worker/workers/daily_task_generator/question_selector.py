"""
题目选择模块
根据知识点状态选择合适的原题和变式题
"""
from typing import Dict, Any, List
from loguru import logger
from appwrite.services.databases import Databases
from appwrite.query import Query


def estimate_question_count(status: str, difficulty: str) -> int:
    """
    预估某知识点会推送多少题
    
    Args:
        status: 'newLearning' | 'reviewing' | 'mastered'
        difficulty: 'easy' | 'normal' | 'hard'
    
    Returns:
        预估题目数量
    """
    config = {
        'easy': {
            'newLearning': 1,
            'reviewing': 2,
            'mastered': 1
        },
        'normal': {
            'newLearning': 2,
            'reviewing': 3,
            'mastered': 2
        },
        'hard': {
            'newLearning': 2,
            'reviewing': 4,
            'mastered': 2
        }
    }
    
    return config.get(difficulty, {}).get(status, 2)


def get_question_limits(difficulty: str) -> tuple[int, int]:
    """
    获取题量范围
    
    Args:
        difficulty: 'easy' | 'normal' | 'hard'
    
    Returns:
        (min_questions, max_questions)
    """
    limits = {
        'easy': (3, 6),
        'normal': (6, 14),
        'hard': (10, 20)
    }
    
    return limits.get(difficulty, (6, 14))


def select_original_questions(
    mistakes: List[Dict[str, Any]],
    count: int,
    db: Databases,
    exclude_question_ids: set = None,
    knowledge_point_id: str = None
) -> List[Dict[str, Any]]:
    """
    从错题中选择原题
    
    新增逻辑：
    - 如果提供了 knowledge_point_id，优先选择该知识点为主要知识点的题目
    
    Args:
        mistakes: 错题记录列表
        count: 需要选择的数量
        db: 数据库服务
        exclude_question_ids: 需要排除的题目ID集合（避免重复）
        knowledge_point_id: 当前知识点ID（用于优先级排序）
        
    Returns:
        选中的题目列表（带 mistakeId）
    """
    if count <= 0:
        return []
    
    if exclude_question_ids is None:
        exclude_question_ids = set()
    
    # 按最近错误时间排序，选择最近的
    sorted_mistakes = sorted(
        mistakes,
        key=lambda m: m.get('$createdAt', ''),
        reverse=True
    )
    
    # 获取题目信息并计算优先级
    mistake_with_questions = []
    for mistake in sorted_mistakes:
        question_id = mistake.get('questionId')
        if not question_id or question_id in exclude_question_ids:
            continue
        
        try:
            question = db.get_document('main', 'questions', question_id)
            
            # 计算优先级分数
            priority_score = 0
            if knowledge_point_id:
                primary_kp_ids = question.get('primaryKnowledgePointIds', [])
                is_primary = knowledge_point_id in primary_kp_ids if primary_kp_ids else False
                priority_score = 100 if is_primary else 50
            
            mistake_with_questions.append({
                'mistake': mistake,
                'question': question,
                'priority_score': priority_score
            })
        except Exception as e:
            logger.warning(f"获取题目失败: {question_id}, 错误: {e}")
            continue
    
    # 按优先级排序（主要知识点题目在前，然后按时间排序）
    mistake_with_questions.sort(
        key=lambda x: (x['priority_score'], x['mistake'].get('$createdAt', '')),
        reverse=True
    )
    
    # 选择前 count 个
    selected = []
    for item in mistake_with_questions[:count]:
        selected.append({
            **item['question'],
            'mistakeId': item['mistake']['$id']
        })
    
    # 统计主要知识点题目数量
    if knowledge_point_id:
        primary_count = sum(
            1 for q in selected 
            if knowledge_point_id in q.get('primaryKnowledgePointIds', [])
        )
        logger.debug(
            f"原题选择：知识点 {knowledge_point_id} 选择了 {len(selected)} 道题，"
            f"其中 {primary_count} 道为主要知识点题目"
        )
    
    return selected


def select_variant_questions(
    kp_data: Dict[str, Any],
    count: int,
    db: Databases,
    exclude_question_ids: set = None
) -> List[Dict[str, Any]]:
    """
    选择变式题
    
    策略：
    - reviewing: 70%单知识点，30%轻度综合
    - mastered: 100%综合题
    
    Args:
        kp_data: 知识点数据（包含 review_state, user_kp, mistakes）
        count: 需要选择的数量
        db: 数据库服务
        exclude_question_ids: 需要排除的题目ID集合（避免跨知识点重复）
        
    Returns:
        选中的变式题列表
    """
    if count <= 0:
        return []
    
    if exclude_question_ids is None:
        exclude_question_ids = set()
    
    knowledge_point_id = kp_data['user_kp']['moduleId']
    status = kp_data['review_state']['status']
    
    # 计算单知识点和综合题数量
    if status == 'reviewing':
        single_count = int(count * 0.7)
        combined_count = count - single_count
    else:  # mastered
        single_count = 0
        combined_count = count
    
    selected = []
    
    # 1. 选择单知识点题目
    if single_count > 0:
        single_questions = _select_single_kp_questions(
            knowledge_point_id,
            single_count,
            kp_data['mistakes'],
            db,
            exclude_ids=exclude_question_ids
        )
        selected.extend(single_questions)
    
    # 2. 选择综合题（MVP阶段简化，也从同知识点题目池选择）
    if combined_count > 0:
        # 排除已选的题目（包括本轮已选 + 全局排除）
        local_selected_ids = {q['$id'] for q in selected}
        all_exclude_ids = exclude_question_ids | local_selected_ids
        
        combined_questions = _select_single_kp_questions(
            knowledge_point_id,
            combined_count,
            kp_data['mistakes'],
            db,
            exclude_ids=all_exclude_ids
        )
        selected.extend(combined_questions)
    
    return selected


def select_comprehensive_questions(
    kp_data: Dict[str, Any],
    count: int,
    db: Databases,
    exclude_question_ids: set = None
) -> List[Dict[str, Any]]:
    """
    选择综合题（mastered 阶段用）
    
    MVP阶段简化实现
    
    Args:
        kp_data: 知识点数据
        count: 需要选择的数量
        db: 数据库服务
        exclude_question_ids: 需要排除的题目ID集合
        
    Returns:
        选中的综合题列表
    """
    return select_variant_questions(kp_data, count, db, exclude_question_ids)


def _select_single_kp_questions(
    knowledge_point_id: str,
    count: int,
    mistakes: List[Dict[str, Any]],
    db: Databases,
    exclude_ids = None
) -> List[Dict[str, Any]]:
    """
    选择单知识点题目（内部函数）
    
    新增逻辑：
    - 优先选择该知识点为主要知识点的题目
    - 如果主要知识点题目不足，再选择普通关联题目
    
    Args:
        knowledge_point_id: 知识点ID
        count: 需要选择的数量
        mistakes: 用户错题记录（用于排除）
        db: 数据库服务
        exclude_ids: 需要排除的题目ID（可以是list或set）
        
    Returns:
        选中的题目列表
    """
    if exclude_ids is None:
        exclude_ids = set()
    elif isinstance(exclude_ids, list):
        exclude_ids = set(exclude_ids)
    
    try:
        # 使用更大的缓冲以应对题目去重和优先级排序
        query_limit = max(count * 8, 30)  # 增加缓冲量
        
        response = db.list_documents(
            'main',
            'questions',
            queries=[
                Query.contains('knowledgePointIds', knowledge_point_id),
                Query.equal('isPublic', True),
                Query.limit(query_limit)
            ]
        )
        
        questions = response['documents']
        
        # 获取用户已做过的题目ID
        mistake_q_ids = [m.get('questionId') for m in mistakes if m.get('questionId')]
        
        # 过滤：排除已做过的和已选择的
        filtered = [
            q for q in questions
            if q['$id'] not in mistake_q_ids and q['$id'] not in exclude_ids
        ]
        
        # 按主要知识点优先级排序
        def get_priority_score(question):
            """计算题目优先级分数"""
            primary_kp_ids = question.get('primaryKnowledgePointIds', [])
            is_primary = knowledge_point_id in primary_kp_ids if primary_kp_ids else False
            
            # 主要知识点题目优先级更高
            if is_primary:
                return 100
            else:
                return 50
        
        # 按优先级排序（主要知识点题目在前）
        filtered.sort(key=get_priority_score, reverse=True)
        
        # 取前 count 个
        selected = filtered[:count]
        
        # 统计主要知识点题目数量
        primary_count = sum(
            1 for q in selected 
            if knowledge_point_id in q.get('primaryKnowledgePointIds', [])
        )
        
        logger.debug(
            f"知识点 {knowledge_point_id} 选择了 {len(selected)} 道题，"
            f"其中 {primary_count} 道为主要知识点题目"
        )
        
        if len(selected) < count:
            logger.warning(
                f"知识点 {knowledge_point_id} 的变式题不足，"
                f"需要 {count} 道，实际找到 {len(selected)} 道 "
                f"(可能因题库不足或题目去重)"
            )
        
        return selected
        
    except Exception as e:
        logger.error(f"查询变式题失败: {e}")
        return []


def check_if_all_correct_last_time(mistakes: List[Dict[str, Any]]) -> bool:
    """
    检查上次复习是否全部答对
    
    Args:
        mistakes: 错题记录列表
        
    Returns:
        True 如果上次全对，False 如果有答错
    """
    # MVP阶段简化：只要 reviewCount > 0 且 masteryStatus 不是 'notStarted'，
    # 就认为已经复习过
    for mistake in mistakes:
        review_count = mistake.get('reviewCount', 0)
        correct_count = mistake.get('correctCount', 0)
        
        # 如果有复习过但正确次数少于复习次数，说明有错误
        if review_count > 0 and correct_count < review_count:
            return False
    
    return True


def select_wrong_questions(
    mistakes: List[Dict[str, Any]],
    count: int,
    db: Databases,
    exclude_question_ids: set = None,
    knowledge_point_id: str = None
) -> List[Dict[str, Any]]:
    """
    选择上次答错的题目
    
    Args:
        mistakes: 错题记录列表
        count: 需要选择的数量
        db: 数据库服务
        exclude_question_ids: 需要排除的题目ID集合
        knowledge_point_id: 当前知识点ID（用于优先级排序）
        
    Returns:
        选中的题目列表
    """
    if count <= 0:
        return []
    
    # 筛选出最近复习过但还没掌握的错题
    wrong_mistakes = [
        m for m in mistakes
        if m.get('reviewCount', 0) > 0
        and m.get('masteryStatus', 'notStarted') != 'mastered'
    ]
    
    # 按最近复习时间排序
    sorted_mistakes = sorted(
        wrong_mistakes,
        key=lambda m: m.get('lastReviewAt', ''),
        reverse=True
    )
    
    return select_original_questions(
        sorted_mistakes, 
        count, 
        db, 
        exclude_question_ids,
        knowledge_point_id
    )


"""
任务生成模块 - 核心业务逻辑
"""
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from loguru import logger
from appwrite.services.databases import Databases
from appwrite.query import Query

from .priority_calculator import calculate_priority
from .question_selector import (
    estimate_question_count,
    get_question_limits,
    select_original_questions,
    select_variant_questions,
    select_comprehensive_questions,
    select_wrong_questions,
    check_if_all_correct_last_time
)


def get_active_users(db: Databases) -> List[Dict[str, Any]]:
    """
    获取活跃用户列表
    活跃定义：最近7天内有活动
    
    Args:
        db: 数据库服务
        
    Returns:
        活跃用户列表
    """
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    try:
        response = db.list_documents(
            'main',
            'profiles',
            queries=[
                Query.greater_than('lastActiveAt', seven_days_ago),
                Query.limit(1000)  # 批量处理
            ]
        )
        
        return response['documents']
    except Exception as e:
        logger.error(f"获取活跃用户失败: {e}")
        return []


def select_knowledge_points(
    user_id: str,
    difficulty: str,
    db: Databases
) -> List[Dict[str, Any]]:
    """
    为用户选择今日需要复习的知识点
    
    Args:
        user_id: 用户ID
        difficulty: 难度设置 ('easy' | 'normal' | 'hard')
        db: 数据库服务
        
    Returns:
        选中的知识点列表（带优先级）
    """
    today = date.today().isoformat()
    
    # 1. 获取到期的知识点
    try:
        response = db.list_documents(
            'main',
            'review_states',
            queries=[
                Query.equal('userId', user_id),
                Query.less_than_equal('nextReviewDate', today),
                Query.equal('isActive', True),
                Query.limit(100)
            ]
        )
        
        review_states = response['documents']
    except Exception as e:
        logger.error(f"查询复习状态失败: {e}")
        return []
    
    if not review_states:
        logger.info(f"用户 {user_id} 没有到期的知识点")
        return []
    
    # 2. 为每个知识点计算优先级
    kp_with_priority = []
    
    for rs in review_states:
        knowledge_point_id = rs.get('knowledgePointId')
        if not knowledge_point_id:
            continue
        
        try:
            # 获取用户知识点信息
            user_kp = db.get_document('main', 'user_knowledge_points', knowledge_point_id)
            
            # 获取相关错题
            mistakes_response = db.list_documents(
                'main',
                'mistake_records',
                queries=[
                    Query.equal('userId', user_id),
                    Query.contains('knowledgePointIds', knowledge_point_id),
                    Query.not_equal('masteryStatus', 'mastered'),
                    Query.limit(50)
                ]
            )
            mistakes = mistakes_response['documents']
            
            # 获取知识点相关的题目（用于计算重要度）
            questions_response = db.list_documents(
                'main',
                'questions',
                queries=[
                    Query.contains('knowledgePointIds', knowledge_point_id),
                    Query.limit(20)
                ]
            )
            questions = questions_response['documents']
            
            # 计算优先级
            priority = calculate_priority(rs, user_kp, mistakes, questions)
            
            kp_with_priority.append({
                'review_state': rs,
                'user_kp': user_kp,
                'mistakes': mistakes,
                'priority': priority
            })
            
        except Exception as e:
            logger.error(f"处理知识点 {knowledge_point_id} 失败: {e}")
            continue
    
    if not kp_with_priority:
        return []
    
    # 3. 按优先级排序
    kp_with_priority.sort(key=lambda x: x['priority'], reverse=True)
    
    # 4. 动态选择知识点（根据题量上限）
    min_questions, max_questions = get_question_limits(difficulty)
    
    selected = []
    total_questions = 0
    
    for kp_data in kp_with_priority:
        status = kp_data['review_state'].get('status', 'newLearning')
        estimated = estimate_question_count(status, difficulty)
        
        # 如果加上这个知识点还在上限内，就选择它
        if total_questions + estimated <= max_questions:
            selected.append(kp_data)
            total_questions += estimated
        elif total_questions < min_questions:
            # 还没达到下限，继续添加
            selected.append(kp_data)
            total_questions += estimated
        else:
            # 已达到合适题量，停止添加
            break
    
    logger.info(
        f"用户 {user_id} 选择了 {len(selected)} 个知识点，"
        f"预估 {total_questions} 道题"
    )
    
    return selected


def generate_task_items(
    selected_kps: List[Dict[str, Any]],
    difficulty: str,
    db: Databases
) -> List[Dict[str, Any]]:
    """
    为选中的知识点生成任务项
    
    新策略：支持一题多知识点
    - 先为每个知识点独立选题（不排除重复）
    - 然后按题目ID分组，合并重复的题目
    - 一道题如果对应多个知识点，创建一个任务项关联所有知识点
    - 这样避免因去重导致某些知识点没有题目
    
    Args:
        selected_kps: 选中的知识点列表
        difficulty: 难度设置
        db: 数据库服务
        
    Returns:
        任务项列表（每项可能关联多个知识点）
    """
    # 第一步：为每个知识点独立选题
    kp_question_map = {}  # {kp_id: {'questions': [...], 'kp_data': {...}}}
    
    for kp_data in selected_kps:
        rs = kp_data['review_state']
        kp_id = rs.get('knowledgePointId')
        status = rs.get('status', 'newLearning')
        
        # 根据状态配置题目（不排除重复）
        original_questions = []
        variant_questions = []
        
        if status == 'newLearning':
            # 只选原题
            original_questions = select_original_questions(
                kp_data['mistakes'],
                estimate_question_count(status, difficulty),
                db,
                exclude_question_ids=None,  # 不排除重复
                knowledge_point_id=kp_id  # 传入知识点ID用于优先级排序
            )
            
        elif status == 'reviewing':
            # 原题（上次答错的）+ 变式题
            all_correct = check_if_all_correct_last_time(kp_data['mistakes'])
            original_count = 0 if all_correct else 1
            
            original_questions = select_wrong_questions(
                kp_data['mistakes'],
                original_count,
                db,
                exclude_question_ids=None,  # 不排除重复
                knowledge_point_id=kp_id  # 传入知识点ID用于优先级排序
            )
            
            variant_questions = select_variant_questions(
                kp_data,
                estimate_question_count(status, difficulty) - len(original_questions),
                db,
                exclude_question_ids=None  # 不排除重复
            )
            
        elif status == 'mastered':
            # 只推综合变式题
            variant_questions = select_comprehensive_questions(
                kp_data,
                estimate_question_count(status, difficulty),
                db,
                exclude_question_ids=None  # 不排除重复
            )
        
        # 保存该知识点的题目
        kp_question_map[kp_id] = {
            'original_questions': original_questions,
            'variant_questions': variant_questions,
            'kp_data': kp_data
        }
    
    # 第二步：按题目ID分组，找出哪些题目对应多个知识点
    question_to_kps = {}  # {question_id: [kp_id1, kp_id2, ...]}
    question_details = {}  # {question_id: {'question': {...}, 'source': 'original'/'variant', 'mistakeId': ...}}
    
    for kp_id, data in kp_question_map.items():
        # 处理原题
        for q in data['original_questions']:
            q_id = q['$id']
            if q_id not in question_to_kps:
                question_to_kps[q_id] = []
                question_details[q_id] = {
                    'question': q,
                    'source': 'original',
                    'mistakeId': q.get('mistakeId')
                }
            question_to_kps[q_id].append(kp_id)
        
        # 处理变式题
        for q in data['variant_questions']:
            q_id = q['$id']
            if q_id not in question_to_kps:
                question_to_kps[q_id] = []
                question_details[q_id] = {
                    'question': q,
                    'source': 'variant'
                }
            question_to_kps[q_id].append(kp_id)
    
    # 第三步：为每道题创建任务项，关联所有相关知识点
    task_items = []
    
    for q_id, kp_ids in question_to_kps.items():
        q_detail = question_details[q_id]
        
        # 收集所有相关知识点的信息
        kp_infos = []
        for kp_id in kp_ids:
            kp_data = kp_question_map[kp_id]['kp_data']
            kp_infos.append({
                'knowledgePointId': kp_id,
                'knowledgePointName': kp_data['user_kp'].get('name'),
                'status': kp_data['review_state'].get('status', 'newLearning')
            })
        
        # 构建任务项
        task_item = {
            'id': str(uuid.uuid4()),
            'questionId': q_id,
            'source': q_detail['source'],
            'knowledgePoints': kp_infos,  # 新字段：关联的所有知识点
            'isCompleted': False,
            'isCorrect': None
        }
        
        # 如果是原题，添加错题记录ID
        if q_detail.get('mistakeId'):
            task_item['mistakeRecordId'] = q_detail['mistakeId']
        
        task_items.append(task_item)
    
    logger.info(
        f"生成了 {len(task_items)} 个任务项，"
        f"覆盖 {len(selected_kps)} 个知识点"
    )
    
    return task_items


def generate_ai_message(kp_data: Dict[str, Any]) -> str:
    """
    生成 AI 提示信息
    
    Args:
        kp_data: 知识点数据
        
    Returns:
        AI 提示文本，如果没有则返回空字符串
    """
    # MVP阶段简化，暂不实现
    # 未来可以从 learning_memories 查询用户弱点，生成个性化提示
    return ""


def update_review_schedule(
    review_state_id: str,
    user_id: str,
    db: Databases
):
    """
    更新知识点的下次复习日期
    
    规则：
    - 生成任务后，nextReviewDate 应该往后延（避免明天又推送）
    - 具体间隔根据当前 currentInterval 决定
    
    Args:
        review_state_id: 复习状态记录ID
        user_id: 用户ID
        db: 数据库服务
    """
    try:
        review_state = db.get_document('main', 'review_states', review_state_id)
        
        current_interval = review_state.get('currentInterval', 1)
        status = review_state.get('status', 'newLearning')
        
        # 根据状态设置基础间隔
        # 生成任务后延长间隔，等用户完成后再根据反馈调整
        if status == 'newLearning':
            next_interval = current_interval
        elif status == 'reviewing':
            next_interval = current_interval
        else:  # mastered
            next_interval = current_interval
        
        # 更新 nextReviewDate
        today = datetime.now()
        next_review_date = today + timedelta(days=next_interval)
        
        db.update_document(
            'main',
            'review_states',
            review_state_id,
            {
                'nextReviewDate': next_review_date.isoformat()
            }
        )
        
        logger.debug(
            f"更新复习计划: {review_state_id}, "
            f"下次复习: {next_review_date.date()}"
        )
        
    except Exception as e:
        logger.error(f"更新复习计划失败: {review_state_id}, 错误: {e}")


def generate_daily_task_for_user(
    user: Dict[str, Any],
    db: Databases
) -> Dict[str, Any]:
    """
    为单个用户生成每日任务
    
    Args:
        user: 用户档案数据
        db: 数据库服务
        
    Returns:
        {
            'generated': bool,
            'reason': str,
            'total_questions': int
        }
    """
    user_id = user.get('userId')
    difficulty = user.get('dailyTaskDifficulty', 'normal')
    today = date.today().isoformat()
    
    # 1. 检查今天是否已生成任务
    try:
        existing_response = db.list_documents(
            'main',
            'daily_tasks',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('taskDate', today)
            ]
        )
        
        # 如果已存在，删除旧任务（覆盖策略）
        for task in existing_response['documents']:
            db.delete_document('main', 'daily_tasks', task['$id'])
            logger.info(f"删除旧任务: {task['$id']}")
            
    except Exception as e:
        logger.error(f"检查/删除旧任务失败: {e}")
    
    # 2. 选择知识点
    selected_kps = select_knowledge_points(user_id, difficulty, db)
    
    if not selected_kps:
        return {
            'generated': False,
            'reason': '没有到期的知识点',
            'total_questions': 0
        }
    
    # 3. 生成任务项
    task_items = generate_task_items(selected_kps, difficulty, db)
    
    if not task_items:
        return {
            'generated': False,
            'reason': '无法生成任务项',
            'total_questions': 0
        }
    
    # 4. 统计总题数（现在每个 task_item 就是一道题）
    total_questions = len(task_items)
    
    # 检查题目数量是否合理
    min_questions, max_questions = get_question_limits(difficulty)
    if total_questions < min_questions:
        logger.warning(
            f"用户 {user_id} 题目数量不足: {total_questions}/{min_questions}, "
            f"可能是题库不足导致"
        )
        # 注意：不阻断任务生成，即使题目少于预期也继续
        # 少量的题目总比没有任务好
    
    # 5. 构建任务文档
    task_data = {
        'userId': user_id,
        'taskDate': datetime.now().isoformat(),
        'items': json.dumps(task_items, ensure_ascii=False),
        'totalQuestions': total_questions,
        'completedCount': 0,
        'isCompleted': False
    }
    
    # 6. 保存到数据库
    try:
        db.create_document(
            'main',
            'daily_tasks',
            'unique()',
            task_data
        )
        logger.info(f"✓ 用户 {user_id}: 创建任务成功，{total_questions} 道题")
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        return {
            'generated': False,
            'reason': f'保存任务失败: {str(e)}',
            'total_questions': 0
        }
    
    # 7. 更新知识点的复习时间
    for kp_data in selected_kps:
        update_review_schedule(
            kp_data['review_state']['$id'],
            user_id,
            db
        )
    
    return {
        'generated': True,
        'reason': 'success',
        'total_questions': total_questions
    }


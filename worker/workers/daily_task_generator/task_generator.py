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
from appwrite.id import ID

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
from .timezone_utils import (
    get_user_timezone_date,
    get_user_timezone_datetime,
    get_user_timezone_iso_string
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
    user_timezone: str,
    db: Databases
) -> List[Dict[str, Any]]:
    """
    为用户选择今日需要复习的知识点
    
    Args:
        user_id: 用户ID
        difficulty: 难度设置 ('easy' | 'normal' | 'hard')
        user_timezone: 用户时区（如 'Asia/Shanghai'）
        db: 数据库服务
        
    Returns:
        选中的知识点列表（带优先级）
    """
    # 使用用户时区的当前日期
    today = get_user_timezone_date(user_timezone).isoformat()
    
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
            
            # 计算优先级（传入用户时区的今天）
            today_date = get_user_timezone_date(user_timezone)
            priority = calculate_priority(rs, user_kp, mistakes, questions, today_date)
            
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
    db: Databases,
    user_id: str = None
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    为选中的知识点生成任务项
    
    新策略：支持一题多知识点
    - 先为每个知识点独立选题（不排除重复）
    - 然后按题目ID分组，合并重复的题目
    - 一道题如果对应多个知识点，创建一个任务项关联所有知识点
    - 这样避免因去重导致某些知识点没有题目
    - 如果变式题不足，记录到 shortage_tracker 以便后续生成
    
    Args:
        selected_kps: 选中的知识点列表
        difficulty: 难度设置
        db: 数据库服务
        user_id: 用户ID（用于记录变式题生成需求）
        
    Returns:
        (任务项列表, shortage_tracker字典)
        - 任务项列表：每项可能关联多个知识点
        - shortage_tracker：记录需要生成变式题的源题目
    """
    # 第一步：为每个知识点独立选题
    kp_question_map = {}  # {kp_id: {'questions': [...], 'kp_data': {...}}}
    shortage_tracker = {}  # 记录需要生成变式题的源题目
    
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
                exclude_question_ids=None,  # 不排除重复
                shortage_tracker=shortage_tracker  # 传入 shortage_tracker
            )
            
        elif status == 'mastered':
            # 只推综合变式题
            variant_questions = select_comprehensive_questions(
                kp_data,
                estimate_question_count(status, difficulty),
                db,
                exclude_question_ids=None,  # 不排除重复
                shortage_tracker=shortage_tracker  # 传入 shortage_tracker
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
    
    # 如果有题目不足的情况，记录日志
    if shortage_tracker:
        logger.info(
            f"检测到 {len(shortage_tracker)} 个源题目需要生成变式题"
        )
    
    return task_items, shortage_tracker


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


def trigger_variant_generation(
    user_id: str,
    shortage_tracker: Dict[str, Any],
    db: Databases
):
    """
    异步触发变式题生成
    
    策略：
    - 直接创建 question_generation_tasks 记录
    - Appwrite Event 会自动触发 trigger function
    - Trigger function 会调用 Worker 进行实际生成
    - 生成的新题下次任务生成时可用
    
    Args:
        user_id: 用户ID
        shortage_tracker: 题目不足追踪器，格式：{question_id: {knowledge_point_id, variants_needed}}
        db: 数据库服务
    """
    if not shortage_tracker:
        return
    
    try:
        # 检查用户是否为会员（只有会员才能生成变式题）
        profiles = db.list_documents(
            'main',
            'profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if not profiles['documents']:
            logger.warning(f"用户 {user_id} 档案不存在，跳过变式题生成")
            return
        
        profile = profiles['documents'][0]
        subscription_status = profile.get('subscriptionStatus', 'free')
        
        # 只有活跃会员才触发生成
        if subscription_status != 'active':
            logger.info(f"用户 {user_id} 非会员，跳过变式题生成")
            return
        
        # 检查会员是否过期
        expiry_date = profile.get('subscriptionExpiryDate')
        if expiry_date:
            from datetime import timezone
            expiry_datetime = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
            if expiry_datetime <= datetime.now(timezone.utc):
                logger.info(f"用户 {user_id} 会员已过期，跳过变式题生成")
                return
        
        # 批量创建变式题生成任务
        # 策略：将多个源题目合并为一个任务，减少数据库操作
        source_question_ids = list(shortage_tracker.keys())
        
        # 限制每个任务最多处理10个源题目（避免单个任务太大）
        batch_size = 10
        for i in range(0, len(source_question_ids), batch_size):
            batch_ids = source_question_ids[i:i + batch_size]
            
            # 计算总题目数（每个源题目生成的变式数）
            total_variants = sum(
                shortage_tracker[qid]['variants_needed'] 
                for qid in batch_ids
            )
            
            # 使用统一的 variants_per_question（取平均值）
            avg_variants = max(1, total_variants // len(batch_ids))
            
            # 创建任务记录
            task_data = {
                'userId': user_id,
                'type': 'variant',
                'status': 'pending',
                'sourceQuestionIds': batch_ids,
                'variantsPerQuestion': avg_variants,
                'totalCount': len(batch_ids) * avg_variants,
                'completedCount': 0,
                'generatedQuestionIds': []
            }
            
            try:
                task = db.create_document(
                    'main',
                    'question_generation_tasks',
                    ID.unique(),
                    task_data
                )
                
                logger.info(
                    f"✓ 为用户 {user_id} 创建变式题生成任务: {task['$id']}, "
                    f"源题目数: {len(batch_ids)}, 预计生成: {len(batch_ids) * avg_variants} 题"
                )
            except Exception as e:
                logger.error(f"创建变式题生成任务失败: {e}")
                # 继续处理下一批
                continue
        
        logger.info(
            f"成功为用户 {user_id} 触发变式题生成，"
            f"总源题目数: {len(source_question_ids)}"
        )
        
    except Exception as e:
        logger.error(f"触发变式题生成异常: {e}")
        # 不抛出异常，避免影响主流程


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
    user_timezone = user.get('timezone', 'Asia/Shanghai')  # 获取用户时区
    
    # 使用用户时区的当前日期
    today = get_user_timezone_date(user_timezone)
    today_str = today.isoformat()
    
    # 1. 清理过期的未完成任务（超过7天）
    try:
        seven_days_ago = (today - timedelta(days=7)).isoformat()
        
        old_tasks_response = db.list_documents(
            'main',
            'daily_tasks',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('isCompleted', False),
                Query.less_than('taskDate', seven_days_ago),
                Query.limit(50)
            ]
        )
        
        # 删除过期任务
        for task in old_tasks_response['documents']:
            db.delete_document('main', 'daily_tasks', task['$id'])
            logger.info(f"删除过期任务: {task['$id']} (日期: {task.get('taskDate')})")
            
    except Exception as e:
        logger.warning(f"清理过期任务失败: {e}")
    
    # 2. 检查是否有过多的未完成任务（限制为最多2个）
    try:
        uncompleted_response = db.list_documents(
            'main',
            'daily_tasks',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('isCompleted', False),
                Query.order_desc('taskDate'),
                Query.limit(10)
            ]
        )
        
        uncompleted_count = len(uncompleted_response['documents'])
        
        if uncompleted_count >= 2:
            logger.info(f"用户 {user_id} 已有 {uncompleted_count} 个未完成任务，暂不生成新任务")
            return {
                'generated': False,
                'reason': f'已有 {uncompleted_count} 个未完成任务，请先完成现有任务',
                'total_questions': 0
            }
            
    except Exception as e:
        logger.warning(f"检查未完成任务数量失败: {e}")
    
    # 3. 检查今天是否已生成任务
    try:
        existing_response = db.list_documents(
            'main',
            'daily_tasks',
            queries=[
                Query.equal('userId', user_id),
                Query.equal('taskDate', today_str)
            ]
        )
        
        if existing_response['documents']:
            logger.info(f"用户 {user_id} 今天已有任务，跳过生成")
            return {
                'generated': False,
                'reason': '今天已生成任务',
                'total_questions': 0
            }
            
    except Exception as e:
        logger.error(f"检查今日任务失败: {e}")
    
    # 4. 选择知识点
    selected_kps = select_knowledge_points(user_id, difficulty, user_timezone, db)
    
    if not selected_kps:
        return {
            'generated': False,
            'reason': '没有到期的知识点',
            'total_questions': 0
        }
    
    # 5. 生成任务项
    task_items, shortage_tracker = generate_task_items(selected_kps, difficulty, db, user_id)
    
    if not task_items:
        return {
            'generated': False,
            'reason': '无法生成任务项',
            'total_questions': 0
        }
    
    # 6. 统计总题数（现在每个 task_item 就是一道题）
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
    
    # 7. 构建任务文档
    # 使用用户时区的当前时间，并转换为UTC存储
    task_data = {
        'userId': user_id,
        'taskDate': get_user_timezone_iso_string(user_timezone),
        'items': json.dumps(task_items, ensure_ascii=False),
        'totalQuestions': total_questions,
        'completedCount': 0,
        'isCompleted': False
    }
    
    # 8. 保存到数据库
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
    
    # 9. nextReviewDate 由前端在用户完成任务并提交反馈后更新
    # 任务生成器只负责查询到期的知识点和生成任务
    # 通过以下机制控制任务生成：
    #   - 限制未完成任务数量（最多2个，第 435-449 行）
    #   - 每天只生成一次（第 451-463 行）
    #   - 清理超过7天的过期任务（第 412-430 行）
    
    # 10. 异步触发变式题生成（如果有需要）
    if shortage_tracker:
        try:
            trigger_variant_generation(user_id, shortage_tracker, db)
        except Exception as e:
            # 变式题生成失败不影响主流程
            logger.warning(f"触发变式题生成失败（不影响任务生成）: {e}")
    
    return {
        'generated': True,
        'reason': 'success',
        'total_questions': total_questions
    }


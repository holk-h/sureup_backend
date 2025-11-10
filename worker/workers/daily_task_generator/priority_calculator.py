"""
优先级计算模块
根据知识点的各项指标计算复习优先级
"""
from datetime import datetime, date
from typing import Dict, Any, List
from loguru import logger


def calculate_priority(
    review_state: Dict[str, Any],
    user_kp: Dict[str, Any],
    mistake_records: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
    today: date = None
) -> float:
    """
    计算知识点的复习优先级（0-100分）
    
    优先级 = 紧急度×0.30 + 用户标记×0.25 + 知识点重要度×0.25 + 遗忘风险×0.20
    
    权重说明：
    - 紧急度(30%): 逾期/今日到期/新错题，最紧迫
    - 用户标记(25%): 用户主动标记重要，尊重主观判断
    - 知识点重要度(25%): 知识点自身重要程度（从 user_knowledge_points 表读取）
    - 遗忘风险(20%): 根据遗忘曲线，防止已学知识遗忘
    
    Args:
        review_state: 知识点复习状态
        user_kp: 用户知识点信息（包含 importance 字段）
        mistake_records: 相关错题记录
        questions: 知识点相关的题目列表
        today: 用户时区的"今天"日期（用于时区感知计算）
        
    Returns:
        优先级分数 (0-100)
    """
    if today is None:
        today = date.today()
    
    # 1. 紧急度（0-100分）- 最高权重
    urgency_score = calculate_urgency_score(review_state, mistake_records, today)
    
    # 2. 用户标记（0-100分）- 显著提升权重
    user_mark_score = calculate_user_mark_score(mistake_records)
    
    # 3. 知识点重要度（0-100分）- 直接从知识点记录读取
    importance_score = calculate_importance_score_from_kp(user_kp)
    
    # 4. 遗忘风险（0-100分）- 适当提升权重
    forget_risk = calculate_forget_risk(review_state, today)
    
    # 综合计算（新权重）
    priority = (
        urgency_score * 0.30 +
        user_mark_score * 0.25 +
        importance_score * 0.25 +
        forget_risk * 0.20
    )
    
    logger.debug(
        f"知识点优先级: {user_kp.get('name')} = "
        f"{priority:.1f} (紧急度={urgency_score:.1f}×0.30, "
        f"用户标记={user_mark_score:.1f}×0.25, "
        f"重要度={importance_score:.1f}×0.25, "
        f"遗忘={forget_risk:.1f}×0.20)"
    )
    
    return priority


def calculate_importance_score_from_kp(user_kp: Dict[str, Any]) -> float:
    """
    从知识点记录直接读取 importance 字段计算分数
    
    新设计：
    - importance 字段保存在 user_knowledge_points 表中
    - 描述知识点自身的重要程度（而非题目中的角色）
    
    Args:
        user_kp: 用户知识点记录（包含 importance 字段）
        
    Returns:
        重要度分数 (0-100)
    """
    # 从知识点记录读取 importance 字段
    importance = user_kp.get('importance', 'normal')
    
    # 重要度映射
    importance_map = {
        'high': 100,    # 高频考点
        'basic': 80,    # 基础知识
        'normal': 50    # 普通考点
    }
    
    score = importance_map.get(importance, 50)
    
    logger.debug(
        f"知识点 {user_kp.get('name')} 重要度: {importance} -> {score}分"
    )
    
    return float(score)


def calculate_importance_score_from_questions(
    questions: List[Dict[str, Any]], 
    knowledge_point_id: str
) -> float:
    """
    【已废弃】根据知识点关联题目的 importance 计算分数
    
    注意：此函数已被 calculate_importance_score_from_kp 替代
    保留此函数仅供参考或特殊场景使用
    
    新增逻辑：
    - 如果知识点是题目的主要知识点，权重加倍
    - 主要知识点的重要度分数会显著提升
    
    Args:
        questions: 知识点相关的题目列表
        knowledge_point_id: 当前知识点ID
        
    Returns:
        重要度分数 (0-100)
    """
    if not questions:
        return 50.0  # 默认普通
    
    # 基础重要度映射
    importance_map = {'high': 100, 'basic': 80, 'normal': 50}
    
    total_score = 0
    total_weight = 0
    
    for q in questions:
        # 获取题目的基础重要度分数
        base_score = importance_map.get(q.get('importance', 'normal'), 50)
        
        # 检查当前知识点是否为该题目的主要知识点
        primary_kp_ids = q.get('primaryKnowledgePointIds', [])
        is_primary = knowledge_point_id in primary_kp_ids if primary_kp_ids else False
        
        # 如果是主要知识点，权重加倍
        if is_primary:
            weight = 2.0  # 主要知识点权重
            logger.debug(f"题目 {q.get('$id', 'unknown')} 中知识点 {knowledge_point_id} 是主要知识点，权重加倍")
        else:
            weight = 1.0  # 普通知识点权重
        
        total_score += base_score * weight
        total_weight += weight
    
    # 计算加权平均分
    avg_score = total_score / total_weight if total_weight > 0 else 50.0
    
    # 确保分数在合理范围内
    avg_score = max(0.0, min(100.0, avg_score))
    
    logger.debug(f"知识点 {knowledge_point_id} 重要度分数: {avg_score:.1f} (基于 {len(questions)} 道题)")
    
    return avg_score


def calculate_urgency_score(
    review_state: Dict[str, Any],
    mistake_records: List[Dict[str, Any]],
    today: date = None
) -> float:
    """
    计算紧急度分数
    
    Args:
        review_state: 知识点复习状态
        mistake_records: 相关错题记录
        today: 用户时区的"今天"日期
        
    Returns:
        紧急度分数 (0-100)
    """
    if today is None:
        today = date.today()
    
    # 获取下次复习日期
    next_review_str = review_state.get('nextReviewDate')
    if not next_review_str:
        return 0.0
    
    # 解析日期（可能是 datetime 字符串或 date 字符串）
    try:
        if 'T' in next_review_str:
            # ISO datetime 格式
            next_review = datetime.fromisoformat(next_review_str.replace('Z', '+00:00')).date()
        else:
            # Date 格式
            next_review = datetime.fromisoformat(next_review_str).date()
    except Exception as e:
        logger.error(f"解析日期失败: {next_review_str}, 错误: {e}")
        return 0.0
    
    days_diff = (next_review - today).days
    
    # 逾期未复习
    if days_diff < 0:
        overdue_days = abs(days_diff)
        urgency_score = min(overdue_days * 15, 100)
        return urgency_score
    
    # 今天到期
    if days_diff == 0:
        return 85.0
    
    # 1-3天内新错题（检查最近错题时间）
    if days_diff <= 3:
        latest_mistake = get_latest_mistake(mistake_records)
        if latest_mistake:
            mistake_date = parse_created_at(latest_mistake.get('$createdAt'))
            if mistake_date:
                days_since_mistake = (today - mistake_date).days
                if days_since_mistake <= 3:
                    return 90.0
        return 50.0
    
    # 未来到期
    return 0.0


def calculate_forget_risk(review_state: Dict[str, Any], today: date = None) -> float:
    """
    计算遗忘风险分数（基于艾宾浩斯遗忘曲线）
    
    艾宾浩斯遗忘曲线特点：
    - 刚复习完：遗忘最慢
    - 前期（1-3天）：遗忘速度最快，快速上升
    - 中期（3-7天）：遗忘速度减缓
    - 后期（7天+）：趋于稳定
    
    使用指数函数模拟：遗忘风险 = 100 * (1 - e^(-k * t/T))
    其中：
    - t = days_passed (距上次复习天数)
    - T = currentInterval (复习间隔)
    - k = 2.5 (调节系数，控制遗忘速度)
    
    Args:
        review_state: 知识点复习状态
        today: 用户时区的"今天"日期
        
    Returns:
        遗忘风险分数 (0-100)
    """
    import math
    
    if today is None:
        today = date.today()
    
    last_review_str = review_state.get('lastReviewDate')
    if not last_review_str:
        return 0.0
    
    try:
        if 'T' in last_review_str:
            last_review = datetime.fromisoformat(last_review_str.replace('Z', '+00:00')).date()
        else:
            last_review = datetime.fromisoformat(last_review_str).date()
    except Exception as e:
        logger.error(f"解析最后复习日期失败: {last_review_str}, 错误: {e}")
        return 0.0
    
    days_passed = (today - last_review).days
    current_interval = review_state.get('currentInterval', 1)
    
    if current_interval <= 0 or days_passed <= 0:
        return 0.0
    
    # 艾宾浩斯遗忘曲线公式
    # k = 2.5，使得在 t = T 时遗忘风险约为 92%
    # k = 3.0，使得在 t = T 时遗忘风险约为 95%
    k = 2.5
    time_ratio = days_passed / current_interval
    
    # 遗忘风险 = 100 * (1 - e^(-k * time_ratio))
    # 这个公式的特点：
    # - 前期快速增长（符合遗忘曲线）
    # - 后期趋于平缓
    # - 永远不会超过100
    forget_risk = 100 * (1 - math.exp(-k * time_ratio))
    
    # 确保在合理范围内
    forget_risk = max(0.0, min(100.0, forget_risk))
    
    return forget_risk


def calculate_user_mark_score(mistake_records: List[Dict[str, Any]]) -> float:
    """
    计算用户标记分数
    
    Args:
        mistake_records: 相关错题记录
        
    Returns:
        用户标记分数 (0-100)
    """
    for mistake in mistake_records:
        if mistake.get('isImportant', False):
            return 100.0
    
    return 0.0


def get_latest_mistake(mistake_records: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """
    获取最近的错题记录
    
    Args:
        mistake_records: 错题记录列表
        
    Returns:
        最近的错题记录，如果没有则返回 None
    """
    if not mistake_records:
        return None
    
    # 按创建时间排序
    sorted_mistakes = sorted(
        mistake_records,
        key=lambda m: m.get('$createdAt', ''),
        reverse=True
    )
    
    return sorted_mistakes[0] if sorted_mistakes else None


def parse_created_at(created_at_str: str) -> date | None:
    """
    解析 $createdAt 字符串为 date 对象
    
    Args:
        created_at_str: ISO 格式的日期时间字符串
        
    Returns:
        date 对象，解析失败返回 None
    """
    if not created_at_str:
        return None
    
    try:
        dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        return dt.date()
    except Exception as e:
        logger.error(f"解析创建时间失败: {created_at_str}, 错误: {e}")
        return None


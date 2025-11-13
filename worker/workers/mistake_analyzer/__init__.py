"""
错题分析 Worker
"""
from .worker import MistakeAnalyzerWorker

# 导出核心功能（向后兼容）
from .core import (
    analyze_mistake_image,
    extract_question_content,
    analyze_subject_and_knowledge_points,
    get_llm_provider
)
from .services import (
    ensure_knowledge_point,
    ensure_module,
    add_question_to_knowledge_point,
    get_user_knowledge_points_by_subject,
    create_question,
    get_question,
    update_profile_stats_on_mistake_created
)
from .helpers import (
    create_appwrite_client,
    get_existing_modules,
    get_existing_knowledge_points_by_module
)

__all__ = [
    'MistakeAnalyzerWorker',
    # 核心功能
    'analyze_mistake_image',
    'extract_question_content',
    'analyze_subject_and_knowledge_points',
    'get_llm_provider',
    # 服务
    'ensure_knowledge_point',
    'ensure_module',
    'add_question_to_knowledge_point',
    'get_user_knowledge_points_by_subject',
    'create_question',
    'get_question',
    'update_profile_stats_on_mistake_created',
    # 辅助函数
    'create_appwrite_client',
    'get_existing_modules',
    'get_existing_knowledge_points_by_module'
]


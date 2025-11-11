"""
AI积累错题分析 Function

用户触发积累错题分析时调用此 Function
Function 负责：
1. 创建分析记录（accumulated_analyses）
2. 触发 Worker 任务
3. 返回分析记录 ID 供前端订阅
"""
import os
import sys
import json
from datetime import datetime, timezone
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.query import Query

# 添加 shared 路径
sys.path.append('../shared')

try:
    from utils import success_response, error_response, parse_request_body
except ImportError:
    # 本地测试时的降级处理
    def success_response(data, message="Success"):
        return {"success": True, "data": data, "message": message}
    
    def error_response(message, code=400, details=None):
        return {"success": False, "message": message, "code": code, "details": details}
    
    def parse_request_body(req):
        if hasattr(req, 'body'):
            body = req.body
            if isinstance(body, str):
                return json.loads(body) if body else {}
            return body
        return {}


# Configuration
DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_ANALYSES = 'accumulated_analyses'
COLLECTION_MISTAKES = 'mistake_records'


def get_databases() -> Databases:
    """Initialize Databases service"""
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def trigger_worker_task(task_data: dict) -> bool:
    """
    触发 Worker 任务
    
    这里需要根据你的 Worker 触发机制实现
    可以是：
    1. 发送消息队列（推荐）
    2. 直接 HTTP 调用 Worker API
    3. 写入任务表，Worker 轮询
    """
    try:
        import requests
        
        worker_url = os.environ.get('WORKER_API_URL', 'http://worker:8000')
        
        # 构建任务请求
        task_request = {
            'task_type': 'accumulated_mistakes_analyzer',
            'task_data': task_data,
            'priority': 3  # 中等优先级
        }
        
        print(f"[Worker Task] 触发积累错题分析: {json.dumps(task_request)}")
        
        # 调用 Worker API
        response = requests.post(
            f'{worker_url}/tasks/enqueue',
            json=task_request,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"Worker 任务已入队: {result.get('task_id')}")
            return True
        else:
            print(f"Worker 响应错误: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"触发 Worker 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def calculate_days_since_last_review(databases: Databases, user_id: str) -> int:
    """计算距上次复盘的天数"""
    try:
        # 查找最近一次完成的分析
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_ANALYSES,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('status', 'completed'),
                Query.order_desc('$createdAt'),
                Query.limit(1)
            ]
        )
        
        if result['total'] > 0:
            last_review = result['documents'][0]['$createdAt']
            # 解析日期
            last_date = datetime.fromisoformat(last_review.replace('Z', '+00:00'))
            now = datetime.utcnow()
            days = (now - last_date).days
            return days
        else:
            # 首次分析，返回默认值
            return 0
            
    except Exception as e:
        print(f"计算距上次复盘天数失败: {e}")
        return 0


def count_accumulated_mistakes(databases: Databases, user_id: str) -> int:
    """统计积累的错题数量（未被分析的错题）"""
    try:
        # 统计 accumulatedAnalyzedAt 为 null 的错题数量
        result = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_MISTAKES,
            queries=[
                Query.equal('userId', user_id),
                Query.is_null('accumulatedAnalyzedAt'),  # 查找未分析的错题
                Query.limit(1)  # 只需要 total 数量
            ]
        )
        
        return result['total']
        
    except Exception as e:
        print(f"统计积累错题失败: {e}")
        return 0


def check_accumulated_analysis_limit(databases: Databases, user_id: str) -> tuple:
    """
    检查用户积累错题分析限制
    
    免费用户：每天最多 1 次
    会员用户：无限制
    
    返回: (是否允许, 错误消息, 用户档案)
    """
    try:
        # 获取用户档案
        profiles = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id='profiles',
            queries=[
                Query.equal('userId', user_id),
                Query.limit(1)
            ]
        )
        
        if not profiles['documents']:
            return False, "用户档案不存在", None
        
        profile = profiles['documents'][0]
        
        # 检查订阅状态
        subscription_status = profile.get('subscriptionStatus', 'free')
        
        # 会员用户无限制
        if subscription_status == 'active':
            expiry_date = profile.get('subscriptionExpiryDate')
            if expiry_date:
                expiry_datetime = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                if expiry_datetime > datetime.now(timezone.utc):
                    return True, None, profile
        
        # 免费用户：检查每日限制
        today = datetime.now(timezone.utc).date()
        reset_date = profile.get('dailyLimitsResetDate')
        today_analyses = profile.get('todayAccumulatedAnalysis', 0)
        
        # 检查是否需要重置计数
        if reset_date:
            reset_datetime = datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
            reset_date_only = reset_datetime.date()
            
            if reset_date_only < today:
                # 需要重置
                today_analyses = 0
                databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id='profiles',
                    document_id=profile['$id'],
                    data={
                        'todayAccumulatedAnalysis': 0,
                        'dailyLimitsResetDate': datetime.now(timezone.utc).isoformat()
                    }
                )
                profile['todayAccumulatedAnalysis'] = 0
        else:
            # 首次使用
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id='profiles',
                document_id=profile['$id'],
                data={
                    'dailyLimitsResetDate': datetime.now(timezone.utc).isoformat()
                }
            )
        
        # 检查是否超限（免费用户每天最多 1 次）
        FREE_USER_DAILY_LIMIT = 1
        if today_analyses >= FREE_USER_DAILY_LIMIT:
            return False, f"今日免费额度已用完（{FREE_USER_DAILY_LIMIT}/{FREE_USER_DAILY_LIMIT}），升级会员享无限制", profile
        
        return True, None, profile
        
    except Exception as e:
        return False, f"权限检查失败: {str(e)}", None


def increment_accumulated_analysis_count(databases: Databases, profile_id: str):
    """增加今日积累分析计数"""
    try:
        profile = databases.get_document(
            database_id=DATABASE_ID,
            collection_id='profiles',
            document_id=profile_id
        )
        
        current_count = profile.get('todayAccumulatedAnalysis', 0)
        databases.update_document(
            database_id=DATABASE_ID,
            collection_id='profiles',
            document_id=profile_id,
            data={
                'todayAccumulatedAnalysis': current_count + 1
            }
        )
        return True
    except Exception as e:
        print(f"更新每日计数失败: {str(e)}")
        return False


def main(context):
    """Main entry point for Appwrite Function"""
    try:
        req = context.req
        res = context.res
        
        # 解析请求
        body = parse_request_body(req)
        user_id = body.get('userId')
        
        if not user_id:
            return res.json(error_response("userId is required"))
        
        print(f"收到分析请求: userId={user_id}")
        
        # 初始化数据库
        databases = get_databases()
        
        # 🔒 权限检查：积累错题分析每日限制
        is_allowed, error_msg, profile = check_accumulated_analysis_limit(databases, user_id)
        if not is_allowed:
            return res.json(error_response(error_msg, 403))
        
        # 检查是否有进行中的分析
        existing = databases.list_documents(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_ANALYSES,
            queries=[
                Query.equal('userId', user_id),
                Query.equal('status', ['pending', 'processing']),
                Query.limit(1)
            ]
        )
        
        if existing['total'] > 0:
            # 已有进行中的分析，返回现有记录
            analysis = existing['documents'][0]
            return res.json(success_response({
                'analysisId': analysis['$id'],
                'status': analysis['status'],
                'message': '已有分析正在进行中'
            }))
        
        # 计算统计信息
        days_since_last_review = calculate_days_since_last_review(databases, user_id)
        accumulated_mistakes = count_accumulated_mistakes(databases, user_id)
        
        print(f"统计信息: days={days_since_last_review}, mistakes={accumulated_mistakes}")
        
        # 创建分析记录
        analysis_data = {
            'userId': user_id,
            'status': 'pending',
            'mistakeCount': accumulated_mistakes,
            'daysSinceLastReview': days_since_last_review,
            'analysisContent': '',
            'summary': json.dumps({}),  # 转换为 JSON 字符串
            'mistakeIds': [],
        }
        
        analysis = databases.create_document(
            database_id=DATABASE_ID,
            collection_id=COLLECTION_ANALYSES,
            document_id=ID.unique(),
            data=analysis_data
        )
        
        analysis_id = analysis['$id']
        print(f"创建分析记录: {analysis_id}")
        
        # 触发 Worker 任务
        task_data = {
            'analysis_id': analysis_id,
            'user_id': user_id,
            'mistake_count': accumulated_mistakes,
            'days_since_last_review': days_since_last_review
        }
        
        worker_triggered = trigger_worker_task(task_data)
        
        if not worker_triggered:
            # Worker 触发失败，更新状态
            databases.update_document(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_ANALYSES,
                document_id=analysis_id,
                data={'status': 'failed'}
            )
            return res.json(error_response("Failed to trigger worker task", 500))
        
        # 更新每日计数（仅免费用户需要）
        if profile and profile.get('subscriptionStatus') != 'active':
            increment_accumulated_analysis_count(databases, profile['$id'])
        
        # 返回分析记录 ID
        return res.json(success_response({
            'analysisId': analysis_id,
            'status': 'pending',
            'mistakeCount': accumulated_mistakes,
            'daysSinceLastReview': days_since_last_review,
            'message': '分析任务已创建，请订阅更新'
        }))
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error: {error_details}")
        return res.json(error_response(str(e), 500, error_details))


"""
积累错题分析 Worker 实现

负责分析用户积累的错题，生成学习建议
支持通过 Realtime API 进行流式输出
"""
import os
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger

from workers.base import BaseWorker

# 延迟导入，避免循环依赖
def get_databases():
    from appwrite.client import Client
    from appwrite.services.databases import Databases
    client = Client()
    client.set_endpoint(os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1'))
    client.set_project(os.environ['APPWRITE_PROJECT_ID'])
    client.set_key(os.environ['APPWRITE_API_KEY'])
    return Databases(client)


def get_llm_provider():
    """获取 LLM Provider（复用 mistake_analyzer 的代码）"""
    import sys
    from pathlib import Path
    
    # 添加 mistake_analyzer 路径
    mistake_analyzer_path = Path(__file__).parent.parent / 'mistake_analyzer'
    sys.path.insert(0, str(mistake_analyzer_path))
    
    from llm_provider import get_llm_provider as _get_llm_provider
    return _get_llm_provider()


DATABASE_ID = os.environ.get('APPWRITE_DATABASE_ID', 'main')
COLLECTION_ANALYSES = 'accumulated_analyses'
COLLECTION_MISTAKES = 'mistake_records'
COLLECTION_QUESTIONS = 'questions'
COLLECTION_USER_KP = 'user_knowledge_points'


# 学科中文映射
SUBJECT_NAMES = {
    'math': '数学',
    'physics': '物理',
    'chemistry': '化学',
    'biology': '生物',
    'chinese': '语文',
    'english': '英语',
    'history': '历史',
    'geography': '地理',
    'politics': '政治'
}

# 错因中文映射
ERROR_REASON_NAMES = {
    'conceptUnclear': '概念理解不清',
    'logicBlocked': '思路断了',
    'calculationError': '计算错误',
    'careless': '粗心大意',
    'unfamiliar': '知识盲区',
    'timeInsufficient': '时间不够',
    'other': '其他'
}


class AccumulatedMistakesAnalyzerWorker(BaseWorker):
    """积累错题分析 Worker"""
    
    def __init__(self):
        super().__init__()
        self.databases = None
        self.llm_provider = None
    
    def _init_services(self):
        """初始化服务（延迟初始化）"""
        if not self.databases:
            self.databases = get_databases()
        if not self.llm_provider:
            self.llm_provider = get_llm_provider()
    
    async def process(self, task_data: Dict[str, Any]) -> Any:
        """
        处理积累错题分析任务
        
        Args:
            task_data: {
                'analysis_id': '分析记录ID',
                'user_id': '用户ID',
                'mistake_count': 15,
                'days_since_last_review': 3
            }
        
        Returns:
            分析结果
        """
        analysis_id = task_data.get('analysis_id')
        user_id = task_data.get('user_id')
        
        if not analysis_id or not user_id:
            raise ValueError("缺少 analysis_id 或 user_id")
        
        logger.info(f"开始分析用户 {user_id} 的积累错题，分析ID: {analysis_id}")
        
        # 初始化服务
        self._init_services()
        
        try:
            # 更新状态为 processing
            await self._update_analysis_status(analysis_id, 'processing')
            
            # 1. 获取用户积累的错题
            mistakes = await self._get_accumulated_mistakes(user_id, task_data)
            
            if not mistakes:
                logger.info(f"用户 {user_id} 没有积累错题")
                await self._update_analysis_status(
                    analysis_id, 
                    'completed',
                    content='暂时还没有积累错题哦，记录错题后再来分析吧！'
                )
                return {'success': True, 'message': '没有积累错题'}
            
            # 2. 统计分析数据
            stats = await self._calculate_statistics(mistakes, user_id)
            
            # 3. 生成分析内容（流式输出）
            await self._generate_analysis(analysis_id, mistakes, stats)
            
            # 4. 标记所有错题为已分析
            await self._mark_mistakes_as_analyzed(mistakes)
            
            # 5. 更新为完成状态
            await self._update_analysis_status(
                analysis_id,
                'completed',
                summary=stats['summary'],
                mistake_ids=[m['$id'] for m in mistakes],
                completed_at=datetime.utcnow().isoformat() + 'Z'
            )
            
            logger.info(f"分析完成: {analysis_id}")
            return {
                'success': True,
                'analysis_id': analysis_id,
                'mistake_count': len(mistakes)
            }
            
        except Exception as e:
            logger.error(f"分析失败: {str(e)}", exc_info=True)
            await self._update_analysis_status(
                analysis_id,
                'failed',
                content=f'分析失败：{str(e)}'
            )
            raise
    
    async def _get_accumulated_mistakes(
        self,
        user_id: str,
        task_data: Dict[str, Any]
    ) -> List[Dict]:
        """
        获取用户积累的错题
        
        策略：查找 accumulatedAnalyzedAt 为 null 的错题
        这些是尚未被纳入积累分析的错题
        """
        from appwrite.query import Query
        
        logger.info(f"查找用户 {user_id} 未分析的积累错题（accumulatedAnalyzedAt IS NULL）")
        
        mistakes = []
        offset = 0
        limit = 100
        
        while True:
            result = self.databases.list_documents(
                database_id=DATABASE_ID,
                collection_id=COLLECTION_MISTAKES,
                queries=[
                    Query.equal('userId', user_id),
                    Query.is_null('accumulatedAnalyzedAt'),  # 查找未分析的错题
                    Query.limit(limit),
                    Query.offset(offset)
                ]
            )
            
            mistakes.extend(result['documents'])
            
            if len(result['documents']) < limit:
                break
            
            offset += limit
        
        logger.info(f"找到 {len(mistakes)} 道未分析的积累错题")
        return mistakes
    
    async def _calculate_statistics(
        self,
        mistakes: List[Dict],
        user_id: str
    ) -> Dict[str, Any]:
        """计算统计数据"""
        from collections import Counter
        
        total_count = len(mistakes)
        
        # 学科分布
        subject_counts = Counter(m.get('subject', 'unknown') for m in mistakes)
        subject_distribution = [
            {
                'name': SUBJECT_NAMES.get(subject, subject),
                'count': count,
                'percentage': count / total_count * 100
            }
            for subject, count in subject_counts.most_common()
        ]
        
        # 错因分布
        reason_counts = Counter(m.get('errorReason', 'other') for m in mistakes)
        reason_distribution = [
            {
                'name': ERROR_REASON_NAMES.get(reason, reason),
                'count': count,
                'percentage': count / total_count * 100
            }
            for reason, count in reason_counts.most_common()
        ]
        
        return {
            'total_count': total_count,
            'subject_distribution': subject_distribution,
            'reason_distribution': reason_distribution,
            'summary': {
                'totalMistakes': total_count,
                'topSubject': subject_distribution[0]['name'] if subject_distribution else '无',
                'topReason': reason_distribution[0]['name'] if reason_distribution else '无'
            }
        }
    
    async def _generate_analysis(
        self,
        analysis_id: str,
        mistakes: List[Dict],
        stats: Dict[str, Any]
    ) -> None:
        """
        生成分析内容（流式输出）
        
        使用流式 API 实时生成内容，并以 0.5 秒频率更新数据库
        """
        # 构建 Prompt
        prompt = self._build_analysis_prompt(mistakes, stats)
        
        logger.info(f"开始生成分析内容，使用流式 LLM")
        
        try:
            # 使用流式输出调用 LLM
            stream_response = await self.llm_provider.chat(
                prompt=prompt,
                temperature=0.7,
                max_tokens=30000,  # 增加输出长度限制，充分利用长上下文
                stream=True  # 启用流式输出
            )
            
            # 处理流式响应
            await self._process_stream_response(analysis_id, stream_response)
            
        except Exception as e:
            logger.error(f"LLM 生成失败: {e}")
            raise
    
    async def _process_stream_response(
        self,
        analysis_id: str,
        stream_response: Any
    ) -> None:
        """
        处理流式响应，实时更新数据库
        
        策略：
        1. 实时接收 LLM 流式输出
        2. 累积内容并按 0.5 秒频率更新数据库
        3. 通过 Appwrite Realtime 让前端实时看到内容
        """
        accumulated_content = ''
        last_update_time = asyncio.get_event_loop().time()
        update_interval = 0.5  # 0.5 秒更新一次
        
        logger.info("开始处理流式响应")
        
        try:
            # 遍历流式响应
            with stream_response:
                for chunk in stream_response:
                    # 提取增量内容
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta.content is not None:
                            accumulated_content += delta.content
                            
                            # 检查是否需要更新数据库
                            current_time = asyncio.get_event_loop().time()
                            if current_time - last_update_time >= update_interval:
                                # 更新数据库
                                await self._update_analysis_content(
                                    analysis_id,
                                    accumulated_content
                                )
                                last_update_time = current_time
                                logger.debug(f"更新分析内容，当前长度: {len(accumulated_content)}")
            
            # 最后一次更新，确保所有内容都保存
            if accumulated_content:
                await self._update_analysis_content(analysis_id, accumulated_content)
                logger.info(f"流式输出完成，最终内容长度: {len(accumulated_content)}")
        
        except Exception as e:
            logger.error(f"处理流式响应失败: {e}", exc_info=True)
            raise
    
    async def _update_analysis_content(
        self,
        analysis_id: str,
        content: str
    ) -> None:
        """
        更新分析内容到数据库
        
        使用异步执行器避免阻塞
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_ANALYSES,
                    document_id=analysis_id,
                    data={'analysisContent': content}
                )
            )
        except Exception as e:
            logger.warning(f"更新数据库失败: {e}")
            # 不抛出异常，避免中断流式输出
    
    def _build_analysis_prompt(
        self,
        mistakes: List[Dict],
        stats: Dict[str, Any]
    ) -> str:
        """构建分析 Prompt"""
        
        total_count = stats['total_count']
        subject_dist = stats['subject_distribution']
        reason_dist = stats['reason_distribution']
        
        # 格式化学科分布（显示所有学科）
        subject_text = '\n'.join([
            f"  - {s['name']}: {s['count']}道 ({s['percentage']:.1f}%)"
            for s in subject_dist
        ])
        
        # 格式化错因分布（显示所有错因）
        reason_text = '\n'.join([
            f"  - {r['name']}: {r['count']}道 ({r['percentage']:.1f}%)"
            for r in reason_dist
        ])
        
        # 格式化所有错题的详情列表
        mistakes_detail = self._format_mistakes_detail(mistakes)
        
        prompt = f"""你是一位经验丰富、温暖有爱的学习导师，不仅擅长分析学生的学习模式，更精通各学科的知识点、常见题型和解题技巧。

# 学生积累错题概况

**错题总数**：{total_count} 道

## 学科分布
{subject_text}

## 错因分布
{reason_text}

# 错题详细信息

{mistakes_detail}

---

# 你的任务

请基于以上完整的学习数据，生成一份**深度学习指导报告**（Markdown格式）。这份报告要能真正帮助学生突破瓶颈、掌握方法、获得进步。

## 📊 学习现状洞察

深入分析学生的学习状况，结合具体的错题和错因，指出：

### 主要学习盲区
- 哪些学科/知识点是当前的薄弱环节？
- 这些盲区背后的根本原因是什么？
- 结合具体错题说明问题所在

### 突出的问题模式
- 从错因分布看出什么规律？
- 是概念不清、思路受阻，还是粗心大意？
- 不同学科是否有共同的问题？

### 学习优势与潜力
- 正向反馈：目前做得好的地方
- 可以发挥的优势是什么
- 哪些方面已经在进步

## 学习突破指南

### 核心攻坚点
明确指出**当前最应该攻克的2-3个核心问题**，说明为什么这些是关键，解决它们能带来什么改变。

### 具体学习方法

针对错题中暴露的问题，提供**详细的学习指导**：

**对于涉及的重点知识点**，提供：
1. **概念梳理**：这个知识点的核心是什么，学生容易混淆的地方在哪里
2. **解题思路**：遇到这类题目应该怎么想、按什么步骤来
3. **易错提醒**：常见陷阱和注意事项
4. **练习建议**：可以做什么类型的题来强化

**对于主要错因**（如概念不清、思路断裂等），给出：
1. **根源分析**：为什么会出现这个问题
2. **改进方法**：具体怎么做才能避免
3. **实战技巧**：考试/做题时的应对策略

### 学习效率提升

基于错题反映出的学习习惯问题，提供：
- 如何提高学习效率的方法
- 如何建立知识体系
- 如何避免重复犯错
- 刷题与总结的平衡

## 知识点点拨与技巧

针对错题中涉及的核心知识点，提供**具体的点拨和技巧**：

### 重点知识点解析
选择错题中最关键的知识点，给出：
- 知识点的本质理解
- 与其他知识点的联系
- 记忆/理解的小技巧
- 典型题型的快速识别方法

### 学科通用技巧
根据学科分布，提供相应学科的：
- 答题技巧
- 检验方法
- 时间分配策略
- 提分关键点

## 💪 成长寄语

用**温暖而有力量的话**：
1. 肯定学生记录错题、主动复盘的态度
2. 指出通过这次分析看到的进步空间
3. 给予信心和方向：每个薄弱点都是成长点，每次突破都让你更强大

---

**撰写要求**：
- 语气像一位既专业又温暖的导师
- 分析要**基于具体数据和错题**，有理有据
- 指导要**详细、具体、可操作**，不要泛泛而谈
- 知识点点拨要**准确、实用**，能真正帮助理解
- 适度使用 emoji 增加亲和力
- 确保学生看完能有实质收获

直接输出 Markdown 内容，不要添加任何说明或前缀。"""
        
        return prompt
    
    def _format_mistakes_detail(self, mistakes: List[Dict]) -> str:
        """
        格式化错题详细信息
        
        显示每道题的：学科、错因、备注、是否重要
        不限制数量和长度，充分利用 LLM 的长上下文能力
        """
        if not mistakes:
            return "（暂无错题详情）"
        
        total_count = len(mistakes)
        details = []
        
        for i, mistake in enumerate(mistakes, 1):
            subject = SUBJECT_NAMES.get(mistake.get('subject', ''), '未知学科')
            error_reason = ERROR_REASON_NAMES.get(mistake.get('errorReason', ''), '未标记')
            # 使用 or '' 来处理 None 值
            note = (mistake.get('note') or '').strip()
            is_important = mistake.get('isImportant', False)
            
            # 构建单条错题信息
            detail = f"**错题 {i}** - {subject}"
            
            if is_important:
                detail += " 🔴 重要"
            
            detail += f"\n- 错因：{error_reason}"
            
            if note:
                # 保留完整备注内容
                detail += f"\n- 备注：{note}"
            
            details.append(detail)
        
        result = '\n\n'.join(details)
        result += f"\n\n（以上为全部 {total_count} 道错题的详细信息）"
        
        return result
    
    async def _mark_mistakes_as_analyzed(
        self,
        mistakes: List[Dict]
    ) -> None:
        """
        标记所有错题为已分析
        
        更新 accumulatedAnalyzedAt 字段为当前时间
        """
        if not mistakes:
            return
        
        current_time = datetime.utcnow().isoformat() + 'Z'
        logger.info(f"标记 {len(mistakes)} 道错题为已分析")
        
        # 批量更新每道错题的 accumulatedAnalyzedAt 字段
        for mistake in mistakes:
            mistake_id = mistake['$id']
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.databases.update_document(
                        database_id=DATABASE_ID,
                        collection_id=COLLECTION_MISTAKES,
                        document_id=mistake_id,
                        data={'accumulatedAnalyzedAt': current_time}
                    )
                )
                logger.debug(f"已标记错题 {mistake_id} 为已分析")
            except Exception as e:
                logger.warning(f"更新错题 {mistake_id} 失败: {e}")
                # 继续处理其他错题，不中断流程
        
        logger.info(f"完成标记 {len(mistakes)} 道错题")
    
    async def _update_analysis_status(
        self,
        analysis_id: str,
        status: str,
        content: Optional[str] = None,
        summary: Optional[Dict] = None,
        mistake_ids: Optional[List[str]] = None,
        completed_at: Optional[str] = None
    ) -> None:
        """更新分析记录状态"""
        import json
        
        data = {'status': status}
        
        if content is not None:
            data['analysisContent'] = content
        
        if summary is not None:
            data['summary'] = json.dumps(summary)  # 转换为 JSON 字符串
        
        if mistake_ids is not None:
            data['mistakeIds'] = mistake_ids
        
        if completed_at is not None:
            data['completedAt'] = completed_at
        
        if status == 'processing':
            data['startedAt'] = datetime.utcnow().isoformat() + 'Z'
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.databases.update_document(
                    database_id=DATABASE_ID,
                    collection_id=COLLECTION_ANALYSES,
                    document_id=analysis_id,
                    data=data
                )
            )
            logger.info(f"更新分析状态: {status}")
        except Exception as e:
            logger.error(f"更新分析状态失败: {e}")
            # 不抛出异常，避免中断流程


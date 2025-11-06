"""
任务数据模型
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class TaskBase(BaseModel):
    """任务基类"""
    task_type: str = Field(..., description="任务类型")
    task_data: Dict[str, Any] = Field(..., description="任务数据")
    priority: int = Field(5, ge=1, le=10, description="优先级 (1-10，数字越小优先级越高)")


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field("", description="消息")


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    task_type: str
    status: str  # pending, processing, completed, failed
    enqueued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class QueueStats(BaseModel):
    """队列统计"""
    total: int = 0
    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0


# ========== 具体任务类型 ==========

class MistakeAnalyzerTask(BaseModel):
    """错题分析任务数据"""
    record_data: Dict[str, Any] = Field(..., description="错题记录数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "record_data": {
                    "$id": "record-id",
                    "userId": "user-id",
                    "originalImageId": "image-id",
                    "subject": "math",
                    "analysisStatus": "pending"
                }
            }
        }


class DailyTaskGeneratorTask(BaseModel):
    """每日任务生成任务数据"""
    trigger_time: str = Field(..., description="触发时间 (ISO格式)")
    trigger_type: str = Field(default="manual", description="触发类型 (scheduled|manual)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "trigger_time": "2025-11-05T02:00:00",
                "trigger_type": "scheduled"
            }
        }


"""Pydantic 请求/响应模型（v0.2）。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


# ---------- 客服账号 ----------
class AgentCreate(BaseModel):
    username: str
    password: str


class AgentOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- 分类 ----------
class CategoryCreate(BaseModel):
    name: str
    description: str = ""


class CategoryOut(BaseModel):
    id: int
    name: str
    description: str
    material_count: int = 0
    knowledge_version: int = 0  # 0 表示尚未提取知识

    model_config = ConfigDict(from_attributes=True)


# ---------- 材料 ----------
class MaterialOut(BaseModel):
    id: int
    category_id: int
    filename: str
    file_type: str
    file_size: int
    quality: str = "normal"  # excellent / normal / failed
    source_type: str = "sales"  # product / sales / sop / training / faq
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaterialDetailOut(MaterialOut):
    """单条材料详情，包含文本内容。"""
    content_text: str = ""


class MaterialUpdate(BaseModel):
    """更新材料请求。"""
    filename: Optional[str] = None
    content_text: Optional[str] = None
    quality: Optional[str] = None  # excellent / normal / failed
    source_type: Optional[str] = None  # product / sales / sop / training / faq


# ---------- 知识库 ----------
class KnowledgeOut(BaseModel):
    id: int
    category_id: int
    version: int
    prompt_version: str = "v1.0"
    content: dict
    source_material_ids: list[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- 训练会话 ----------
class SessionCreateRequest(BaseModel):
    category_id: int


class SessionOut(BaseModel):
    id: int
    category_id: int
    category_name: str = ""
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- 对话消息 ----------
class SendMessageRequest(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SendMessageReply(BaseModel):
    """客服发一条消息后，返回 AI 客户的下一句。"""

    agent_message: MessageOut
    customer_message: Optional[MessageOut] = None  # AI 客户回复（训练结束可能为空）
    is_finished: bool = False  # AI 客户主动结束对话


# ---------- 评分 ----------
class ScoreOut(BaseModel):
    id: int
    session_id: int
    total_score: float
    dimension_scores: dict = {}  # 四维分数 {"需求确认":25,"产品专业":20,...}
    advantages: list[str]
    mistakes: list[str]
    suggestions: list[str]
    summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinishReply(BaseModel):
    """结束训练触发评分后的响应。"""

    session: SessionOut
    score: ScoreOut


# ---------- 管理员：训练成绩查询 ----------
class AdminSessionListItem(BaseModel):
    """管理员视角的训练记录列表项（含分数摘要）。"""

    id: int
    user_id: int
    username: str
    category_id: int
    category_name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    message_count: int = 0
    score_total: Optional[float] = None  # None 表示尚未评分
    score_summary: str = ""

    model_config = ConfigDict(from_attributes=True)


class AdminSessionDetail(BaseModel):
    """管理员视角的训练记录详情（含完整对话+评分）。"""

    id: int
    user_id: int
    username: str
    category_id: int
    category_name: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    conversation_summary: str = ""
    messages: list[MessageOut]
    score: Optional[ScoreOut] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- 知识提取 ----------
class ExtractKnowledgeRequest(BaseModel):
    category_id: int


class ExtractKnowledgeReply(BaseModel):
    category_id: int
    knowledge_id: int
    version: int
    used_llm: bool  # 是否使用了真实 LLM
    message: str


# ---------- 管理员：训练成绩成长趋势 ----------
class ScoreTrendPoint(BaseModel):
    """某个 (客服×分类) 组合在某一日的评分点。"""

    date: str  # YYYY-MM-DD
    session_id: int
    total_score: float
    dimension_scores: dict = {}  # 四维分数


class ScoreTrendSeries(BaseModel):
    """一个 (客服×分类) 组合的成长趋势序列。"""

    user_id: int
    username: str
    category_id: int
    category_name: str
    points: list[ScoreTrendPoint]
    first_score: Optional[float] = None  # 区间内首条分数
    latest_score: Optional[float] = None  # 区间内最新分数
    delta: float = 0.0  # latest - first（>=2 条才有意义）
    trend: str = "flat"  # up / down / flat
    count: int = 0  # 区间内训练次数


class ScoreTrendsResponse(BaseModel):
    users: list[dict]  # 过滤用：[{"id","name"}]
    categories: list[dict]  # 过滤用：[{"id","name"}]
    series: list[ScoreTrendSeries]

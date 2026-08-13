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
    dimension_scores: dict = {}  # 各维度得分 {"需求确认":25,"产品专业":20,...}
    scoring_dimensions: dict = {}  # 各维度满分 {"需求确认":30,...} 前端渲染用
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


# ---------- 聊天语料导入 ----------
class ChatImportRequest(BaseModel):
    """原始聊天记录导入请求。"""
    category_id: int
    quality: str = "excellent"  # excellent / normal / failed
    raw_text: str


class ChatImportReply(BaseModel):
    """聊天语料导入结果。"""
    material: MaterialOut
    knowledge_version: int
    used_llm: bool
    success_count: int = 0
    failure_count: int = 0
    extracted_patterns: list[str] = []  # success/failure 模式摘要


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


# ---------- 错题本训练闭环（v0.7） ----------
class QuestionOut(BaseModel):
    """训练题目（客户剧本）。"""

    id: int
    category_id: int
    category_name: str = ""
    title: str
    scenario: str = ""
    script_text: str = ""
    source_type: str = "uploaded"  # uploaded / ai
    source_material_id: Optional[int] = None
    skill_id: Optional[int] = None  # 主知识点（v0.8）
    skill_name: str = ""  # 主知识点名
    difficulty: str = "medium"  # easy / medium / hard（v0.8）
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionSyncReply(BaseModel):
    created: int  # 本次新建题目数
    total: int  # 该品类题目总数


class BatchStartRequest(BaseModel):
    """客服开新批请求。"""

    category_id: int


class BatchQuestionOut(BaseModel):
    """批内单题（含会话与判定摘要）。"""

    id: int
    seq: int
    question_id: int
    question_title: str = ""
    is_mistake: bool = False  # 该题当前在该客服错题本
    session_id: Optional[int] = None
    session_status: str = ""  # in_progress / completed / ""
    score_total: Optional[float] = None
    review_status: str = "pending"  # pending / approved / rejected
    reviewed_at: Optional[datetime] = None


class TrainingBatchOut(BaseModel):
    """训练批次视图。"""

    id: int
    user_id: int
    category_id: int
    category_name: str = ""
    status: str  # in_progress / awaiting_review / reviewed
    question_count: int = 0
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    items: list[BatchQuestionOut] = []

    model_config = ConfigDict(from_attributes=True)


class BatchStartReply(BaseModel):
    """开新批响应。"""

    batch: TrainingBatchOut


class StartQuestionReply(BaseModel):
    """开始批内一题。"""

    session: SessionOut
    question: QuestionOut
    seq: int = 0
    total: int = 0
    is_mistake: bool = False
    batch_status: str = "in_progress"


class AgentBatchProgress(BaseModel):
    """客服训练进度视图。"""

    has_batch: bool = False
    batch: Optional[TrainingBatchOut] = None  # 当前/最近批次
    done_count: int = 0  # 当前批已完成题数
    mistake_count: int = 0  # 错题本未解决题数
    can_start_new: bool = False  # 能否开新批（无 in_progress/awaiting 批次）


class ReviewItem(BaseModel):
    question_id: int
    passed: bool


class ReviewBatchRequest(BaseModel):
    items: list[ReviewItem]


class ReviewBatchReply(BaseModel):
    batch: TrainingBatchOut
    mistakes_updated: int = 0  # 本次新进错题本题数


class AdminBatchListItem(BaseModel):
    """管理员视角的批次列表项。"""

    id: int
    user_id: int
    username: str = ""
    category_id: int
    category_name: str = ""
    status: str
    question_count: int = 0
    reviewed_count: int = 0  # 已判定题数
    created_at: datetime
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- 知识点掌握度引擎（v0.8） ----------
class SkillCreate(BaseModel):
    """新建知识点。"""

    name: str
    description: str = ""


class SkillUpdate(BaseModel):
    """更新知识点。"""

    name: Optional[str] = None
    description: Optional[str] = None


class SkillOut(BaseModel):
    """知识点视图。"""

    id: int
    category_id: int
    name: str
    description: str = ""
    source: str = "ai"  # ai / manual
    question_count: int = 0  # 绑定了多少道题（主知识点）
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MasteryOut(BaseModel):
    """单个知识点的掌握度视图。"""

    skill_id: int
    skill_name: str = ""
    mastery: float = 0.0  # 0~100
    status: str = "weak"  # weak / pass / master
    attempt_count: int = 0
    reject_count: int = 0
    last_judged_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MasteryListResponse(BaseModel):
    """客服个人掌握度图谱（某品类）。"""

    category_id: int
    category_name: str = ""
    items: list[MasteryOut] = []  # 按掌握度升序
    weak_count: int = 0
    pass_count: int = 0
    master_count: int = 0


class MasteryOverviewResponse(BaseModel):
    """管理员团队掌握度看板（某品类）。"""

    category_id: int
    category_name: str = ""
    skills: list[SkillOut] = []
    agents: list[dict] = []  # [{"id","name"}]
    rows: list[dict] = []  # [{user_id, username, skill_id, skill_name, mastery, status}]
    weak_ranking: list[dict] = []  # 薄弱知识点排行 [{skill_id, skill_name, avg_mastery, weak_count}]

"""数据模型（v0.2 七张表）。

两层知识架构：
- Material: 管理员上传的原始材料（txt/md 聊天记录、产品资料）
- Knowledge: AI 从材料中提取的结构化知识 JSON（模拟客户/评分都依赖它）

对话与评分：
- ChatSession / ChatMessage: 客服一次训练的会话与逐轮消息
- Score: 一次训练结束后的结构化评分（一会对一会话）
"""
import json
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """用户：admin 管理员 / agent 客服。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="agent")  # admin / agent
    created_at = Column(DateTime, default=datetime.utcnow)


class Category(Base):
    """训练分类（如 PVC训练、金属铭牌训练）。"""

    __tablename__ = "category"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    materials = relationship(
        "Material", back_populates="category", cascade="all, delete-orphan"
    )
    knowledge = relationship(
        "Knowledge", back_populates="category", cascade="all, delete-orphan"
    )


class Material(Base):
    """管理员上传的原始材料文件。content_text 为解析后的纯文本，供 AI 处理。

    quality 标注案例质量（仅对 sales 类型有意义）：
    - excellent: 优秀成交案例
    - normal:    普通案例
    - failed:    失败/丢单案例

    source_type 标注资料类型（决定 AI 学习方式）：
    - product:  产品知识（规格/参数/材质说明）
    - sales:    销售案例（聊天记录/成交/丢单）
    - sop:      SOP标准操作流程
    - training: 培训教材
    - faq:      常见问题
    """

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer, ForeignKey("category.id"), nullable=False, index=True
    )
    filename = Column(String(255), nullable=False)  # 原始文件名
    file_path = Column(String(512), nullable=False)  # 服务器存储路径
    content_text = Column(Text, default="")  # 解析后的纯文本
    file_type = Column(String(16), default="txt")  # txt/md/docx/pptx/pdf/xlsx
    file_size = Column(Integer, default=0)  # 字节数
    quality = Column(String(16), default="normal")  # excellent/normal/failed
    source_type = Column(String(16), default="sales")  # product/sales/sop/training/faq
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="materials")


class Knowledge(Base):
    """AI 从材料中提取的结构化知识 JSON。

    content_json 结构：
    {
      "category": "PVC",
      "required_questions": ["尺寸","数量","厚度","用途"],
      "common_objections": ["价格太高","交期太长"],
      "recommended_responses": [{"scenario":"...","guideline":"..."}],
      "product_specs": {...}
    }
    """

    __tablename__ = "knowledge"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer, ForeignKey("category.id"), nullable=False, index=True
    )
    content_json = Column(Text, nullable=False, default="{}")
    version = Column(Integer, default=1)  # 每次重新提取自增
    prompt_version = Column(String(32), default="v1.0")  # 生成该知识库所用的 prompt 版本
    source_material_ids = Column(Text, default="[]")  # 提取自哪些材料
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="knowledge")

    def get_content(self) -> dict:
        return json.loads(self.content_json or "{}")

    def set_content(self, data: dict) -> None:
        self.content_json = json.dumps(data, ensure_ascii=False)

    def get_source_ids(self) -> list[int]:
        return json.loads(self.source_material_ids or "[]")

    def set_source_ids(self, ids: list[int]) -> None:
        self.source_material_ids = json.dumps(ids)


class ChatSession(Base):
    """客服一次训练会话。"""

    __tablename__ = "chat_session"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False)
    status = Column(String(16), default="in_progress")  # in_progress / completed
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    conversation_summary = Column(Text, default="")  # 长对话的 AI 历史摘要（压缩 LLM 上下文）
    batch_question_id = Column(  # 错题本批次内题目（旧会话为 NULL，兼容）
        Integer, ForeignKey("batch_question.id"), nullable=True, index=True
    )

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )
    score = relationship(
        "Score", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    """对话消息：customer(AI客户) / agent(客服)。"""

    __tablename__ = "chat_message"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("chat_session.id"), nullable=False, index=True
    )
    role = Column(String(16), nullable=False)  # customer / agent
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class Score(Base):
    """一次训练的结构化评分（一对一会话）。"""

    __tablename__ = "score"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("chat_session.id"), nullable=False, unique=True, index=True
    )
    total_score = Column(Float, default=0.0)  # 0~100
    dimension_scores = Column(Text, default="{}")  # JSON: {"需求确认":25,"产品专业":20,...}
    scoring_dimensions = Column(Text, default="{}")  # JSON: {"需求确认":30,...} 各维度满分
    advantages = Column(Text, default="[]")  # JSON 数组
    mistakes = Column(Text, default="[]")  # JSON 数组
    suggestions = Column(Text, default="[]")  # JSON 数组
    summary = Column(Text, default="")  # 总评
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="score")

    def get_advantages(self) -> list[str]:
        return json.loads(self.advantages or "[]")

    def get_mistakes(self) -> list[str]:
        return json.loads(self.mistakes or "[]")

    def get_suggestions(self) -> list[str]:
        return json.loads(self.suggestions or "[]")

    def get_dimension_scores(self) -> dict:
        return json.loads(self.dimension_scores or "{}")

    def set_dimension_scores(self, scores: dict) -> None:
        self.dimension_scores = json.dumps(scores, ensure_ascii=False)

    def get_scoring_dimensions(self) -> dict:
        return json.loads(self.scoring_dimensions or "{}")

    def set_scoring_dimensions(self, dims: dict) -> None:
        self.scoring_dimensions = json.dumps(dims, ensure_ascii=False)

    def set_lists(
        self,
        advantages: list[str],
        mistakes: list[str],
        suggestions: list[str],
    ) -> None:
        self.advantages = json.dumps(advantages, ensure_ascii=False)
        self.mistakes = json.dumps(mistakes, ensure_ascii=False)
        self.suggestions = json.dumps(suggestions, ensure_ascii=False)

    def set_dimension_scores(self, dimension_scores: dict) -> None:
        self.dimension_scores = json.dumps(dimension_scores, ensure_ascii=False)


# ===================== 错题本训练闭环（v0.7） =====================


class Question(Base):
    """训练题目（客户剧本）。

    来源两种：
    - uploaded: 由已上传的 sales 聊天记录自动转题（source_material_id 指向原材料）
    - ai: AI 根据上传题生成的衍生题（二期）

    扮演时，AI 客户以 script_text 为蓝本衍生对话。

    v0.8 掌握度引擎：
    - skill_id: 主知识点（NULL = 未归类，旧题）
    - difficulty: 易/中/难（自适应出题用）
    - related_skill_ids: 关联知识点 id 列表（辅助信号，JSON）
    """

    __tablename__ = "question"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False, index=True)
    source_material_id = Column(Integer, nullable=True)  # 由哪条材料转题
    title = Column(String(255), nullable=False)  # 题目名
    scenario = Column(Text, default="")  # 客户场景/画像描述
    script_text = Column(Text, default="")  # 客户剧本（聊天记录原文 / 衍生文本）
    source_type = Column(String(16), default="uploaded")  # uploaded / ai
    skill_id = Column(Integer, ForeignKey("skill.id"), nullable=True, index=True)  # 主知识点
    difficulty = Column(String(16), default="medium")  # easy / medium / hard
    related_skill_ids = Column(Text, default="[]")  # JSON: [skill_id, ...]
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category")
    skill = relationship("Skill")

    def get_related_skill_ids(self) -> list[int]:
        return json.loads(self.related_skill_ids or "[]")

    def set_related_skill_ids(self, ids: list[int]) -> None:
        self.related_skill_ids = json.dumps(ids)


class TrainingBatch(Base):
    """客服一次训练批次（默认 20 题）。

    status 状态机：
    - in_progress:    练题中（20 题未全完成）
    - awaiting_review: 20 题练完，等主管判定
    - reviewed:        主管判定完，客服可开下一批
    """

    __tablename__ = "training_batch"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False, index=True)
    status = Column(String(16), default="in_progress")
    question_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    items = relationship(
        "BatchQuestion",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="BatchQuestion.seq",
    )


class BatchQuestion(Base):
    """批内题目：关联该题的训练会话与主管判定结果。"""

    __tablename__ = "batch_question"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer, ForeignKey("training_batch.id"), nullable=False, index=True
    )
    question_id = Column(Integer, ForeignKey("question.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)  # 批内序号 1..N
    session_id = Column(
        Integer, ForeignKey("chat_session.id"), nullable=True, index=True
    )  # 该题对应的训练会话（开始练后非空）
    review_status = Column(String(16), default="pending")  # pending / approved / rejected
    reviewed_at = Column(DateTime, nullable=True)

    batch = relationship("TrainingBatch", back_populates="items")
    question = relationship("Question")


class MistakeLog(Base):
    """客服错题本：被主管判定「不合适」的题目，间隔混入后续批次，直到判定「合适」。"""

    __tablename__ = "mistake_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("question.id"), nullable=False, index=True)
    appear_count = Column(Integer, default=1)  # 累计判错次数
    added_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)  # 非空 = 已通过

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_mistake_user_question"),
    )


# ===================== 知识点掌握度引擎（v0.8） =====================


class Skill(Base):
    """知识点（客服应掌握的能力项）。

    来源两种：
    - ai:     AI 从材料提炼知识时同步生成（source_material_ids 指向原材料）
    - manual: 管理员手工维护

    粒度：每品类 8~20 个（决策 #5）。
    """

    __tablename__ = "skill"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer, ForeignKey("category.id"), nullable=False, index=True
    )
    name = Column(String(64), nullable=False)  # 知识点名，如「报价计算」
    description = Column(Text, default="")  # 考察内容说明
    source = Column(String(16), default="ai")  # ai / manual
    source_material_ids = Column(Text, default="[]")  # 提炼自哪些材料（JSON）
    version = Column(Integer, default=1)  # 每次重新提炼自增（同 Knowledge 机制）
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_skill_category_name"),
    )

    category = relationship("Category")

    def get_source_ids(self) -> list[int]:
        return json.loads(self.source_material_ids or "[]")

    def set_source_ids(self, ids: list[int]) -> None:
        self.source_material_ids = json.dumps(ids)


class SkillMastery(Base):
    """用户 × 知识点掌握度（一人一知识点一行）。

    mastery: 0~100 EMA 值（决策 #11：加权移动平均，新判定权重更高）
    status: weak(薄弱) / pass(及格) / master(达标)（决策 #2，三档不判结业）
    """

    __tablename__ = "skill_mastery"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skill.id"), nullable=False, index=True)
    mastery = Column(Float, default=0.0)  # 0~100
    attempt_count = Column(Integer, default=0)  # 累计作答（判定）次数
    reject_count = Column(Integer, default=0)  # 累计驳回次数
    status = Column(String(16), default="weak")  # weak / pass / master
    last_judged_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_mastery_user_skill"),
    )

    skill = relationship("Skill")


class QuickReply(Base):
    """客服快捷回复短语（v0.9，全局通用）。

    客服训练对话时可点击快速填入/发送；管理员在管理端维护。
    v0.9.3：加 group_name 分组（千牛式分组切换），如 常用回复/催付/设计图。
    """

    __tablename__ = "quick_reply"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)  # 短语内容
    group_name = Column(String(32), default="常用回复")  # 分组（千牛式）
    is_active = Column(Integer, default=1)  # 1 启用 / 0 停用
    sort_order = Column(Integer, default=0)  # 排序（越小越靠前）
    created_at = Column(DateTime, default=datetime.utcnow)

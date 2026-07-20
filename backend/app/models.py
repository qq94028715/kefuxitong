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
    dimension_scores = Column(Text, default="{}")  # JSON: {"需求确认":35,"产品知识":15,...}
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

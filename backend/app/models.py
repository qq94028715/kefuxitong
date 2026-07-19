"""数据模型。

核心实体：
- User: 用户（admin 管理员 / agent 客服）
- TrainingType: 训练类型（如 PVC训练、金属铭牌训练）
- Corpus: 训练语料（客户问题 + 标准回答）
- TrainingSession: 训练会话（客服一次训练的记录）
- TrainingMessage: 训练消息（AI客户与客服的逐轮对话）
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
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="agent")  # admin / agent
    created_at = Column(DateTime, default=datetime.utcnow)


class TrainingType(Base):
    __tablename__ = "training_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    corpus = relationship(
        "Corpus", back_populates="training_type", cascade="all, delete-orphan"
    )


class Corpus(Base):
    __tablename__ = "corpus"

    id = Column(Integer, primary_key=True, index=True)
    training_type_id = Column(
        Integer, ForeignKey("training_types.id"), nullable=False, index=True
    )
    customer_question = Column(Text, nullable=False)  # 客户会问的问题
    standard_answer = Column(Text, nullable=False)  # 标准回答
    created_at = Column(DateTime, default=datetime.utcnow)

    training_type = relationship("TrainingType", back_populates="corpus")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    training_type_id = Column(
        Integer, ForeignKey("training_types.id"), nullable=False
    )
    # 本次训练抽取的语料 ID 列表（JSON 数组）
    questions = Column(Text, nullable=False, default="[]")
    current_index = Column(Integer, default=0)  # 当前进行到第几题
    status = Column(String(16), default="in_progress")  # in_progress / completed
    score = Column(Float, default=0.0)  # 累计得分（满分100）
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

    messages = relationship(
        "TrainingMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TrainingMessage.id",
    )

    def get_question_ids(self) -> list[int]:
        return json.loads(self.questions or "[]")

    def set_question_ids(self, ids: list[int]) -> None:
        self.questions = json.dumps(ids)


class TrainingMessage(Base):
    __tablename__ = "training_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("training_sessions.id"), nullable=False, index=True
    )
    role = Column(String(16), nullable=False)  # customer(AI客户) / agent(客服)
    content = Column(Text, nullable=False)
    score = Column(Float, nullable=True)  # 仅 agent 消息有评分
    feedback = Column(Text, default="")  # 仅 agent 消息有反馈
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("TrainingSession", back_populates="messages")

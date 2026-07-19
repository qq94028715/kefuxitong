"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Optional

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


# ---------- 训练类型 ----------
class TrainingTypeCreate(BaseModel):
    name: str
    description: str = ""


class TrainingTypeOut(BaseModel):
    id: int
    name: str
    description: str
    corpus_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# ---------- 语料 ----------
class CorpusCreate(BaseModel):
    training_type_id: int
    customer_question: str
    standard_answer: str


class CorpusOut(BaseModel):
    id: int
    training_type_id: int
    customer_question: str
    standard_answer: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- 训练会话 ----------
class SessionCreateRequest(BaseModel):
    training_type_id: int


class SessionOut(BaseModel):
    id: int
    training_type_id: int
    status: str
    score: float
    total_questions: int
    current_index: int
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- 训练消息 ----------
class SendMessageRequest(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    score: Optional[float] = None
    feedback: str = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrainReply(BaseModel):
    """客服发送一条消息后的统一回复。"""

    agent_message: MessageOut  # 客服刚发的消息（含评分反馈）
    next_customer_message: Optional[MessageOut] = None  # AI客户的下一句话
    is_finished: bool
    current_index: int
    total_questions: int
    total_score: float

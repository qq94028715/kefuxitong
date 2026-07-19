"""kefuxitong 客服训练系统 - FastAPI 入口。

路由分组：
- /api/admin/*  管理员接口（账号、训练类型、语料管理）
- /api/agent/*   客服接口（登录、训练对话）
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .ai_trainer import evaluate_answer, pick_questions
from .auth import (
    create_access_token,
    hash_password,
    require_admin,
    require_agent,
    verify_password,
)
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .models import Corpus, TrainingMessage, TrainingSession, TrainingType, User
from .schemas import (
    AgentCreate,
    AgentOut,
    CorpusCreate,
    CorpusOut,
    LoginRequest,
    MessageOut,
    SendMessageRequest,
    SessionCreateRequest,
    SessionOut,
    TokenResponse,
    TrainReply,
    TrainingTypeCreate,
    TrainingTypeOut,
)


# 默认示例语料（首次启动自动写入，便于立即体验训练流程）
DEFAULT_CORPUS = {
    "PVC训练": [
        (
            "你们的PVC板厚度有哪些规格？",
            "我们的PVC板厚度从1mm到20mm，常用规格有2mm、3mm、5mm、8mm、10mm，可按需定制。",
        ),
        (
            "PVC板耐高温吗？最高能用多少度？",
            "常规PVC板长期使用温度不超过60℃，短期可达80℃。如需更高耐温，建议选用CPVC材质。",
        ),
        (
            "PVC板可以户外使用吗？会老化吗？",
            "普通PVC板户外受紫外线影响会老化发黄，建议选用户外级抗UV的PVC板，使用寿命可达5-8年。",
        ),
    ],
    "金属铭牌训练": [
        (
            "金属铭牌有哪些材质可选？",
            "常用材质有不锈钢、铝合金、黄铜、锌合金，可根据使用场景和预算选择。",
        ),
        (
            "铭牌可以做哪些工艺？",
            "常见工艺包括腐蚀填色、丝网印刷、激光雕刻、冲压凸字、电镀等，支持多种工艺组合。",
        ),
        (
            "最小起订量是多少？交期多久？",
            "常规铭牌起订量100片，标准交期7-10个工作日，加急可3-5天，需收加急费。",
        ),
    ],
}


def init_db():
    """建表并写入默认数据（管理员 + 训练类型 + 示例语料）。"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 默认管理员
        if not db.query(User).filter(User.username == settings.default_admin_username).first():
            db.add(
                User(
                    username=settings.default_admin_username,
                    password_hash=hash_password(settings.default_admin_password),
                    role="admin",
                )
            )

        # 默认训练类型 + 示例语料
        for name, desc in [
            ("PVC训练", "PVC产品客服场景训练"),
            ("金属铭牌训练", "金属铭牌产品客服场景训练"),
        ]:
            tt = db.query(TrainingType).filter(TrainingType.name == name).first()
            if not tt:
                tt = TrainingType(name=name, description=desc)
                db.add(tt)
                db.flush()
            if db.query(Corpus).filter(Corpus.training_type_id == tt.id).count() == 0:
                for q, a in DEFAULT_CORPUS.get(name, []):
                    db.add(
                        Corpus(
                            training_type_id=tt.id,
                            customer_question=q,
                            standard_answer=a,
                        )
                    )
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="kefuxitong 客服训练系统",
    version="0.1.0",
    description="AI 驱动的客服培训平台：管理员维护语料，客服登录后选择训练类型进行模拟对话训练。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期允许所有来源，生产环境请改为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "kefuxitong", "version": "0.1.0", "docs": "/docs"}


# ===================== 管理员接口 =====================


@app.post("/api/admin/login", response_model=TokenResponse)
def admin_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.role != "admin" or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    return TokenResponse(access_token=token, role=user.role, username=user.username)


@app.get("/api/admin/agents", response_model=list[AgentOut])
def list_agents(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).filter(User.role == "agent").order_by(User.id).all()


@app.post("/api/admin/agents", response_model=AgentOut)
def create_agent(
    req: AgentCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password), role="agent")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.delete("/api/admin/agents/{agent_id}")
def delete_agent(
    agent_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not user:
        raise HTTPException(status_code=404, detail="客服账号不存在")
    db.delete(user)
    db.commit()
    return {"detail": "已删除"}


@app.get("/api/admin/training-types", response_model=list[TrainingTypeOut])
def list_training_types_admin(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _training_types_with_count(db)


@app.post("/api/admin/training-types", response_model=TrainingTypeOut)
def create_training_type(
    req: TrainingTypeCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(TrainingType).filter(TrainingType.name == req.name).first():
        raise HTTPException(status_code=400, detail="训练类型已存在")
    tt = TrainingType(name=req.name, description=req.description)
    db.add(tt)
    db.commit()
    db.refresh(tt)
    return TrainingTypeOut(id=tt.id, name=tt.name, description=tt.description, corpus_count=0)


@app.delete("/api/admin/training-types/{tt_id}")
def delete_training_type(
    tt_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tt = db.query(TrainingType).filter(TrainingType.id == tt_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="训练类型不存在")
    db.delete(tt)  # 级联删除语料
    db.commit()
    return {"detail": "已删除"}


@app.get("/api/admin/corpus", response_model=list[CorpusOut])
def list_corpus(
    training_type_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(Corpus)
        .filter(Corpus.training_type_id == training_type_id)
        .order_by(Corpus.id)
        .all()
    )


@app.post("/api/admin/corpus", response_model=CorpusOut)
def create_corpus(
    req: CorpusCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.query(TrainingType).filter(TrainingType.id == req.training_type_id).first():
        raise HTTPException(status_code=404, detail="训练类型不存在")
    c = Corpus(
        training_type_id=req.training_type_id,
        customer_question=req.customer_question,
        standard_answer=req.standard_answer,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@app.delete("/api/admin/corpus/{corpus_id}")
def delete_corpus(
    corpus_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    c = db.query(Corpus).filter(Corpus.id == corpus_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="语料不存在")
    db.delete(c)
    db.commit()
    return {"detail": "已删除"}


# ===================== 客服接口 =====================


@app.post("/api/agent/login", response_model=TokenResponse)
def agent_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.role != "agent" or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    return TokenResponse(access_token=token, role=user.role, username=user.username)


@app.get("/api/agent/training-types", response_model=list[TrainingTypeOut])
def list_training_types_agent(_: User = Depends(require_agent), db: Session = Depends(get_db)):
    return _training_types_with_count(db)


@app.post("/api/agent/sessions", response_model=SessionOut)
def start_session(
    req: SessionCreateRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    tt = db.query(TrainingType).filter(TrainingType.id == req.training_type_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="训练类型不存在")
    questions = pick_questions(db, req.training_type_id, settings.questions_per_session)
    if not questions:
        raise HTTPException(status_code=400, detail=f"{tt.name} 暂无语料，请联系管理员添加")

    session = TrainingSession(
        user_id=user.id,
        training_type_id=req.training_type_id,
        current_index=0,
        status="in_progress",
    )
    session.set_question_ids([q.id for q in questions])
    db.add(session)
    db.flush()

    # 发送第一条客户消息
    db.add(
        TrainingMessage(
            session_id=session.id,
            role="customer",
            content=questions[0].customer_question,
        )
    )
    db.commit()
    db.refresh(session)
    return _session_out(session)


@app.get("/api/agent/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    s = (
        db.query(TrainingSession)
        .filter(TrainingSession.id == session_id, TrainingSession.user_id == user.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    return _session_out(s)


@app.get("/api/agent/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    s = (
        db.query(TrainingSession)
        .filter(TrainingSession.id == session_id, TrainingSession.user_id == user.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    return s.messages


@app.post("/api/agent/sessions/{session_id}/messages", response_model=TrainReply)
def send_message(
    session_id: int,
    req: SendMessageRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    s = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    if s.status == "completed":
        raise HTTPException(status_code=400, detail="训练已结束")

    question_ids = s.get_question_ids()
    idx = s.current_index
    if idx >= len(question_ids):
        raise HTTPException(status_code=400, detail="无待答题目")

    current_corpus = db.query(Corpus).filter(Corpus.id == question_ids[idx]).first()
    if not current_corpus:
        raise HTTPException(status_code=500, detail="语料缺失")

    # 1) 评估客服回答
    score, feedback = evaluate_answer(req.content, current_corpus.standard_answer)
    agent_msg = TrainingMessage(
        session_id=s.id,
        role="agent",
        content=req.content,
        score=score,
        feedback=feedback,
    )
    db.add(agent_msg)
    s.score += score

    # 2) 推进到下一题
    next_idx = idx + 1
    s.current_index = next_idx
    next_customer = None
    is_finished = False

    if next_idx >= len(question_ids):
        s.status = "completed"
        s.ended_at = datetime.utcnow()
        is_finished = True
    else:
        next_corpus = db.query(Corpus).filter(Corpus.id == question_ids[next_idx]).first()
        if next_corpus:
            cm = TrainingMessage(
                session_id=s.id,
                role="customer",
                content=next_corpus.customer_question,
            )
            db.add(cm)
            db.flush()
            next_customer = cm

    db.commit()
    db.refresh(agent_msg)

    return TrainReply(
        agent_message=MessageOut.model_validate(agent_msg, from_attributes=True),
        next_customer_message=(
            MessageOut.model_validate(next_customer, from_attributes=True)
            if next_customer
            else None
        ),
        is_finished=is_finished,
        current_index=next_idx,
        total_questions=len(question_ids),
        total_score=round(s.score, 1),
    )


# ===================== 辅助函数 =====================


def _training_types_with_count(db: Session) -> list[TrainingTypeOut]:
    items = db.query(TrainingType).order_by(TrainingType.id).all()
    result = []
    for tt in items:
        count = db.query(Corpus).filter(Corpus.training_type_id == tt.id).count()
        result.append(
            TrainingTypeOut(
                id=tt.id,
                name=tt.name,
                description=tt.description,
                corpus_count=count,
            )
        )
    return result


def _session_out(s: TrainingSession) -> SessionOut:
    return SessionOut(
        id=s.id,
        training_type_id=s.training_type_id,
        status=s.status,
        score=round(s.score, 1),
        total_questions=len(s.get_question_ids()),
        current_index=s.current_index,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )

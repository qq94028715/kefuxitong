"""kefuxitong 客服训练系统 - FastAPI 入口（v0.3）。

v0.3 核心升级：Intent 三层路由 + 流式输出。
- chat → intent.classify → Quick Reply / Cache / DeepSeek → stream 输出
- 多数轮次毫秒级响应（无需调 LLM），DeepSeek 兜底复杂场景
- SSE 流式传输，前端逐字显示
"""
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from .ai import cache as reply_cache
from .ai.evaluator import evaluate_session
from .ai.knowledge import (
    extract_knowledge,
    get_knowledge_for_training,
    get_latest_knowledge,
)
from .ai.router import generate_reply_stream
from .ai.simulator import END_MARKER, generate_customer_reply
from .auth import (
    create_access_token,
    hash_password,
    require_admin,
    require_agent,
    verify_password,
)
from .config import UPLOAD_DIR, settings
from .database import Base, SessionLocal, engine, get_db
from .models import (
    Category,
    ChatMessage,
    ChatSession,
    Knowledge,
    Material,
    Score,
    User,
)
from .schemas import (
    AgentCreate,
    AgentOut,
    AdminSessionDetail,
    AdminSessionListItem,
    CategoryCreate,
    CategoryOut,
    ExtractKnowledgeReply,
    ExtractKnowledgeRequest,
    FinishReply,
    KnowledgeOut,
    LoginRequest,
    MaterialDetailOut,
    MaterialOut,
    MaterialUpdate,
    MessageOut,
    ScoreOut,
    SendMessageReply,
    SendMessageRequest,
    SessionCreateRequest,
    SessionOut,
    TokenResponse,
)

# 内置示例知识（首次启动写入，无 LLM 也能体验训练流程）
DEFAULT_KNOWLEDGE: dict[str, dict] = {
    "PVC训练": {
        "category": "PVC训练",
        "product_summary": "PVC 板材/标签产品，常用于标识、装饰、工业件。",
        "required_questions": ["尺寸", "数量", "厚度", "用途", "耐温要求"],
        "common_objections": ["价格太高", "交期太长", "担心户外老化"],
        "recommended_responses": [
            {
                "scenario": "客户问耐温",
                "guideline": "常规 PVC 长期 60℃、短期 80℃，更高温场景推荐 CPVC。",
            },
            {
                "scenario": "客户问户外使用",
                "guideline": "普通 PVC 紫外线下会老化发黄，推荐户外级抗 UV 板，寿命 5-8 年。",
            },
        ],
        "product_specs": {
            "材质": "PVC / CPVC",
            "厚度": "1mm - 20mm，常用 2/3/5/8/10mm",
            "工艺": "切割、雕刻、丝印、UV 打印",
            "起订量": "按规格面议",
            "交期": "7-10 个工作日",
        },
        "key_knowledge": [
            "户外使用需选抗 UV 级",
            "常规 PVC 不耐高温（≤60℃）",
            "可定制尺寸与厚度",
        ],
        "success_patterns": [
            {
                "scenario": "客户问耐温",
                "technique": "先确认使用场景温度，再推荐合适材质",
                "example": "常规 PVC 长期 60℃，更高温推荐 CPVC",
            },
        ],
        "failure_patterns": [
            {
                "scenario": "未确认户外用途",
                "mistake": "推荐了普通 PVC 而非抗 UV 级",
                "consequence": "户外使用会老化发黄，客户投诉",
            },
        ],
    },
    "金属铭牌训练": {
        "category": "金属铭牌训练",
        "product_summary": "金属铭牌/标牌，用于设备铭牌、品牌标识、礼品牌。",
        "required_questions": ["尺寸", "数量", "材质", "工艺", "用途"],
        "common_objections": ["起订量高", "交期长", "价格贵"],
        "recommended_responses": [
            {
                "scenario": "客户问 MOQ",
                "guideline": "常规 100 片起订，量大有阶梯价，先确认规格再报价。",
            },
            {
                "scenario": "客户问工艺",
                "guideline": "腐蚀填色、丝印、激光雕刻、冲压凸字、电镀，可组合工艺。",
            },
        ],
        "product_specs": {
            "材质": "不锈钢 / 铝合金 / 黄铜 / 锌合金",
            "工艺": "腐蚀填色 / 丝印 / 激光雕刻 / 冲压 / 电镀",
            "起订量": "100 片",
            "交期": "7-10 个工作日，加急 3-5 天",
        },
        "key_knowledge": [
            "支持多工艺组合",
            "加急需另收加急费",
            "不同材质价格差异大，需按预算推荐",
        ],
        "success_patterns": [
            {
                "scenario": "客户问 MOQ",
                "technique": "先确认规格再报起订量，提供阶梯价",
                "example": "常规 100 片起订，量大有阶梯价",
            },
        ],
        "failure_patterns": [
            {
                "scenario": "未确认材质就报价",
                "mistake": "报了铝合金价格，客户实际要黄铜",
                "consequence": "价格差距大，客户觉得不专业而流失",
            },
        ],
    },
}


def init_db():
    """建表并写入默认数据（管理员 + 两个分类 + 示例知识）。"""
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

        # 默认分类 + 示例知识
        for name, desc in [
            ("PVC训练", "PVC 产品客服场景训练"),
            ("金属铭牌训练", "金属铭牌产品客服场景训练"),
        ]:
            cat = db.query(Category).filter(Category.name == name).first()
            if not cat:
                cat = Category(name=name, description=desc)
                db.add(cat)
                db.flush()
            # 写入示例知识（如果没有）
            if not get_latest_knowledge(db, cat.id):
                k = Knowledge(category_id=cat.id, version=1)
                k.set_content(DEFAULT_KNOWLEDGE[name])
                k.set_source_ids([])
                db.add(k)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="kefuxitong 客服训练系统",
    version="0.2.0",
    description="AI 驱动的客服培训平台：材料→结构化知识→模拟客户对话→AI 评分。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "kefuxitong",
        "version": "0.2.0",
        "docs": "/docs",
        "llm_enabled": bool(settings.llm_api_key),
    }


# ===================== 管理员接口 =====================


@app.post("/api/admin/login", response_model=TokenResponse)
def admin_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.role != "admin" or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    return TokenResponse(access_token=token, role=user.role, username=user.username)


# ---------- 客服账号 ----------
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
def delete_agent(agent_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not user:
        raise HTTPException(status_code=404, detail="客服账号不存在")
    db.delete(user)
    db.commit()
    return {"detail": "已删除"}


# ---------- 分类 ----------
@app.get("/api/admin/categories", response_model=list[CategoryOut])
def list_categories_admin(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _categories_with_count(db)


@app.post("/api/admin/categories", response_model=CategoryOut)
def create_category(
    req: CategoryCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(Category).filter(Category.name == req.name).first():
        raise HTTPException(status_code=400, detail="分类已存在")
    cat = Category(name=req.name, description=req.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryOut(
        id=cat.id, name=cat.name, description=cat.description,
        material_count=0, knowledge_version=0,
    )


@app.delete("/api/admin/categories/{cat_id}")
def delete_category(cat_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    db.delete(cat)  # 级联删除材料与知识
    db.commit()
    return {"detail": "已删除"}


# ---------- 材料 ----------
@app.get("/api/admin/materials", response_model=list[MaterialOut])
def list_materials(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(Material)
        .filter(Material.category_id == category_id)
        .order_by(Material.id)
        .all()
    )


@app.post("/api/admin/materials/upload", response_model=MaterialOut)
async def upload_material(
    category_id: int = Form(...),
    quality: str = Form("normal"),
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")

    # 案例类型校验
    ALLOWED_QUALITY = {"excellent", "normal", "failed"}
    if quality not in ALLOWED_QUALITY:
        raise HTTPException(
            status_code=400,
            detail=f"案例类型无效，仅支持 {', '.join(sorted(ALLOWED_QUALITY))}",
        )

    # 文件大小限制（5MB）
    MAX_FILE_SIZE = 5 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，限制 5MB 以内")

    # 扩展名白名单校验
    raw_name = file.filename or "untitled.txt"
    filename = Path(raw_name).name  # 剥掉路径，防穿越
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    ALLOWED_EXTS = {"txt", "md", "json"}
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：.{ext}，仅支持 {', '.join(sorted(ALLOWED_EXTS))}",
        )
    file_type = ext

    # 尝试 utf-8，失败用 gbk（Windows 中文常见）
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="ignore")

    safe_name = f"{category_id}_{uuid.uuid4().hex[:8]}_{filename}"
    save_path = UPLOAD_DIR / safe_name
    # 二次防御：确认最终路径仍在 UPLOAD_DIR 内
    try:
        save_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    save_path.write_bytes(content)

    m = Material(
        category_id=category_id,
        filename=filename,
        file_path=str(save_path),
        content_text=text,
        file_type=file_type,
        file_size=len(content),
        quality=quality,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@app.delete("/api/admin/materials/{material_id}")
def delete_material(
    material_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="材料不存在")
    # 删除物理文件（忽略错误）
    try:
        from pathlib import Path
        Path(m.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(m)
    db.commit()
    return {"detail": "已删除"}


@app.get("/api/admin/materials/{material_id}", response_model=MaterialDetailOut)
def get_material(
    material_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="材料不存在")
    return m


@app.put("/api/admin/materials/{material_id}", response_model=MaterialDetailOut)
def update_material(
    material_id: int,
    req: MaterialUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="材料不存在")

    if req.filename is not None:
        m.filename = req.filename

    if req.quality is not None:
        ALLOWED_QUALITY = {"excellent", "normal", "failed"}
        if req.quality not in ALLOWED_QUALITY:
            raise HTTPException(
                status_code=400,
                detail=f"案例类型无效，仅支持 {', '.join(sorted(ALLOWED_QUALITY))}",
            )
        m.quality = req.quality

    if req.content_text is not None:
        m.content_text = req.content_text
        # 同步更新物理文件
        try:
            from pathlib import Path
            Path(m.file_path).write_text(req.content_text, encoding="utf-8")
        except Exception:
            raise HTTPException(status_code=500, detail="更新文件失败")

    db.commit()
    db.refresh(m)
    return m


# ---------- 知识库 ----------
@app.get("/api/admin/knowledge", response_model=KnowledgeOut)
def get_knowledge(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    k = get_latest_knowledge(db, category_id)
    if not k:
        raise HTTPException(status_code=404, detail="该分类尚未提取知识库")
    return _knowledge_out(k)


@app.post("/api/admin/knowledge/extract", response_model=ExtractKnowledgeReply)
def extract(
    req: ExtractKnowledgeRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        k, used_llm = extract_knowledge(db, req.category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 知识库更新后，清空该分类的旧回复缓存，避免新人训练用旧知识
    reply_cache.invalidate(req.category_id)
    msg = (
        f"已用 LLM 提取知识库（v{k.version}）"
        if used_llm
        else f"已用规则模式提取知识库（v{k.version}），未配置 LLM_API_KEY"
    )
    return ExtractKnowledgeReply(
        category_id=req.category_id,
        knowledge_id=k.id,
        version=k.version,
        used_llm=used_llm,
        message=msg,
    )


# ---------- 训练成绩（管理员） ----------
@app.get("/api/admin/sessions", response_model=list[AdminSessionListItem])
def admin_list_sessions(
    user_id: int | None = None,
    category_id: int | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看训练记录列表（含分数摘要）。

    可按 user_id / category_id 过滤。按 id 倒序（最新在前）。
    """
    q = (
        db.query(ChatSession, User, Category)
        .join(User, ChatSession.user_id == User.id)
        .join(Category, ChatSession.category_id == Category.id)
    )
    if user_id:
        q = q.filter(ChatSession.user_id == user_id)
    if category_id:
        q = q.filter(ChatSession.category_id == category_id)
    rows = q.order_by(ChatSession.id.desc()).all()

    result = []
    for s, u, c in rows:
        msg_count = (
            db.query(ChatMessage).filter(ChatMessage.session_id == s.id).count()
        )
        score_total = s.score.total_score if s.score else None
        score_summary = s.score.summary if s.score else ""
        result.append(
            AdminSessionListItem(
                id=s.id,
                user_id=s.user_id,
                username=u.username,
                category_id=s.category_id,
                category_name=c.name,
                status=s.status,
                started_at=s.started_at,
                ended_at=s.ended_at,
                message_count=msg_count,
                score_total=score_total,
                score_summary=score_summary,
            )
        )
    return result


@app.get("/api/admin/sessions/{session_id}", response_model=AdminSessionDetail)
def admin_get_session(
    session_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看某次训练的完整对话与评分详情。"""
    row = (
        db.query(ChatSession, User, Category)
        .join(User, ChatSession.user_id == User.id)
        .join(Category, ChatSession.category_id == Category.id)
        .filter(ChatSession.id == session_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="训练记录不存在")
    s, u, c = row
    return AdminSessionDetail(
        id=s.id,
        user_id=s.user_id,
        username=u.username,
        category_id=s.category_id,
        category_name=c.name,
        status=s.status,
        started_at=s.started_at,
        ended_at=s.ended_at,
        messages=[
            MessageOut.model_validate(m, from_attributes=True) for m in s.messages
        ],
        score=_score_out(s.score) if s.score else None,
    )


# ===================== 客服接口 =====================


@app.post("/api/agent/login", response_model=TokenResponse)
def agent_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.role != "agent" or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    return TokenResponse(access_token=token, role=user.role, username=user.username)


@app.get("/api/agent/categories", response_model=list[CategoryOut])
def list_categories_agent(_: User = Depends(require_agent), db: Session = Depends(get_db)):
    return _categories_with_count(db)


@app.post("/api/agent/sessions", response_model=SessionOut)
def start_session(
    req: SessionCreateRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == req.category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    try:
        knowledge = get_knowledge_for_training(db, req.category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session = ChatSession(
        user_id=user.id, category_id=req.category_id, status="in_progress"
    )
    db.add(session)
    db.flush()

    # AI 客户开场白
    reply = generate_customer_reply(
        knowledge, history=[], category_name=cat.name,
        turn_count=0, max_turns=settings.max_dialogue_turns,
    )
    reply = _clean_reply(reply)
    db.add(ChatMessage(session_id=session.id, role="customer", content=reply))
    db.commit()
    db.refresh(session)
    return _session_out(session, cat.name)


@app.get("/api/agent/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    s = _get_user_session(db, session_id, user.id)
    cat = db.query(Category).filter(Category.id == s.category_id).first()
    return _session_out(s, cat.name if cat else "")


@app.get("/api/agent/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    s = _get_user_session(db, session_id, user.id)
    return s.messages


@app.post("/api/agent/sessions/{session_id}/messages", response_model=SendMessageReply)
def send_message(
    session_id: int,
    req: SendMessageRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    s = _get_user_session(db, session_id, user.id)
    if s.status == "completed":
        raise HTTPException(status_code=400, detail="训练已结束")
    cat = db.query(Category).filter(Category.id == s.category_id).first()
    knowledge = get_knowledge_for_training(db, s.category_id)

    # 存客服消息
    agent_msg = ChatMessage(session_id=s.id, role="agent", content=req.content)
    db.add(agent_msg)
    db.flush()

    # 计算已完成轮数（客服发言次数）
    history = list(s.messages)  # 含刚加的 agent_msg
    turn_count = sum(1 for m in history if m.role == "agent")

    # 生成 AI 客户回复
    raw = generate_customer_reply(
        knowledge, history=history, category_name=cat.name,
        turn_count=turn_count, max_turns=settings.max_dialogue_turns,
    )

    customer_msg = None
    is_finished = False
    clean = _clean_reply(raw)
    if clean != raw and END_MARKER in raw:
        # 含结束标记
        if clean:
            customer_msg = ChatMessage(session_id=s.id, role="customer", content=clean)
            db.add(customer_msg)
            db.flush()
        is_finished = True
    elif raw.strip() == END_MARKER:
        is_finished = True
    else:
        customer_msg = ChatMessage(session_id=s.id, role="customer", content=clean)
        db.add(customer_msg)
        db.flush()

    # 超过最大轮数
    if turn_count >= settings.max_dialogue_turns:
        is_finished = True

    db.commit()
    if customer_msg:
        db.refresh(customer_msg)
    db.refresh(agent_msg)

    return SendMessageReply(
        agent_message=MessageOut.model_validate(agent_msg, from_attributes=True),
        customer_message=(
            MessageOut.model_validate(customer_msg, from_attributes=True)
            if customer_msg else None
        ),
        is_finished=is_finished,
    )


# ---------- SSE 流式消息端点 (v0.3) ----------

@app.post("/api/agent/sessions/{session_id}/stream")
def stream_message(
    session_id: int,
    req: SendMessageRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """流式发送消息 + 接收 AI 客户回复（SSE）。

    客服发消息 → intent 意图分类 → Quick Reply/Cache/DeepSeek 三层路由
    → 逐字流式输出。前端用 EventSource / fetch+ReadableStream 接收。

    流程：
    1. 存客服消息 → commit
    2. 路由生成客户回复（流式）
    3. 存客户消息到数据库
    4. 流式结束后前端 GET messages 刷新列表
    """
    s = _get_user_session(db, session_id, user.id)
    if s.status == "completed":
        raise HTTPException(status_code=400, detail="训练已结束")

    cat = db.query(Category).filter(Category.id == s.category_id).first()
    knowledge = get_knowledge_for_training(db, s.category_id)
    knowledge_id = s.category_id  # 按 category 维度缓存

    # 存客服消息
    agent_msg = ChatMessage(session_id=s.id, role="agent", content=req.content)
    db.add(agent_msg)
    db.flush()

    history = list(s.messages)  # 含刚加的 agent_msg
    turn_count = sum(1 for m in history if m.role == "agent")

    # 提交客服消息，后续 generator 用独立 session
    db.commit()
    db.refresh(agent_msg)

    def _stream():
        full_reply = ""
        is_finished = False

        # 流式生成客户回复
        for chunk in generate_reply_stream(
            knowledge=knowledge,
            history=history,
            category_name=cat.name if cat else "",
            turn_count=turn_count,
            max_turns=settings.max_dialogue_turns,
            knowledge_id=knowledge_id,
        ):
            if chunk == "[DONE]":
                break
            full_reply += chunk
            yield f"data: {json.dumps({'token': chunk, 'done': False}, ensure_ascii=False)}\n\n"

        # 存储客户消息
        db2 = SessionLocal()
        try:
            clean = full_reply.strip()
            # 检测 END_MARKER（路由可能返回后跟了结束标记）
            if END_MARKER in clean:
                clean = _clean_reply(clean)
                is_finished = True

            if clean:
                cm = ChatMessage(session_id=session_id, role="customer", content=clean)
                db2.add(cm)
                db2.commit()
                db2.refresh(cm)
                msg_id = cm.id
            else:
                msg_id = None

            # 超过最大轮数自动结束
            if turn_count >= settings.max_dialogue_turns:
                is_finished = True

            yield f"data: {json.dumps({'done': True, 'message_id': msg_id, 'turn': turn_count, 'is_finished': is_finished}, ensure_ascii=False)}\n\n"
        finally:
            db2.close()

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/agent/sessions/{session_id}/finish", response_model=FinishReply)
def finish_session(
    session_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    s = _get_user_session(db, session_id, user.id)
    cat = db.query(Category).filter(Category.id == s.category_id).first()

    # 已结束：直接返回已有评分
    if s.status == "completed" and s.score:
        return FinishReply(session=_session_out(s, cat.name if cat else ""),
                           score=_score_out(s.score))

    if s.status == "completed":
        raise HTTPException(status_code=400, detail="训练已结束但无评分")

    turn_count = sum(1 for m in s.messages if m.role == "agent")
    if turn_count < settings.min_dialogue_turns:
        raise HTTPException(
            status_code=400,
            detail=f"至少对话 {settings.min_dialogue_turns} 轮才能结束评分，当前 {turn_count} 轮",
        )

    knowledge = get_knowledge_for_training(db, s.category_id)
    result = evaluate_session(s.messages, knowledge, cat.name)

    score = Score(session_id=s.id, total_score=result["score"], summary=result["summary"])
    score.set_lists(result["advantages"], result["mistakes"], result["suggestions"])
    score.set_dimension_scores(result.get("dimension_scores", {}))
    db.add(score)
    s.status = "completed"
    s.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    db.refresh(score)

    return FinishReply(
        session=_session_out(s, cat.name if cat else ""),
        score=_score_out(score),
    )


@app.get("/api/agent/sessions/{session_id}/score", response_model=ScoreOut)
def get_score(
    session_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    s = _get_user_session(db, session_id, user.id)
    if not s.score:
        raise HTTPException(status_code=404, detail="尚未评分")
    return _score_out(s.score)


# ===================== 辅助函数 =====================


def _categories_with_count(db: Session) -> list[CategoryOut]:
    items = db.query(Category).order_by(Category.id).all()
    result = []
    for cat in items:
        material_count = db.query(Material).filter(Material.category_id == cat.id).count()
        latest = get_latest_knowledge(db, cat.id)
        result.append(
            CategoryOut(
                id=cat.id, name=cat.name, description=cat.description,
                material_count=material_count,
                knowledge_version=latest.version if latest else 0,
            )
        )
    return result


def _knowledge_out(k: Knowledge) -> KnowledgeOut:
    return KnowledgeOut(
        id=k.id, category_id=k.category_id, version=k.version,
        content=k.get_content(), source_material_ids=k.get_source_ids(),
        created_at=k.created_at,
    )


def _session_out(s: ChatSession, category_name: str = "") -> SessionOut:
    return SessionOut(
        id=s.id, category_id=s.category_id, category_name=category_name,
        status=s.status, started_at=s.started_at, ended_at=s.ended_at,
    )


def _score_out(sc: Score) -> ScoreOut:
    return ScoreOut(
        id=sc.id, session_id=sc.session_id, total_score=sc.total_score,
        dimension_scores=sc.get_dimension_scores(),
        advantages=sc.get_advantages(), mistakes=sc.get_mistakes(),
        suggestions=sc.get_suggestions(), summary=sc.summary,
        created_at=sc.created_at,
    )


def _get_user_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    s = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="训练会话不存在")
    return s


def _clean_reply(raw: str) -> str:
    """去掉 END_MARKER 及其后的内容，去掉多余空白。"""
    if not raw:
        return ""
    text = raw.replace(END_MARKER, "").strip()
    return text

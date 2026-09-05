"""kefuxitong 客服训练系统 - FastAPI 入口（v0.3）。

v0.3 核心升级：Intent 三层路由 + 流式输出。
- chat → intent.classify → Quick Reply / Cache / DeepSeek → stream 输出
- 多数轮次毫秒级响应（无需调 LLM），DeepSeek 兜底复杂场景
- SSE 流式传输，前端逐字显示
"""
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from . import batch as batch_svc
from .ai import cache as reply_cache
from .ai import llm, mastery as mastery_svc
from .ai.adaptive import plan_batch
from .ai.evaluator import evaluate_session
from .ai.parser import parse_file, SUPPORTED_EXTENSIONS
from .ai.knowledge import (
    extract_knowledge,
    get_knowledge_for_training,
    get_latest_knowledge,
    PROMPT_VERSION,
)
from .ai.router import generate_reply_stream
from .ai.simulator import END_MARKER, generate_customer_reply, SUMMARY_THRESHOLD, summarize_older
from .auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    require_agent,
    verify_password,
)
from .config import UPLOAD_DIR, settings
from .database import Base, SessionLocal, engine, get_db
from .models import (
    BatchQuestion,
    Category,
    ChatMessage,
    ChatSession,
    Knowledge,
    Material,
    MistakeLog,
    Question,
    QuickReply,
    Score,
    Skill,
    SkillMastery,
    TrainingBatch,
    User,
)
from .schemas import (
    AdminBatchListItem,
    AdminSessionDetail,
    AdminSessionListItem,
    AgentBatchHistoryItem,
    AgentBatchProgress,
    AgentCreate,
    AgentOut,
    AgentPasswordUpdate,
    BatchQuestionOut,
    BatchStartReply,
    BatchStartRequest,
    CategoryCreate,
    CategoryOut,
    ChatImportReply,
    ChatImportRequest,
    ExtractKnowledgeReply,
    ExtractKnowledgeRequest,
    FinishReply,
    KnowledgeOut,
    LoginRequest,
    MasteryListResponse,
    MasteryOut,
    MasteryOverviewResponse,
    MaterialDetailOut,
    MaterialOut,
    MaterialUpdate,
    MessageOut,
    QuestionOut,
    QuestionBindSkill,
    QuestionSyncReply,
    QuickReplyCreate,
    QuickReplyOut,
    QuickReplyUpdate,
    ReviewBatchReply,
    ReviewBatchRequest,
    ScoreOut,
    ScoreTrendsResponse,
    ScoreTrendSeries,
    ScoreTrendPoint,
    SelfPasswordUpdate,
    SendMessageReply,
    SendMessageRequest,
    SessionCreateRequest,
    SessionOut,
    SkillCreate,
    SkillOut,
    SkillUpdate,
    StartQuestionReply,
    TokenResponse,
    TrainingBatchOut,
    TypingStatsOut,
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
        "sales_process": ["确认需求", "推荐材质方案", "报价", "促进成交"],
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
        "sales_process": ["确认需求", "确认材质工艺", "报价", "促进成交"],
    },
}


def init_db():
    """建表并写入默认数据（管理员 + 两个分类 + 示例知识）。"""
    Base.metadata.create_all(bind=engine)
    _migrate_legacy_columns()
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
                k = Knowledge(category_id=cat.id, version=1, prompt_version=PROMPT_VERSION)
                k.set_content(DEFAULT_KNOWLEDGE[name])
                k.set_source_ids([])
                db.add(k)
            # v0.8：写入示例知识点（从示例知识的 required_questions + key_knowledge 生成）
            _seed_skills(db, cat.id, DEFAULT_KNOWLEDGE.get(name, {}))
        # v0.9：写入占位快捷短语（空表才写）
        _seed_quick_replies(db)
        db.commit()
    finally:
        db.close()


def _seed_skills(db: Session, category_id: int, knowledge: dict) -> None:
    """从知识 JSON 生成示例知识点（required_questions + 部分 key_knowledge）。"""
    names = list(knowledge.get("required_questions") or [])
    for kn in (knowledge.get("key_knowledge") or [])[:3]:
        if isinstance(kn, str):
            names.append(kn[:20])
    mastery_svc.ensure_skills_from_knowledge(db, category_id, names, [])


def _migrate_legacy_columns():
    """轻量迁移：旧库补列（不删库）。

    v0.7: chat_session.batch_question_id
    v0.8: question.skill_id / difficulty / related_skill_ids
    """
    try:
        if "chat_session" not in inspect(engine).get_table_names():
            return
        cols = [c["name"] for c in inspect(engine).get_columns("chat_session")]
        if "batch_question_id" not in cols:
            with engine.connect() as conn:
                conn.execute(
                    text("ALTER TABLE chat_session ADD COLUMN batch_question_id INTEGER")
                )
                conn.commit()
    except Exception as e:  # 迁移失败不阻塞启动
        logging.getLogger(__name__).warning("chat_session 迁移失败: %s", e)

    # v0.8: question 补列
    try:
        if "question" not in inspect(engine).get_table_names():
            return
        cols = [c["name"] for c in inspect(engine).get_columns("question")]
        with engine.connect() as conn:
            if "skill_id" not in cols:
                conn.execute(text("ALTER TABLE question ADD COLUMN skill_id INTEGER"))
            if "difficulty" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE question ADD COLUMN difficulty "
                        "VARCHAR(16) DEFAULT 'medium'"
                    )
                )
            if "related_skill_ids" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE question ADD COLUMN related_skill_ids "
                        "TEXT DEFAULT '[]'"
                    )
                )
            conn.commit()
    except Exception as e:  # 迁移失败不阻塞启动
        logging.getLogger(__name__).warning("question 迁移失败: %s", e)

    # v0.9.3: quick_reply 补分组列
    try:
        if "quick_reply" not in inspect(engine).get_table_names():
            return
        cols = [c["name"] for c in inspect(engine).get_columns("quick_reply")]
        with engine.connect() as conn:
            if "group_name" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE quick_reply ADD COLUMN group_name "
                        "VARCHAR(32) DEFAULT '常用回复'"
                    )
                )
                conn.commit()
    except Exception as e:  # 迁移失败不阻塞启动
        logging.getLogger(__name__).warning("quick_reply 迁移失败: %s", e)


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


# ---------- 修改自己的密码（管理员 / 客服通用） ----------
@app.post("/api/auth/change-password")
def change_self_password(
    req: SelfPasswordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前登录用户修改自己的密码，需校验原密码。"""
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")

    new_pwd = (req.new_password or "").strip()
    if len(new_pwd) < 4:
        raise HTTPException(status_code=400, detail="新密码至少 4 位")

    user.password_hash = hash_password(new_pwd)
    db.commit()
    return {"detail": "密码已修改", "username": user.username}


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


@app.put("/api/admin/agents/{agent_id}/password")
def reset_agent_password(
    agent_id: int,
    req: AgentPasswordUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员重置客服密码（无需知道原密码）。

    只作用于 role=agent 的账号，避免误改管理员。
    """
    user = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not user:
        raise HTTPException(status_code=404, detail="客服账号不存在")

    pwd = (req.password or "").strip()
    if len(pwd) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 位")

    user.password_hash = hash_password(pwd)
    db.commit()
    return {"detail": "密码已重置", "id": user.id, "username": user.username}


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
    """删除分类：级联清理材料/知识/题目/知识点/掌握度，避免孤儿数据。

    SQLite 不强制外键，历史 chat_session 的 category_id 会悬空（保留会话记录）。
    """
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    # 该品类题目及其关联（批内题/错题本）
    qids = [
        q.id for q in db.query(Question).filter(Question.category_id == cat_id).all()
    ]
    if qids:
        db.query(BatchQuestion).filter(
            BatchQuestion.question_id.in_(qids)
        ).delete(synchronize_session=False)
        db.query(MistakeLog).filter(
            MistakeLog.question_id.in_(qids)
        ).delete(synchronize_session=False)
        db.query(Question).filter(Question.id.in_(qids)).delete(
            synchronize_session=False
        )
    # 该品类知识点及其掌握度
    skill_ids = [
        s.id for s in db.query(Skill).filter(Skill.category_id == cat_id).all()
    ]
    if skill_ids:
        db.query(SkillMastery).filter(
            SkillMastery.skill_id.in_(skill_ids)
        ).delete(synchronize_session=False)
        db.query(Skill).filter(Skill.id.in_(skill_ids)).delete(
            synchronize_session=False
        )
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
    source_type: str = Form("sales"),
    quality: str = Form("normal"),
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")

    # 资料类型校验
    ALLOWED_SOURCE_TYPES = {"product", "sales", "sop", "training", "faq"}
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"资料类型无效，仅支持 {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
        )

    # 案例类型校验
    ALLOWED_QUALITY = {"excellent", "normal", "failed"}
    if quality not in ALLOWED_QUALITY:
        raise HTTPException(
            status_code=400,
            detail=f"案例类型无效，仅支持 {', '.join(sorted(ALLOWED_QUALITY))}",
        )

    # 文件大小限制（10MB，PPT/PDF 可能较大）
    MAX_FILE_SIZE = 10 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，限制 10MB 以内")

    # 扩展名白名单校验
    raw_name = file.filename or "untitled.txt"
    filename = Path(raw_name).name  # 剥掉路径，防穿越
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：.{ext}，仅支持 {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    file_type = ext

    safe_name = f"{category_id}_{uuid.uuid4().hex[:8]}_{filename}"
    save_path = UPLOAD_DIR / safe_name
    # 二次防御：确认最终路径仍在 UPLOAD_DIR 内
    try:
        save_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    save_path.write_bytes(content)

    # 多格式解析：统一转为纯文本
    try:
        text = parse_file(save_path, file_type)
    except ValueError as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))

    m = Material(
        category_id=category_id,
        filename=filename,
        file_path=str(save_path),
        content_text=text,
        file_type=file_type,
        file_size=len(content),
        quality=quality,
        source_type=source_type,
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

    if req.source_type is not None:
        ALLOWED_SOURCE_TYPES = {"product", "sales", "sop", "training", "faq"}
        if req.source_type not in ALLOWED_SOURCE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"资料类型无效，仅支持 {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
            )
        m.source_type = req.source_type

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


# ---------- 知识点管理（v0.8 掌握度引擎） ----------


@app.get("/api/admin/skills", response_model=list[SkillOut])
def list_skills(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """品类下知识点列表（含绑定题数）。"""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    result = []
    for s in (
        db.query(Skill)
        .filter(Skill.category_id == category_id)
        .order_by(Skill.id)
        .all()
    ):
        q_count = db.query(Question).filter(Question.skill_id == s.id).count()
        result.append(
            SkillOut(
                id=s.id, category_id=s.category_id, name=s.name,
                description=s.description, source=s.source,
                question_count=q_count, created_at=s.created_at,
            )
        )
    return result


@app.post("/api/admin/skills", response_model=SkillOut)
def create_skill(
    category_id: int,
    req: SkillCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新建知识点（手工维护，source=manual）。"""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="知识点名不能为空")
    dup = (
        db.query(Skill)
        .filter(Skill.category_id == category_id, Skill.name == name)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="同名知识点已存在")
    s = Skill(
        category_id=category_id, name=name,
        description=req.description, source="manual",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return SkillOut(
        id=s.id, category_id=s.category_id, name=s.name,
        description=s.description, source=s.source,
        question_count=0, created_at=s.created_at,
    )


@app.put("/api/admin/skills/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    req: SkillUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """改知识点名/描述。"""
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="知识点不存在")
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="知识点名不能为空")
        dup = (
            db.query(Skill)
            .filter(
                Skill.category_id == s.category_id,
                Skill.name == name,
                Skill.id != s.id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=400, detail="同名知识点已存在")
        s.name = name
    if req.description is not None:
        s.description = req.description
    db.commit()
    db.refresh(s)
    q_count = db.query(Question).filter(Question.skill_id == s.id).count()
    return SkillOut(
        id=s.id, category_id=s.category_id, name=s.name,
        description=s.description, source=s.source,
        question_count=q_count, created_at=s.created_at,
    )


@app.delete("/api/admin/skills/{skill_id}")
def delete_skill(
    skill_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除知识点：关联题主知识点置 NULL，掌握度记录删除。"""
    s = db.query(Skill).filter(Skill.id == skill_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="知识点不存在")
    for q in db.query(Question).filter(Question.skill_id == s.id).all():
        q.skill_id = None
    db.query(SkillMastery).filter(SkillMastery.skill_id == s.id).delete()
    db.delete(s)
    db.commit()
    return {"ok": True}


@app.get("/api/admin/mastery-overview", response_model=MasteryOverviewResponse)
def mastery_overview(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """团队掌握度看板：客服×知识点矩阵 + 薄弱知识点排行。"""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    skills = (
        db.query(Skill)
        .filter(Skill.category_id == category_id)
        .order_by(Skill.id)
        .all()
    )
    agents = (
        db.query(User).filter(User.role == "agent").order_by(User.id).all()
    )
    skill_info = [
        SkillOut(
            id=s.id, category_id=s.category_id, name=s.name,
            description=s.description, source=s.source,
            question_count=db.query(Question).filter(Question.skill_id == s.id).count(),
            created_at=s.created_at,
        )
        for s in skills
    ]
    agents_info = [{"id": u.id, "name": u.username} for u in agents]

    rows = []
    skill_ids = [s.id for s in skills]
    if skill_ids:
        mastery_rows = (
            db.query(SkillMastery)
            .filter(SkillMastery.skill_id.in_(skill_ids))
            .all()
        )
        m_map = {(r.user_id, r.skill_id): r for r in mastery_rows}
        name_by_id = {s.id: s.name for s in skills}
        for u in agents:
            for sid in skill_ids:
                r = m_map.get((u.id, sid))
                rows.append(
                    {
                        "user_id": u.id,
                        "username": u.username,
                        "skill_id": sid,
                        "skill_name": name_by_id[sid],
                        "mastery": r.mastery if r else 0.0,
                        "status": r.status if r else "weak",
                    }
                )

    weak_ranking = []
    for s in skills:
        vals = [r["mastery"] for r in rows if r["skill_id"] == s.id]
        avg = round(sum(vals) / len(vals), 1) if vals else 0.0
        weak_cnt = sum(
            1 for r in rows if r["skill_id"] == s.id and r["status"] == "weak"
        )
        weak_ranking.append(
            {
                "skill_id": s.id,
                "skill_name": s.name,
                "avg_mastery": avg,
                "weak_count": weak_cnt,
            }
        )
    weak_ranking.sort(key=lambda x: (x["avg_mastery"], -x["weak_count"]))

    return MasteryOverviewResponse(
        category_id=category_id, category_name=cat.name,
        skills=skill_info, agents=agents_info,
        rows=rows, weak_ranking=weak_ranking,
    )


# ---------- 快捷回复短语（v0.9） ----------

# 初始占位短语（空表时写入；主人提供真实短语后可在管理端增删改）
DEFAULT_QUICK_REPLIES = [
    ("常用回复", "您好，请问有什么可以帮您？"),
    ("常用回复", "好的，请问您需要什么规格？尺寸和厚度大概多少？"),
    ("常用回复", "可以的，我先跟您确认一下需求。"),
    ("常用回复", "这个价格可以谈的，您量大我这边可以帮您申请优惠。"),
    ("常用回复", "交期大概 7-10 个工作日，急单可以另外安排加急。"),
    ("常用回复", "好的，我先去确认一下，稍后回复您。"),
    ("常用回复", "方便留个联系方式吗？让技术同事直接跟您对接。"),
]


def _seed_quick_replies(db: Session) -> None:
    """首次启动写入占位快捷短语（表空才写，避免覆盖管理端数据）。"""
    if db.query(QuickReply).count() > 0:
        return
    for i, (group, content) in enumerate(DEFAULT_QUICK_REPLIES):
        db.add(
            QuickReply(
                content=content,
                group_name=group,
                is_active=1,
                sort_order=i,
            )
        )
    db.commit()


@app.get("/api/admin/quick-replies", response_model=list[QuickReplyOut])
def list_quick_replies(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看全部快捷短语（含停用，按排序）。"""
    rows = (
        db.query(QuickReply).order_by(QuickReply.sort_order, QuickReply.id).all()
    )
    return [
        QuickReplyOut(
            id=r.id,
            content=r.content,
            group_name=r.group_name or "常用回复",
            is_active=bool(r.is_active),
            sort_order=r.sort_order,
            created_at=r.created_at,
        )
        for r in rows
    ]


@app.post("/api/admin/quick-replies", response_model=QuickReplyOut)
def create_quick_reply(
    req: QuickReplyCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """新建快捷短语（追加到末尾）。"""
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="短语内容不能为空")
    group = (req.group_name or "常用回复").strip()[:32] or "常用回复"
    max_order = db.query(QuickReply).count()
    r = QuickReply(
        content=content, group_name=group, is_active=1, sort_order=max_order
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return QuickReplyOut(
        id=r.id, content=r.content, group_name=r.group_name, is_active=True,
        sort_order=r.sort_order, created_at=r.created_at,
    )


@app.put("/api/admin/quick-replies/{qid}", response_model=QuickReplyOut)
def update_quick_reply(
    qid: int,
    req: QuickReplyUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """改短语内容 / 分组 / 启用状态。"""
    r = db.query(QuickReply).filter(QuickReply.id == qid).first()
    if not r:
        raise HTTPException(status_code=404, detail="快捷短语不存在")
    if req.content is not None:
        content = req.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="短语内容不能为空")
        r.content = content
    if req.group_name is not None:
        group = req.group_name.strip()[:32] or "常用回复"
        r.group_name = group
    if req.is_active is not None:
        r.is_active = 1 if req.is_active else 0
    db.commit()
    db.refresh(r)
    return QuickReplyOut(
        id=r.id, content=r.content, group_name=r.group_name,
        is_active=bool(r.is_active),
        sort_order=r.sort_order, created_at=r.created_at,
    )


@app.delete("/api/admin/quick-replies/{qid}")
def delete_quick_reply(
    qid: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    r = db.query(QuickReply).filter(QuickReply.id == qid).first()
    if not r:
        raise HTTPException(status_code=404, detail="快捷短语不存在")
    db.delete(r)
    db.commit()
    return {"detail": "已删除"}


@app.get("/api/agent/quick-replies", response_model=list[QuickReplyOut])
def agent_quick_replies(
    _: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """客服端获取启用中的快捷短语（按排序）。"""
    rows = (
        db.query(QuickReply)
        .filter(QuickReply.is_active == 1)
        .order_by(QuickReply.sort_order, QuickReply.id)
        .all()
    )
    return [
        QuickReplyOut(
            id=r.id,
            content=r.content,
            group_name=r.group_name or "常用回复",
            is_active=True,
            sort_order=r.sort_order,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ---------- 聊天语料导入 ----------

# 清洗规则：要跳过的消息模式
_SKIP_PATTERNS = [
    "欢迎您光临本店",
    "将为您服务",
    "当前用户来自",
    "您有退货包运费",
    "亲，已帮你挑好",
    "请确认收货地址",
    "协商发货时间",
    "协商发货时间已同意",
    "我要咨询这笔订单",
    "亲，您有一笔订单",
    "您直接拍",
    "您直接支付",
    "商品已帮你挑好",
    "付这个",
    "由 小",
    "转交给 小",
]
# 客服名匹配模式
_AGENT_PATTERNS = [
    "中科立得旗舰店:",
    "旗舰店:",
]


def _clean_chat(raw_text: str) -> tuple[str, str]:
    """清洗原始聊天记录，返回 (标准化文本, 标题)。

    处理逻辑：
    1. 检测格式（Tab分隔 / 纯文本），按角色分组
    2. 规则识别角色（客服名含"旗舰店"前缀）
    3. 过滤系统消息、自动回复
    4. 合并连续同角色消息
    5. 隐私脱敏：发送者昵称不输出（仅角色前缀），消息内容中引用的
       昵称统一替换为「客户N/客服N」，手机号打码（保留前3后4）
    """
    lines = raw_text.replace("\r\n", "\n").split("\n")
    lines = [ln.strip() for ln in lines if ln.strip()]

    # 检测是否为 Tab 分隔格式（聊天对象\t聊天内容\t聊天时间）
    messages_raw = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        # 跳过表头
        if ln.startswith("聊天对象") or ln.startswith("聊天内容") or ln.startswith("聊天时间"):
            i += 1
            continue
        # Tab 分隔格式：nick\tcontent\ttimestamp
        parts = ln.split("\t")
        if len(parts) >= 2 and len(parts[0]) < 60:
            nick = parts[0].strip()
            content = parts[1].strip()
            # 跳过时间戳行
            if len(nick) >= 19 and nick[4] == "-":
                i += 1
                continue
            # 跳过系统消息、卡片、链接
            if content.startswith("http") or content.startswith("【卡片"):
                i += 1
                continue
            messages_raw.append((nick, content))
        else:
            # 非Tab格式：可能是普通文本行
            # 跳过时间戳
            if len(ln) >= 19 and ln[4] == "-":
                i += 1
                continue
            # 尝试作为角色名行处理
            is_nick = any(p in ln for p in _AGENT_PATTERNS) or (len(ln) < 30 and "旗舰店" not in ln)
            if is_nick:
                nick = ln
                content = ""
                if i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if not (len(nxt) >= 19 and nxt[4] == "-"):
                        content = nxt
                        i += 1
                if content:
                    messages_raw.append((nick, content))
        i += 1

    # ---- 隐私脱敏：昵称 → 客户N/客服N 映射（内容中的引用也替换）----
    # 1) 判定每个发送者昵称的角色
    nick_to_role = {}
    for nick, _ in messages_raw:
        if nick not in nick_to_role:
            nick_to_role[nick] = "客服" if any(p in nick for p in _AGENT_PATTERNS) else "客户"
    # 2) 分配脱敏名（同一昵称全程一致；首个客服 = "客服"，其余编号）
    customer_no = 0
    agent_no = 0
    nick_map: dict[str, str] = {}
    for nick, role in nick_to_role.items():
        if role == "客服":
            agent_no += 1
            nick_map[nick] = "客服" if agent_no == 1 else f"客服{agent_no}"
        else:
            customer_no += 1
            nick_map[nick] = f"客户{customer_no}"
    # 3) 补充：去掉"旗舰店:"前缀的客服名也映射到同一脱敏名（内容里可能只引用后半段）
    for nick, masked in list(nick_map.items()):
        short = nick.split(":")[-1].strip()
        if short and short != nick and short not in nick_map:
            nick_map[short] = masked
    # 长昵称优先替换，避免短昵称误伤长昵称
    ordered_nicks = sorted((n for n in nick_map if n), key=len, reverse=True)

    def desensitize(text: str) -> str:
        for nick in ordered_nicks:
            if nick in text:
                text = text.replace(nick, nick_map[nick])
        # 手机号打码：保留前3后4（如 138****5678）
        text = re.sub(
            r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)", r"\1****\2", text
        )
        return text

    # 过滤 + 合并
    merged = []
    for nick, content in messages_raw:
        # 跳过系统自动回复
        skip = False
        for pat in _SKIP_PATTERNS:
            if pat in content:
                skip = True
                break
        if skip:
            continue
        if content.startswith("http"):
            content = "[图片/文件]"

        # 判断角色
        role = nick_to_role.get(nick, "客户")
        # 脱敏：内容中的昵称引用替换 + 手机号打码
        content = desensitize(content)
        line = f"{role}：{content}"

        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + "\n" + line)
        else:
            merged.append((role, line))

    chat_text = "\n".join(msg for _, msg in merged)

    # 生成标题
    title = "聊天语料导入"
    if merged:
        first = merged[0][1].split("\n")[0]
        title = first[:60]

    return chat_text, title


def _detect_result(chat_text: str) -> str:
    """根据对话内容推断成交结果（简单规则）。"""
    text_lower = chat_text.lower()
    # 已成交信号
    deal_signals = [
        "下单了", "已下单", "付了", "支付", "成交", "好的，下单",
        "提交", "就按这个付", "直接拍", "下单后", "下单",
    ]
    # 未成交信号
    fail_signals = [
        "再考虑", "再看看", "太贵了", "算了", "不做了",
        "好吧", "嗯呢",
    ]
    deal_count = sum(1 for s in deal_signals if s in chat_text)
    fail_count = sum(1 for s in fail_signals if s in chat_text)
    if deal_count > fail_count:
        return "excellent"
    if fail_count > deal_count:
        return "failed"
    return "normal"


@app.post("/api/admin/import-chat", response_model=ChatImportReply)
def import_chat(
    req: ChatImportRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """导入原始聊天记录：清洗 → 角色识别 → 入库 → LLM 提取。

    自动完成格式化，不必人工整理。
    """
    # 验证品类
    cat = db.query(Category).filter(Category.id == req.category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")

    # 验证 quality
    if req.quality not in ("excellent", "normal", "failed"):
        raise HTTPException(status_code=400, detail="质量标记无效，仅支持 excellent/normal/failed")

    # 清洗
    chat_text, title = _clean_chat(req.raw_text)

    # 如果用户未标注 quality，自动检测
    quality = req.quality
    if quality == "excellent" and "excellent" not in req.raw_text.lower():
        detected = _detect_result(chat_text)
        if detected != "excellent":
            quality = detected

    # 生成文件名
    fname = f"{uuid.uuid4().hex[:8]}_chat_import.txt"
    save_path = UPLOAD_DIR / fname
    save_path.write_text(chat_text, encoding="utf-8")

    # 创建 Material
    m = Material(
        category_id=req.category_id,
        filename=title[:80],
        file_path=str(save_path),
        content_text=chat_text,
        file_type="txt",
        file_size=len(chat_text.encode("utf-8")),
        quality=quality,
        source_type="sales",
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    # 触发 LLM 提取
    k, used_llm = extract_knowledge(db, req.category_id)
    content = k.get_content()

    # 提取模式摘要
    patterns = []
    for sp in content.get("success_patterns", []):
        patterns.append(f"[成功] {sp.get('scenario', '')}")
    for fp in content.get("failure_patterns", []):
        patterns.append(f"[失败] {fp.get('scenario', '')}")

    return ChatImportReply(
        material=MaterialOut.model_validate(m, from_attributes=True),
        knowledge_version=k.version,
        used_llm=used_llm,
        success_count=len(content.get("success_patterns", [])),
        failure_count=len(content.get("failure_patterns", [])),
        extracted_patterns=patterns,
    )


# ---------- 训练成绩（管理员） ----------
# ---------- 管理员：题库与批次判定（v0.7 错题本闭环） ----------


@app.get("/api/admin/questions", response_model=list[QuestionOut])
def list_questions(
    category_id: int = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """题库列表（可按品类过滤）。"""
    q = db.query(Question)
    if category_id:
        q = q.filter(Question.category_id == category_id)
    return [_question_out(x) for x in q.order_by(Question.id.desc()).all()]


@app.post("/api/admin/questions/sync", response_model=QuestionSyncReply)
def sync_questions_api(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把该品类已上传的 sales 聊天记录补转为题目。"""
    created = batch_svc.sync_questions(db, category_id)
    total = db.query(Question).filter(Question.category_id == category_id).count()
    return QuestionSyncReply(created=created, total=total)


@app.put("/api/admin/questions/{qid}/bind-skill", response_model=QuestionOut)
def bind_question_skill(
    qid: int,
    req: QuestionBindSkill,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """题目绑定/解绑知识点 + 设置难度（v0.8 补：旧题手动归类入口）。

    skill_id 为空 = 解绑；difficulty 仅接受 easy/medium/hard。
    """
    q = db.query(Question).filter(Question.id == qid).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    if req.skill_id is not None:
        s = (
            db.query(Skill)
            .filter(Skill.id == req.skill_id, Skill.category_id == q.category_id)
            .first()
        )
        if not s:
            raise HTTPException(
                status_code=400, detail="知识点不存在或不属于该品类"
            )
        q.skill_id = s.id
    else:
        q.skill_id = None
    if req.difficulty in ("easy", "medium", "hard"):
        q.difficulty = req.difficulty
    db.commit()
    db.refresh(q)
    return _question_out(q)


@app.get("/api/admin/batches", response_model=list[AdminBatchListItem])
def list_batches(
    user_id: int = None,
    status: str = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """批次列表（可按客服/状态筛选）。"""
    q = db.query(TrainingBatch)
    if user_id:
        q = q.filter(TrainingBatch.user_id == user_id)
    if status:
        q = q.filter(TrainingBatch.status == status)
    result = []
    for b in q.order_by(TrainingBatch.id.desc()).all():
        u = db.query(User).filter(User.id == b.user_id).first()
        cat = db.query(Category).filter(Category.id == b.category_id).first()
        reviewed_count = sum(1 for bq in b.items if bq.review_status != "pending")
        result.append(
            AdminBatchListItem(
                id=b.id, user_id=b.user_id, username=u.username if u else "",
                category_id=b.category_id, category_name=cat.name if cat else "",
                status=b.status, question_count=b.question_count,
                reviewed_count=reviewed_count,
                created_at=b.created_at, reviewed_at=b.reviewed_at,
            )
        )
    return result


@app.get("/api/admin/batches/{batch_id}", response_model=TrainingBatchOut)
def admin_batch_detail(
    batch_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """批次详情（20 题 + 会话/评分摘要 + 判定状态）。"""
    b = db.query(TrainingBatch).filter(TrainingBatch.id == batch_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    return _batch_out(db, b, b.user_id)


@app.post("/api/admin/batches/{batch_id}/review", response_model=ReviewBatchReply)
def review_batch_api(
    batch_id: int,
    req: ReviewBatchRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """主管判定：逐题点合适/不合适。不合适进错题本，合适解错题。"""
    try:
        changed = batch_svc.review_batch(
            db,
            batch_id,
            [{"question_id": i.question_id, "passed": i.passed} for i in req.items],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    b = db.query(TrainingBatch).filter(TrainingBatch.id == batch_id).first()
    return ReviewBatchReply(batch=_batch_out(db, b, b.user_id), mistakes_updated=changed)


@app.get("/api/admin/sessions", response_model=list[AdminSessionListItem])
def admin_list_sessions(
    user_id: int | None = None,
    category_id: int | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看训练记录列表（含分数摘要）。

    可按 user_id / category_id 过滤。按 id 倒序（最新在前）。
    v0.11: 聚合键入统计（avg_cpm / avg_response_ms / quick_reply_ratio / typing_samples）。
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
        msgs = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).all()
        msg_count = len(msgs)
        score_total = s.score.total_score if s.score else None
        score_summary = s.score.summary if s.score else ""

        # v0.11 聚合
        agent_msgs = [m for m in msgs if m.role == "agent"]
        valid_msgs = [
            m for m in agent_msgs
            if (m.keystroke_count or 0) >= 3
            and (m.char_count or 0) >= 5
            and not m.is_paste
            and m.typed_duration_ms
            and m.typed_duration_ms > 0
            and m.char_count
        ]
        cpms = [_compute_cpm(m.char_count, m.typed_duration_ms)
                for m in valid_msgs]
        cpms = [c for c in cpms if c is not None and c > 0]
        avg_cpm = round(sum(cpms) / len(cpms), 1) if cpms else None
        resp = [m.response_duration_ms for m in agent_msgs
                if m.response_duration_ms is not None
                and 0 <= m.response_duration_ms < 10 * 60 * 1000]
        avg_resp = int(sum(resp) / len(resp)) if resp else None
        qr_count = sum(1 for m in agent_msgs if m.is_quick_reply)
        qr_ratio = round(qr_count / len(agent_msgs), 2) if agent_msgs else None

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
                avg_cpm=avg_cpm,
                avg_response_ms=avg_resp,
                quick_reply_ratio=qr_ratio,
                typing_samples=len(valid_msgs),
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
        conversation_summary=s.conversation_summary or "",
        messages=[_msg_out(m) for m in s.messages],
        score=_score_out(s.score) if s.score else None,
    )


@app.get("/api/admin/score-trends", response_model=ScoreTrendsResponse)
def admin_score_trends(
    user_id: int | None = None,
    category_id: int | None = None,
    days: int = 90,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员查看训练成绩成长趋势。

    按 (客服 × 分类) 聚合每次评分的时间序列，输出分数走势与成长方向。
    可按时段（最近 days 天，默认 90）、客服、分类过滤。
    """
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))

    q = (
        db.query(Score, ChatSession, User, Category)
        .join(ChatSession, Score.session_id == ChatSession.id)
        .join(User, ChatSession.user_id == User.id)
        .join(Category, ChatSession.category_id == Category.id)
        .filter(ChatSession.ended_at.isnot(None))
        .filter(ChatSession.ended_at >= cutoff)
    )
    if user_id:
        q = q.filter(ChatSession.user_id == user_id)
    if category_id:
        q = q.filter(ChatSession.category_id == category_id)
    rows = q.order_by(ChatSession.ended_at.asc()).all()

    # 按 (user_id, category_id) 分组
    grouped: dict[tuple[int, int], dict] = {}
    for sc, s, u, c in rows:
        key = (s.user_id, s.category_id)
        grp = grouped.setdefault(
            key,
            {
                "user_id": s.user_id,
                "username": u.username,
                "category_id": s.category_id,
                "category_name": c.name,
                "points": [],
            },
        )
        d = s.ended_at or sc.created_at
        grp["points"].append(
            ScoreTrendPoint(
                date=d.strftime("%Y-%m-%d"),
                session_id=s.id,
                total_score=sc.total_score,
                dimension_scores=sc.get_dimension_scores(),
            )
        )

    # 汇总每条序列的首/末分、成长方向与次数
    series: list[ScoreTrendSeries] = []
    for key, grp in grouped.items():
        pts = sorted(grp["points"], key=lambda p: p.date)
        scores = [p.total_score for p in pts]
        first = scores[0] if scores else None
        latest = scores[-1] if scores else None
        count = len(scores)
        if count >= 2:
            delta = round(latest - first, 1)
            trend = "up" if latest > first else ("down" if latest < first else "flat")
        else:
            delta = 0.0
            trend = "flat"
        series.append(
            ScoreTrendSeries(
                user_id=grp["user_id"],
                username=grp["username"],
                category_id=grp["category_id"],
                category_name=grp["category_name"],
                points=pts,
                first_score=first,
                latest_score=latest,
                delta=delta,
                trend=trend,
                count=count,
            )
        )

    series.sort(key=lambda x: (x.username, x.category_name))

    users = [
        {"id": u.id, "name": u.username}
        for u in db.query(User).filter(User.role == "agent").order_by(User.id).all()
    ]
    categories = [
        {"id": c.id, "name": c.name}
        for c in db.query(Category).order_by(Category.id).all()
    ]

    return ScoreTrendsResponse(users=users, categories=categories, series=series)


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


@app.get("/api/agent/mastery", response_model=MasteryListResponse)
def agent_mastery(
    category_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """客服个人掌握度图谱（某品类，按掌握度升序）。"""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    skills = (
        db.query(Skill)
        .filter(Skill.category_id == category_id)
        .order_by(Skill.id)
        .all()
    )
    m_map = mastery_svc.skill_mastery_map(db, user.id, category_id)
    items = []
    for s in skills:
        r = m_map.get(s.id)
        items.append(
            MasteryOut(
                skill_id=s.id,
                skill_name=s.name,
                mastery=r.mastery if r else 0.0,
                status=r.status if r else "weak",
                attempt_count=r.attempt_count if r else 0,
                reject_count=r.reject_count if r else 0,
                last_judged_at=r.last_judged_at if r else None,
            )
        )
    items.sort(key=lambda x: x.mastery)
    return MasteryListResponse(
        category_id=category_id,
        category_name=cat.name,
        items=items,
        weak_count=sum(1 for i in items if i.status == "weak"),
        pass_count=sum(1 for i in items if i.status == "pass"),
        master_count=sum(1 for i in items if i.status == "master"),
    )


# ---------- 错题本批次训练（v0.7） ----------


@app.get("/api/agent/batch-progress", response_model=AgentBatchProgress)
def batch_progress(
    user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    """客服训练进度：当前批次状态 + 错题本数量 + 能否开新批。"""
    batch = batch_svc.latest_batch(db, user.id)
    if not batch:
        return AgentBatchProgress(has_batch=False, can_start_new=True)
    done_count = sum(
        1
        for bq in batch.items
        if bq.session_id
        and (
            db.query(ChatSession).filter(ChatSession.id == bq.session_id).first().status
            == "completed"
        )
    )
    mistake_count = batch_svc.count_unresolved_mistakes(db, user.id)
    # 找该批首个 in_progress session，用于前端一键续接
    active_session_id = None
    for bq in sorted(batch.items, key=lambda x: x.seq):
        if bq.session_id is None:
            continue
        s = db.query(ChatSession).filter(ChatSession.id == bq.session_id).first()
        if s and s.status == "in_progress":
            active_session_id = s.id
            break
    return AgentBatchProgress(
        has_batch=True,
        batch=_batch_out(db, batch, user.id),
        done_count=done_count,
        mistake_count=mistake_count,
        can_start_new=batch.status == "reviewed",
        active_session_id=active_session_id,
    )


@app.post("/api/agent/batches", response_model=BatchStartReply)
def start_batch(
    req: BatchStartRequest,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """开新批：组卷 20 题（错题间隔混入）。有未完成/未判定批次时禁止开新批。"""
    active = (
        db.query(TrainingBatch)
        .filter(
            TrainingBatch.user_id == user.id,
            TrainingBatch.status.in_(["in_progress", "awaiting_review"]),
        )
        .first()
    )
    if active:
        raise HTTPException(
            status_code=400, detail="还有未练完或未判定的批次，请先完成再开新一批"
        )
    cat = db.query(Category).filter(Category.id == req.category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    try:
        batch = batch_svc.create_batch(db, user.id, req.category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BatchStartReply(batch=_batch_out(db, batch, user.id))


@app.get("/api/agent/batches", response_model=list[AgentBatchHistoryItem])
def list_my_batches(
    user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    """客服自己的批次历史列表（含所有状态），按 id 倒序。

    用于客服查看已练完/已判定的批次，避免退出后再也找不到。
    """
    batches = (
        db.query(TrainingBatch)
        .filter(TrainingBatch.user_id == user.id)
        .order_by(TrainingBatch.id.desc())
        .all()
    )
    result = []
    for b in batches:
        cat = db.query(Category).filter(Category.id == b.category_id).first()
        done_count = sum(
            1
            for bq in b.items
            if bq.session_id
            and (
                db.query(ChatSession)
                .filter(ChatSession.id == bq.session_id)
                .first()
                .status
                == "completed"
            )
        )
        # 最近一条 in_progress session（用于续接）
        active_session_id = None
        for bq in sorted(b.items, key=lambda x: x.seq):
            if bq.session_id is None:
                continue
            s = (
                db.query(ChatSession)
                .filter(ChatSession.id == bq.session_id)
                .first()
            )
            if s and s.status == "in_progress":
                active_session_id = s.id
                break
        result.append(
            AgentBatchHistoryItem(
                id=b.id,
                category_id=b.category_id,
                category_name=cat.name if cat else "",
                status=b.status,
                question_count=b.question_count,
                done_count=done_count,
                created_at=b.created_at,
                reviewed_at=b.reviewed_at,
                active_session_id=active_session_id,
            )
        )
    return result


@app.get("/api/agent/batches/{batch_id}", response_model=TrainingBatchOut)
def get_batch(
    batch_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    b = (
        db.query(TrainingBatch)
        .filter(TrainingBatch.id == batch_id, TrainingBatch.user_id == user.id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    return _batch_out(db, b, user.id)


@app.post("/api/agent/batches/{batch_id}/start-question", response_model=StartQuestionReply)
def start_batch_question(
    batch_id: int, user: User = Depends(require_agent), db: Session = Depends(get_db)
):
    """开始批内下一道未做的题：创建训练会话，AI 客户按本题剧本开场。"""
    b = (
        db.query(TrainingBatch)
        .filter(TrainingBatch.id == batch_id, TrainingBatch.user_id == user.id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="批次不存在")
    if b.status == "awaiting_review":
        raise HTTPException(status_code=400, detail="本批已练完，等待主管判定")
    if b.status == "reviewed":
        raise HTTPException(status_code=400, detail="本批已判定完，请开新一批")

    session, question, bq = batch_svc.start_question(db, b, user.id)
    if not session:
        batch_svc.refresh_batch_status(db, b)
        raise HTTPException(400, detail="本批题目已全部开始")

    cat = db.query(Category).filter(Category.id == b.category_id).first()
    # 判断是新建还是续接：续接时不再加 AI 开场白，避免重复
    existing_msg_count = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .count()
    )
    if existing_msg_count == 0:
        knowledge = get_knowledge_for_training(db, b.category_id)
        reply = generate_customer_reply(
            knowledge,
            history=[],
            category_name=cat.name if cat else "",
            turn_count=0,
            max_turns=settings.max_dialogue_turns,
            question_script=question.script_text if question else "",
        )
        reply = _clean_reply(reply)
        db.add(ChatMessage(session_id=session.id, role="customer", content=reply))
        db.commit()
        db.refresh(session)

    return StartQuestionReply(
        session=_session_out(session, cat.name if cat else ""),
        question=_question_out(question),
        seq=bq.seq,
        total=b.question_count,
        is_mistake=batch_svc.is_mistake(db, user.id, question.id),
        batch_status=b.status,
    )


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
    return [_msg_out(m) for m in s.messages]


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

    # 找上一条 customer 消息（用于算 response_duration）
    prev_customer = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == s.id, ChatMessage.role == "customer")
        .order_by(ChatMessage.id.desc())
        .first()
    )
    prev_customer_at = prev_customer.created_at if prev_customer else None

    # 存客服消息（created_at 即为 send_at）
    agent_msg = ChatMessage(session_id=s.id, role="agent", content=req.content)
    db.add(agent_msg)
    db.flush()  # 先拿到 id 与 created_at，再写 typing 字段

    # v0.11: 应用键入统计
    _apply_typing_metrics(agent_msg, req.typing_metrics, prev_customer_at)

    # 计算已完成轮数（客服发言次数）
    history = list(s.messages)  # 含刚加的 agent_msg
    turn_count = sum(1 for m in history if m.role == "agent")

    # 长对话摘要：压缩传给 LLM 的上下文（超过阈值时生效）
    summary = _compute_summary(s, cat.name if cat else "")
    s.conversation_summary = summary

    # 生成 AI 客户回复（批次题绑定剧本时按剧本衍生扮演）
    raw = generate_customer_reply(
        knowledge, history=history, category_name=cat.name,
        turn_count=turn_count, max_turns=settings.max_dialogue_turns,
        conversation_summary=summary,
        question_script=_session_question_script(db, s),
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
        agent_message=_msg_out(agent_msg),
        customer_message=(
            _msg_out(customer_msg)
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

    # 找上一条 customer 消息（用于算 response_duration）
    prev_customer = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == s.id, ChatMessage.role == "customer")
        .order_by(ChatMessage.id.desc())
        .first()
    )
    prev_customer_at = prev_customer.created_at if prev_customer else None

    # 存客服消息（created_at 即 send_at）
    agent_msg = ChatMessage(session_id=s.id, role="agent", content=req.content)
    db.add(agent_msg)
    db.flush()  # 先拿到 created_at，再写 typing 字段

    # v0.11: 应用键入统计
    _apply_typing_metrics(agent_msg, req.typing_metrics, prev_customer_at)

    history = list(s.messages)  # 含刚加的 agent_msg
    turn_count = sum(1 for m in history if m.role == "agent")

    # 长对话摘要：压缩传给 LLM 的上下文（超过阈值时生效）
    summary = _compute_summary(s, cat.name if cat else "")
    s.conversation_summary = summary

    # 剧本必须在闭包外取（db 在请求结束后会关闭，生成器内再访问会失效）
    question_script = _session_question_script(db, s)

    # 提交客服消息（含 typing 字段），后续 generator 用独立 session
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
            conversation_summary=summary,
            question_script=question_script,
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
    result = evaluate_session(
        s.messages, knowledge, cat.name, conversation_summary=s.conversation_summary or ""
    )

    score = Score(session_id=s.id, total_score=result["score"], summary=result["summary"])
    score.set_lists(result["advantages"], result["mistakes"], result["suggestions"])
    score.set_dimension_scores(result.get("dimension_scores", {}))
    scoring_dims = result.get("scoring_dimensions", {})  # per-category 维度定义
    score.set_scoring_dimensions(scoring_dims)
    db.add(score)
    s.status = "completed"
    s.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    db.refresh(score)

    # 批次题完成 → 刷新批次状态（20 题练完 → awaiting_review）
    if s.batch_question_id:
        bq = (
            db.query(BatchQuestion)
            .filter(BatchQuestion.id == s.batch_question_id)
            .first()
        )
        if bq:
            batch = (
                db.query(TrainingBatch)
                .filter(TrainingBatch.id == bq.batch_id)
                .first()
            )
            if batch:
                batch_svc.refresh_batch_status(db, batch)

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
        prompt_version=k.prompt_version,
        content=k.get_content(), source_material_ids=k.get_source_ids(),
        created_at=k.created_at,
    )


def _session_out(s: ChatSession, category_name: str = "") -> SessionOut:
    return SessionOut(
        id=s.id, category_id=s.category_id, category_name=category_name,
        status=s.status, started_at=s.started_at, ended_at=s.ended_at,
    )


# ===================== v0.11 键入统计辅助 =====================


def _compute_cpm(char_count: Optional[int], typed_duration_ms: Optional[int]) -> Optional[float]:
    """CPM = 字 / 分钟。typed_duration_ms <= 0 或 char_count 缺失 → None。"""
    if char_count is None or typed_duration_ms is None or typed_duration_ms <= 0:
        return None
    return round(char_count / typed_duration_ms * 60 * 1000, 1)


def _typing_stats_from_msg(m: ChatMessage) -> Optional[TypingStatsOut]:
    """仅客服消息（agent）有意义；AI 客户消息统一返回 None。"""
    if m.role != "agent":
        return None
    stats = TypingStatsOut(
        keystroke_count=m.keystroke_count,
        char_count=m.char_count,
        is_paste=m.is_paste,
        is_quick_reply=m.is_quick_reply,
        typed_duration_ms=m.typed_duration_ms,
        response_duration_ms=m.response_duration_ms,
        cpm=_compute_cpm(m.char_count, m.typed_duration_ms),
    )
    # 全部字段都 None 时返回 None，让前端省着渲染
    return stats if any([
        m.keystroke_count is not None,
        m.char_count is not None,
        m.is_paste is not None,
        m.is_quick_reply is not None,
        m.typed_duration_ms is not None,
        m.response_duration_ms is not None,
    ]) else None


def _msg_out(m: ChatMessage) -> MessageOut:
    """统一构造 MessageOut，带 typing 字段。"""
    return MessageOut(
        id=m.id, role=m.role, content=m.content, created_at=m.created_at,
        typing=_typing_stats_from_msg(m),
    )


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    """前端 ISO 时间字符串 → datetime 对象（兼容 'Z' 后缀）。None → None。"""
    if not s:
        return None
    try:
        # 'Z' → '+00:00' 给 fromisoformat
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        # 统一转为 naive UTC（项目用 datetime.utcnow）
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _apply_typing_metrics(
    msg: ChatMessage,
    metrics,
    prev_customer_msg_created_at: Optional[datetime],
) -> None:
    """把前端上报的 typing_metrics 写入 ChatMessage，并自动算 typed/response duration。

    前端传 ISO 字符串，后端自己算耗时，避免时区误差。
    response_duration = msg.created_at(≈ send_at) - 上一条 customer 消息时间。
    """
    if metrics is None:
        return
    fk = _parse_iso_dt(metrics.first_keystroke_at)
    lk = _parse_iso_dt(metrics.last_keystroke_at)
    msg.first_keystroke_at = fk
    msg.last_keystroke_at = lk
    if metrics.keystroke_count is not None:
        msg.keystroke_count = max(0, int(metrics.keystroke_count))
    if metrics.char_count is not None:
        msg.char_count = max(0, int(metrics.char_count))
    if metrics.is_paste is not None:
        msg.is_paste = bool(metrics.is_paste)
    if metrics.is_quick_reply is not None:
        msg.is_quick_reply = bool(metrics.is_quick_reply)

    # typed_duration：last - first（毫秒）
    if fk and lk and lk >= fk:
        msg.typed_duration_ms = int((lk - fk).total_seconds() * 1000)
    else:
        msg.typed_duration_ms = None

    # response_duration：上一条 customer 消息到这条 agent 消息（毫秒）
    if prev_customer_msg_created_at and msg.created_at:
        delta = msg.created_at - prev_customer_msg_created_at
        # 数据库存了 created_at（commit 前的）就直接用；用毫秒
        msg.response_duration_ms = max(0, int(delta.total_seconds() * 1000))
    else:
        msg.response_duration_ms = None


def _score_out(sc: Score) -> ScoreOut:
    return ScoreOut(
        id=sc.id, session_id=sc.session_id, total_score=sc.total_score,
        dimension_scores=sc.get_dimension_scores(),
        scoring_dimensions=sc.get_scoring_dimensions(),
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


def _session_question_script(db: Session, session) -> str:
    """取会话绑定的题目剧本（旧会话无绑定返回空串）。"""
    if not session.batch_question_id:
        return ""
    bq = (
        db.query(BatchQuestion)
        .filter(BatchQuestion.id == session.batch_question_id)
        .first()
    )
    if not bq:
        return ""
    q = db.query(Question).filter(Question.id == bq.question_id).first()
    return q.script_text if q else ""


def _question_out(q: Question) -> QuestionOut:
    cat_name = q.category.name if q.category else ""
    skill_name = q.skill.name if q.skill else ""
    return QuestionOut(
        id=q.id, category_id=q.category_id, category_name=cat_name,
        title=q.title, scenario=q.scenario, script_text=q.script_text,
        source_type=q.source_type, source_material_id=q.source_material_id,
        skill_id=q.skill_id, skill_name=skill_name,
        difficulty=q.difficulty or "medium",
        created_at=q.created_at,
    )


def _batch_question_out(
    db: Session, bq: BatchQuestion, user_id: int
) -> "BatchQuestionOut":
    q = bq.question
    score_total = None
    session_status = ""
    if bq.session_id:
        s = db.query(ChatSession).filter(ChatSession.id == bq.session_id).first()
        if s:
            session_status = s.status
            if s.score:
                score_total = s.score.total_score
    return BatchQuestionOut(
        id=bq.id, seq=bq.seq, question_id=bq.question_id,
        question_title=q.title if q else "",
        is_mistake=batch_svc.is_mistake(db, user_id, bq.question_id),
        session_id=bq.session_id, session_status=session_status,
        score_total=score_total, review_status=bq.review_status,
        reviewed_at=bq.reviewed_at,
    )


def _batch_out(db: Session, batch: TrainingBatch, user_id: int) -> TrainingBatchOut:
    cat = db.query(Category).filter(Category.id == batch.category_id).first()
    return TrainingBatchOut(
        id=batch.id, user_id=batch.user_id, category_id=batch.category_id,
        category_name=cat.name if cat else "",
        status=batch.status, question_count=batch.question_count,
        created_at=batch.created_at, reviewed_at=batch.reviewed_at,
        items=[_batch_question_out(db, bq, user_id) for bq in batch.items],
    )


def _clean_reply(raw: str) -> str:
    """去掉 END_MARKER 及其后的内容，去掉多余空白。"""
    if not raw:
        return ""
    text = raw.replace(END_MARKER, "").strip()
    return text


def _compute_summary(session, category_name: str) -> str:
    """长对话时生成/增量更新历史摘要，供后续生成与最终评分压缩 LLM 上下文。

    仅当配置了 LLM 且消息数超过 SUMMARY_THRESHOLD 才调用；否则沿用已有摘要。
    """
    if not llm.is_llm_enabled():
        return session.conversation_summary or ""
    msgs = list(session.messages)
    if len(msgs) <= SUMMARY_THRESHOLD:
        return session.conversation_summary or ""
    return summarize_older(msgs, session.conversation_summary or "", category_name)

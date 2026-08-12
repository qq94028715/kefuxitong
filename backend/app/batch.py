"""训练批次服务（错题本闭环，v0.7）。

核心机制：
- 题库 = 该品类已上传的 sales 聊天记录自动转题目（sync_questions）
- 组卷：错题本未解决题「间隔型」均匀混入 + 题库随机补齐，默认一批 20 题
- 批次状态机：in_progress → awaiting_review（20 题练完） → reviewed（主管判定完）
- 判定：不合适 → 进错题本（appear_count+1）；合适 → 解错题（resolved_at 置位）

设计约束：
- 不删旧库：新表由 create_all 建，chat_session.batch_question_id 由 main.init_db 迁移
- 错题按间隔均匀分散，不连续出现（类似错题本，避免连刷同一题）
"""
import random
from datetime import datetime

from sqlalchemy.orm import Session

from .models import (
    BatchQuestion,
    ChatSession,
    Material,
    MistakeLog,
    Question,
    TrainingBatch,
)

BATCH_SIZE = 20  # 每批题数（默认 20 题）
MISTAKE_PER_BATCH = 5  # 每批混入错题数上限（25%）
MIN_QUESTIONS_TO_START = 1  # 题库至少多少题才能开批


# ---------- 题库同步 ----------


def sync_questions(db: Session, category_id: int) -> int:
    """把该品类未转题的 sales 聊天记录补转为题目，返回新建数。"""
    existing = {
        q.source_material_id
        for q in db.query(Question).filter(
            Question.category_id == category_id,
            Question.source_material_id.isnot(None),
        )
    }
    mats = (
        db.query(Material)
        .filter(
            Material.category_id == category_id,
            Material.source_type == "sales",
        )
        .all()
    )
    created = 0
    for m in mats:
        if m.id in existing:
            continue
        db.add(
            Question(
                category_id=category_id,
                source_material_id=m.id,
                title=_make_title(m),
                scenario=_make_scenario(m.content_text),
                script_text=m.content_text or "",
                source_type="uploaded",
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def _make_title(m: Material) -> str:
    name = (m.filename or "").rsplit(".", 1)[0].strip()
    if name:
        return name
    quality = {"excellent": "成交案例", "failed": "未成交案例"}.get(m.quality, "聊天记录")
    return f"{quality} #{m.id}"


def _make_scenario(text: str) -> str:
    """从聊天记录里提炼一句场景描述（取客户第一条非空消息，截 60 字）。"""
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sep in ("：", ":", "】", "|"):
            if sep in line:
                return line.split(sep, 1)[-1].strip()[:60]
        return line[:60]
    return ""


# ---------- 组卷 ----------


def create_batch(db: Session, user_id: int, category_id: int) -> TrainingBatch:
    """开新批：错题间隔混入 + 题库补齐，默认一批 20 题。

    Raises: ValueError 当该品类题库为空。
    """
    sync_questions(db, category_id)

    # 1) 错题本未解决题目（该品类）
    mistake_qids = [
        ml.question_id
        for ml in (
            db.query(MistakeLog)
            .join(Question, MistakeLog.question_id == Question.id)
            .filter(
                MistakeLog.user_id == user_id,
                MistakeLog.resolved_at.is_(None),
                Question.category_id == category_id,
            )
            .all()
        )
    ]

    # 2) 备选题：该品类全部题目
    all_qs = db.query(Question).filter(Question.category_id == category_id).all()
    if len(all_qs) < MIN_QUESTIONS_TO_START:
        raise ValueError("该品类暂无训练题目，请先在「导入语料」上传聊天记录")

    # 3) 组卷：错题取前 N 道（不重复），其余随机补齐，错题均匀分散
    n = min(len(mistake_qids), MISTAKE_PER_BATCH)
    chosen = mistake_qids[:n]
    pool = [q.id for q in all_qs if q.id not in chosen]
    random.shuffle(pool)
    fill = pool[: max(0, BATCH_SIZE - n)]
    question_ids = _interleave_mistakes(chosen, fill)

    batch = TrainingBatch(
        user_id=user_id,
        category_id=category_id,
        status="in_progress",
        question_count=len(question_ids),
    )
    db.add(batch)
    db.flush()
    for i, qid in enumerate(question_ids, start=1):
        db.add(BatchQuestion(batch_id=batch.id, question_id=qid, seq=i))
    db.commit()
    db.refresh(batch)
    return batch


def _interleave_mistakes(mistakes: list[int], fill: list[int]) -> list[int]:
    """把错题按等间距均匀分散到题目序列中，避免连续出现。

    mistakes: 错题 id（混入）
    fill: 普通题 id（补齐）
    返回按展示顺序排列的题目 id 列表。
    """
    total = len(mistakes) + len(fill)
    if not mistakes or not fill:
        return mistakes + fill
    positions = set()
    step = total / len(mistakes)
    for i in range(len(mistakes)):
        positions.add(min(total - 1, int(round((i + 0.5) * step))))
    result = []
    mi, fi = 0, 0
    for idx in range(total):
        if idx in positions and mi < len(mistakes):
            result.append(mistakes[mi])
            mi += 1
        else:
            result.append(fill[fi])
            fi += 1
    return result


# ---------- 练题 ----------


def start_question(db: Session, batch: TrainingBatch, user_id: int):
    """取批次中第一道未开始（无会话）的题，创建训练会话并绑定。

    Returns: (session, question, batch_question) 或 (None, None, None) 当全部已开始。
    """
    for bq in batch.items:
        if bq.session_id is None:
            q = db.query(Question).filter(Question.id == bq.question_id).first()
            s = ChatSession(
                user_id=user_id, category_id=batch.category_id, status="in_progress"
            )
            db.add(s)
            db.flush()
            s.batch_question_id = bq.id  # 双向绑定：会话 → 批内题
            bq.session_id = s.id
            db.commit()
            db.refresh(s)
            return s, q, bq
    return None, None, None


def refresh_batch_status(db: Session, batch: TrainingBatch) -> None:
    """根据各题会话完成情况刷新批次状态：20 题练完 → awaiting_review。"""
    if batch.status != "in_progress":
        return
    done = 0
    for bq in batch.items:
        if not bq.session_id:
            continue
        s = db.query(ChatSession).filter(ChatSession.id == bq.session_id).first()
        if s and s.status == "completed":
            done += 1
    if done >= batch.question_count:
        batch.status = "awaiting_review"
        db.commit()


def is_mistake(db: Session, user_id: int, question_id: int) -> bool:
    """该题当前是否在该客服错题本（未解决）。"""
    return (
        db.query(MistakeLog)
        .filter(
            MistakeLog.user_id == user_id,
            MistakeLog.question_id == question_id,
            MistakeLog.resolved_at.is_(None),
        )
        .first()
        is not None
    )


# ---------- 判定 ----------


def review_batch(db: Session, batch_id: int, items: list) -> int:
    """主管判定批次内题目。

    items: [(question_id, passed: bool), ...]
    返回本次新进/累计错题本条目数（changed 数）。
    """
    batch = db.query(TrainingBatch).filter(TrainingBatch.id == batch_id).first()
    if not batch:
        raise ValueError("批次不存在")
    by_qid = {item["question_id"]: item["passed"] for item in items}
    changed = 0
    for bq in batch.items:
        if bq.question_id not in by_qid:
            continue
        passed = by_qid[bq.question_id]
        bq.review_status = "approved" if passed else "rejected"
        bq.reviewed_at = datetime.utcnow()
        if passed:
            _resolve_mistake(db, batch.user_id, bq.question_id)
        else:
            _add_mistake(db, batch.user_id, bq.question_id)
            changed += 1
    # 全部判定完 → reviewed
    if batch.items and all(bq.review_status != "pending" for bq in batch.items):
        batch.status = "reviewed"
        batch.reviewed_at = datetime.utcnow()
    db.commit()
    return changed


def _add_mistake(db: Session, user_id: int, question_id: int) -> None:
    ml = (
        db.query(MistakeLog)
        .filter(MistakeLog.user_id == user_id, MistakeLog.question_id == question_id)
        .first()
    )
    if ml:
        ml.appear_count += 1
        ml.resolved_at = None  # 重新进入错题状态
        ml.added_at = datetime.utcnow()
    else:
        db.add(MistakeLog(user_id=user_id, question_id=question_id))


def _resolve_mistake(db: Session, user_id: int, question_id: int) -> None:
    ml = (
        db.query(MistakeLog)
        .filter(MistakeLog.user_id == user_id, MistakeLog.question_id == question_id)
        .first()
    )
    if ml:
        ml.resolved_at = datetime.utcnow()


# ---------- 进度 ----------


def latest_batch(db: Session, user_id: int, category_id: int | None = None):
    """取客服最新一批（可按品类过滤）。"""
    q = db.query(TrainingBatch).filter(TrainingBatch.user_id == user_id)
    if category_id is not None:
        q = q.filter(TrainingBatch.category_id == category_id)
    return q.order_by(TrainingBatch.id.desc()).first()


def count_unresolved_mistakes(db: Session, user_id: int) -> int:
    """客服错题本未解决题数（全品类）。"""
    return (
        db.query(MistakeLog)
        .filter(MistakeLog.user_id == user_id, MistakeLog.resolved_at.is_(None))
        .count()
    )

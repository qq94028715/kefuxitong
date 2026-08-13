"""知识点掌握度引擎（v0.8）。

掌握度算法（决策 #11）：EMA 指数移动平均，新判定权重更高。
    mastery_new = (1 - α) × mastery_old + α × judgment
    judgment：通过 = 100；主管驳回 = 0，且 α 翻倍（α_reject = 2α）

状态三档（决策 #2，不判结业，仅供主管参考）：
    weak(薄弱)  mastery < pass_threshold
    pass(及格)  pass_threshold <= mastery < master_threshold
    master(达标) mastery >= master_threshold
"""
from datetime import datetime
import json

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Skill, SkillMastery
from . import llm


def derive_status(mastery: float) -> str:
    """按掌握度值推导状态档位。"""
    if mastery < settings.mastery_pass_threshold:
        return "weak"
    if mastery < settings.mastery_master_threshold:
        return "pass"
    return "master"


def get_mastery(db: Session, user_id: int, skill_id: int) -> SkillMastery | None:
    return (
        db.query(SkillMastery)
        .filter(SkillMastery.user_id == user_id, SkillMastery.skill_id == skill_id)
        .first()
    )


def get_or_create_mastery(
    db: Session, user_id: int, skill_id: int
) -> SkillMastery:
    row = get_mastery(db, user_id, skill_id)
    if not row:
        row = SkillMastery(user_id=user_id, skill_id=skill_id, mastery=0.0)
        db.add(row)
        db.flush()
    return row


def record_judgment(
    db: Session, user_id: int, skill_id: int, passed: bool
) -> SkillMastery:
    """一次判定后更新掌握度（EMA）。

    passed=True 通过；False = 主管驳回（当次扣分翻倍）。
    """
    row = get_or_create_mastery(db, user_id, skill_id)
    alpha = settings.mastery_alpha
    if not passed:
        alpha *= 2  # 驳回翻倍（防刷题虚高）
    judgment = 100.0 if passed else 0.0
    row.mastery = round((1 - alpha) * row.mastery + alpha * judgment, 1)
    row.attempt_count += 1
    if not passed:
        row.reject_count += 1
    row.status = derive_status(row.mastery)
    row.last_judged_at = datetime.utcnow()
    return row


def skill_mastery_map(
    db: Session, user_id: int, category_id: int
) -> dict[int, SkillMastery]:
    """用户在某品类的全部掌握度记录，keyed by skill_id。"""
    skill_ids = [
        s.id
        for s in db.query(Skill).filter(Skill.category_id == category_id).all()
    ]
    if not skill_ids:
        return {}
    rows = (
        db.query(SkillMastery)
        .filter(
            SkillMastery.user_id == user_id,
            SkillMastery.skill_id.in_(skill_ids),
        )
        .all()
    )
    return {r.skill_id: r for r in rows}


def weak_skill_ids(db: Session, user_id: int, category_id: int) -> list[int]:
    """用户在该品类的薄弱知识点（weak 状态），按掌握度升序（最薄弱在前）。"""
    rows = skill_mastery_map(db, user_id, category_id)
    return sorted(
        (s for s in rows.values() if s.status == "weak"),
        key=lambda r: r.mastery,
    )


def suggest_difficulty(mastery_value: float) -> str:
    """按当前掌握度建议出题难度（决策 #9）。"""
    if mastery_value < settings.mastery_pass_threshold:
        return "easy"
    if mastery_value < settings.mastery_master_threshold:
        return "medium"
    return "hard"


# ---------- 接口辅助 ----------


def mastery_out_dict(row: SkillMastery, skill_name: str) -> dict:
    """前端展示用字典。"""
    return {
        "skill_id": row.skill_id,
        "skill_name": skill_name,
        "mastery": row.mastery,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "reject_count": row.reject_count,
        "last_judged_at": row.last_judged_at,
    }


def ensure_skills_from_knowledge(
    db: Session, category_id: int, skill_names: list[str], material_ids: list[int]
) -> int:
    """把知识点清单同步到 skill 表（同名跳过，避免重复）。

    返回新增数。名称截断到 32 字符；AI 提炼的记录来源材料 ID。
    """
    created = 0
    existing = {
        s.name
        for s in db.query(Skill).filter(Skill.category_id == category_id).all()
    }
    material_ids_json = json.dumps(material_ids)
    for name in skill_names:
        name = (name or "").strip()[:32]
        if not name or name in existing:
            continue
        db.add(
            Skill(
                category_id=category_id,
                name=name,
                description="",
                source="ai",
                source_material_ids=material_ids_json,
            )
        )
        existing.add(name)
        created += 1
    if created:
        db.commit()
    return created


def llm_enabled() -> bool:
    """供 prompt 提示用：是否启用真实 LLM。"""
    return llm.is_llm_enabled()

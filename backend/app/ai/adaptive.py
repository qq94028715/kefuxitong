"""自适应出题（v0.8，决策 #8/#9）。

选题优先级（按掌握度引擎）：
1. 错题重练（最高优先）：MistakeLog 未解决题
2. 薄弱点：weak 状态知识点的题
3. 难度升级：pass 状态知识点下，难度不低于当前掌握度建议档的题
4. 巩固/新题：品类内其余题

批内配比（config 可调）：错题 20% + 薄弱 50% + 巩固 20% + 新题 10%。
错题按等间距均匀分散，避免连刷同一题（沿用 v0.7 设计约束）。
"""
import random

from sqlalchemy.orm import Session

from ..config import settings
from ..models import BatchQuestion, MistakeLog, Question, TrainingBatch
from . import mastery

_DIFF_RANK = {"easy": 0, "medium": 1, "hard": 2}


def _diff_rank(difficulty: str) -> int:
    return _DIFF_RANK.get((difficulty or "medium").lower(), 1)


def _shuffle_take(pool: list, n: int) -> list:
    pool = list(pool)
    random.shuffle(pool)
    return pool[:n]


def _unresolved_mistakes(db: Session, user_id: int, category_id: int) -> list[int]:
    """未解决错题 qid（该品类，按最近添加优先）。"""
    rows = (
        db.query(MistakeLog)
        .join(Question, MistakeLog.question_id == Question.id)
        .filter(
            MistakeLog.user_id == user_id,
            MistakeLog.resolved_at.is_(None),
            Question.category_id == category_id,
        )
        .order_by(MistakeLog.added_at.desc())
        .all()
    )
    return [r.question_id for r in rows]


def _practiced_ids(db: Session, user_id: int, category_id: int) -> set[int]:
    """该用户在该品类已练过（有会话）的题 id。"""
    rows = (
        db.query(BatchQuestion)
        .join(TrainingBatch, BatchQuestion.batch_id == TrainingBatch.id)
        .filter(
            TrainingBatch.user_id == user_id,
            TrainingBatch.category_id == category_id,
            BatchQuestion.session_id.isnot(None),
        )
        .all()
    )
    return {r.question_id for r in rows}


def _interleave_mistakes(mistakes: list[int], fill: list[int]) -> list[int]:
    """把错题按等间距均匀分散到题目序列中，避免连续出现。"""
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


def plan_batch(db: Session, user_id: int, category_id: int, size: int = 20) -> list[int]:
    """生成一批题目 id（有序，错题均匀分散）。

    Raises: ValueError 当该品类题库为空。
    """
    all_qs = db.query(Question).filter(Question.category_id == category_id).all()
    if not all_qs:
        raise ValueError("该品类暂无训练题目，请先在「导入语料」上传聊天记录")

    mistake_ids = _unresolved_mistakes(db, user_id, category_id)
    practiced = _practiced_ids(db, user_id, category_id)
    m_map = mastery.skill_mastery_map(db, user_id, category_id)
    weak_ids = {s.id for s in mastery.weak_skill_ids(db, user_id, category_id)}
    mistake_set = set(mistake_ids)

    # 薄弱点题：主知识点 weak 状态，且非错题
    weak_pool = [
        q.id for q in all_qs if q.skill_id in weak_ids and q.id not in mistake_set
    ]
    # 升级题：主知识点 pass 状态，且难度 >= 当前掌握度建议档
    upgrade_pool = []
    for q in all_qs:
        if q.id in mistake_set or not q.skill_id:
            continue
        row = m_map.get(q.skill_id)
        if not row or row.status != "pass":
            continue
        suggested = mastery.suggest_difficulty(row.mastery)
        if _diff_rank(q.difficulty or "medium") >= _diff_rank(suggested):
            upgrade_pool.append(q.id)
    # 新题：未练过
    new_pool = [q.id for q in all_qs if q.id not in practiced]
    # 巩固：已练过且不属于以上任何组
    excluded = mistake_set | set(weak_pool) | set(upgrade_pool) | set(new_pool)
    consolidate_pool = [q.id for q in all_qs if q.id not in excluded]

    size = max(1, min(size, len(all_qs)))
    n_mistake = min(len(mistake_ids), round(size * settings.adaptive_mistake_ratio))
    n_weak = min(len(weak_pool), round(size * settings.adaptive_weak_ratio))
    n_upgrade = min(len(upgrade_pool), round(size * settings.adaptive_consolidate_ratio))
    rest = size - n_mistake - n_weak - n_upgrade

    chosen_mistake = mistake_ids[:n_mistake]
    chosen_weak = _shuffle_take(weak_pool, n_weak)
    chosen_upgrade = _shuffle_take(upgrade_pool, n_upgrade)
    chosen_new = _shuffle_take(new_pool, rest)
    if len(chosen_new) < rest:
        chosen_new += _shuffle_take(consolidate_pool, rest - len(chosen_new))

    fill = chosen_weak + chosen_upgrade + chosen_new
    return _interleave_mistakes(chosen_mistake, fill)

"""v0.8 掌握度闭环集成测试（内存库，不碰真实数据）。"""
import sys

sys.path.insert(0, r"E:\project\kefuxitong_v0.7_dev_20260813\kefuxitong\backend")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Category, User, Skill, Question, TrainingBatch, BatchQuestion, MistakeLog,
)
from app.batch import review_batch
from app.ai import mastery as m


def setup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    cat = Category(name="测试品类")
    db.add(cat)
    db.flush()
    agent = User(username="a1", password_hash="x", role="agent")
    db.add(agent)
    db.flush()
    sk_ema = Skill(category_id=cat.id, name="报价计算")
    sk_rev = Skill(category_id=cat.id, name="需求确认")
    db.add_all([sk_ema, sk_rev])
    db.flush()
    # 4 道题绑 review 用的知识点
    qids = []
    for i in range(4):
        q = Question(category_id=cat.id, title=f"题{i}", skill_id=sk_rev.id, difficulty="medium")
        db.add(q)
        db.flush()
        qids.append(q.id)
    db.commit()
    return db, agent.id, sk_ema.id, sk_rev.id, qids


def test_ema_chain(db, uid, sid):
    """EMA 演算：连对 5 次 → master；驳回一次 → 大幅回落。"""
    row = m.get_or_create_mastery(db, uid, sid)
    chain = []
    for i in range(5):
        row = m.record_judgment(db, uid, sid, True)
        chain.append((round(row.mastery, 1), row.status))
    assert chain == [(30.0, "weak"), (51.0, "pass"), (65.7, "pass"), (76.0, "pass"), (83.2, "master")], chain
    row = m.record_judgment(db, uid, sid, False)  # 驳回 → α 翻倍
    assert row.mastery == 33.3, row.mastery  # 83.2*0.4
    assert row.status == "weak"
    print("EMA 链路 OK:", chain, "→ 驳回后", row.mastery, row.status)


def test_review_writes_mastery(db, uid, sid, qids):
    """review_batch 判定 → 掌握度写入。"""
    b = TrainingBatch(user_id=uid, category_id=db.query(Category).first().id, status="in_progress", question_count=2)
    db.add(b)
    db.flush()
    for i, qid in enumerate(qids[:2], start=1):
        db.add(BatchQuestion(batch_id=b.id, question_id=qid, seq=i))
    db.commit()
    # 全通过
    review_batch(db, b.id, [{"question_id": qids[0], "passed": True}, {"question_id": qids[1], "passed": True}])
    row = m.get_mastery(db, uid, sid)
    assert row.attempt_count == 2 and row.reject_count == 0, (row.attempt_count, row.reject_count)
    assert row.mastery == 51.0, row.mastery  # 30 → 51
    # 再开一批，一题驳回
    b2 = TrainingBatch(user_id=uid, category_id=db.query(Category).first().id, status="in_progress", question_count=1)
    db.add(b2)
    db.flush()
    db.add(BatchQuestion(batch_id=b2.id, question_id=qids[2], seq=1))
    db.commit()
    review_batch(db, b2.id, [{"question_id": qids[2], "passed": False}])
    row = m.get_mastery(db, uid, sid)
    assert row.reject_count == 1 and row.attempt_count == 3
    assert row.mastery == 20.4, row.mastery  # 51*0.4
    assert row.status == "weak"
    # 错题本应有一条
    ml = db.query(MistakeLog).filter(MistakeLog.user_id == uid).count()
    assert ml == 1, ml
    print("review 写掌握度 OK: 2通过→51, 1驳回→20.4, 错题本 1 条")


if __name__ == "__main__":
    db, uid, sid_ema, sid_rev, qids = setup()
    test_ema_chain(db, uid, sid_ema)
    test_review_writes_mastery(db, uid, sid_rev, qids)
    print("ALL PASS")

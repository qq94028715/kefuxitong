"""错题本批次闭环端到端回归测试（独立临时库，不污染正式数据）。

用法：cd backend && .venv/Scripts/python.exe test_batch_flow.py
覆盖链路：导语料 → 开批(组卷) → 逐题训练评分 → 批次锁定 → 主管判定 → 错题进本 → 新批错题混入 → 判定合适解错题
"""
import os
import sys
import tempfile
from pathlib import Path

TMP_DB = Path(tempfile.gettempdir()) / "kefuxitong_test_batch.db"
if TMP_DB.exists():
    TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB.as_posix()}"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

CHAT1 = (
    "聊天对象\t客户甲\t聊天内容\t你好，我想做一批PVC标签\t聊天时间\t2026-07-20 10:00\n"
    "聊天对象\t旗舰店客服\t聊天内容\t您好，请问大概什么尺寸、数量多少？\t聊天时间\t2026-07-20 10:01\n"
    "聊天对象\t客户甲\t聊天内容\t尺寸100*50mm，数量2000片\t聊天时间\t2026-07-20 10:02\n"
    "聊天对象\t旗舰店客服\t聊天内容\t好的，PVC材质可以，7天交货，单价0.45元，可以吗？\t聊天时间\t2026-07-20 10:03\n"
    "聊天对象\t客户甲\t聊天内容\t可以，下单吧\t聊天时间\t2026-07-20 10:04\n"
)
CHAT2 = (
    "聊天对象\t客户乙\t聊天内容\t金属铭牌多少钱一块？\t聊天时间\t2026-07-20 11:00\n"
    "聊天对象\t旗舰店客服\t聊天内容\t您好，铭牌看材质和工艺，您大概要什么规格？\t聊天时间\t2026-07-20 11:01\n"
    "聊天对象\t客户乙\t聊天内容\t304不锈钢，100*80，500块\t聊天时间\t2026-07-20 11:02\n"
    "聊天对象\t旗舰店客服\t聊天内容\t好的，腐蚀雕刻工艺，含税含运费8.5元/块，要吗？\t聊天时间\t2026-07-20 11:03\n"
    "聊天对象\t客户乙\t聊天内容\t太贵了，别家7块\t聊天时间\t2026-07-20 11:04\n"
)


def main():
    with TestClient(app) as c:
        # 1. 管理员登录
        r = c.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.text
        AH = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 2. 建客服
        r = c.post("/api/admin/agents", json={"username": "agent1", "password": "123456"}, headers=AH)
        assert r.status_code == 200, r.text

        # 3. 品类
        cats = c.get("/api/admin/categories", headers=AH).json()
        cat_id = next(x["id"] for x in cats if x["name"] == "PVC训练")

        # 4. 导入两条聊天记录（销售语料 → 自动转题素材）
        for txt in (CHAT1, CHAT2):
            r = c.post(
                "/api/admin/import-chat",
                json={"category_id": cat_id, "quality": "excellent", "raw_text": txt},
                headers=AH,
            )
            assert r.status_code == 200, r.text

        # 5. 客服开批
        r = c.post("/api/agent/login", json={"username": "agent1", "password": "123456"})
        AH2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = c.post("/api/agent/batches", json={"category_id": cat_id}, headers=AH2)
        assert r.status_code == 200, r.text
        batch = r.json()["batch"]
        assert batch["question_count"] == 2, batch
        print(f"[1] 开批 OK：{batch['question_count']} 题（题库=2 条语料自动转题）")

        # 6. 逐题训练 + 评分
        for _ in range(batch["question_count"]):
            r = c.post(f"/api/agent/batches/{batch['id']}/start-question", headers=AH2)
            assert r.status_code == 200, r.text
            sq = r.json()
            sid = sq["session"]["id"]
            assert sq["seq"] >= 1
            for _ in range(4):
                r = c.post(
                    f"/api/agent/sessions/{sid}/messages",
                    json={"content": "您好，请问您需要什么规格的产品？我可以为您推荐合适的方案。"},
                    headers=AH2,
                )
                assert r.status_code == 200, r.text
            r = c.post(f"/api/agent/sessions/{sid}/finish", headers=AH2)
            assert r.status_code == 200, r.text
            print(f"[2] 第 {sq['seq']} 题训练+评分 OK，得分 {r.json()['score']['total_score']}")

        # 7. 批次锁定
        r = c.get(f"/api/agent/batches/{batch['id']}", headers=AH2)
        assert r.json()["status"] == "awaiting_review", r.text
        print("[3] 批次已进入 awaiting_review（等主管判定）")

        # 8. 主管判定：第 1 题不合适，第 2 题合适
        items = [{"question_id": x["question_id"], "passed": x["seq"] != 1} for x in r.json()["items"]]
        r = c.post(f"/api/admin/batches/{batch['id']}/review", json={"items": items}, headers=AH)
        assert r.status_code == 200, r.text
        assert r.json()["mistakes_updated"] == 1, r.json()
        print("[4] 主管判定 OK：1 题进错题本")

        # 9. 开新批 → 错题必须混入且标记 is_mistake
        r = c.post("/api/agent/batches", json={"category_id": cat_id}, headers=AH2)
        assert r.status_code == 200, r.text
        batch2 = r.json()["batch"]
        qids2 = [x["question_id"] for x in batch2["items"]]
        mistake_qid = items[0]["question_id"]
        assert mistake_qid in qids2, (mistake_qid, qids2)
        assert any(x["is_mistake"] for x in batch2["items"]), batch2["items"]
        print(f"[5] 新批错题间隔混入 OK：题序 {qids2}，is_mistake={[x['is_mistake'] for x in batch2['items']]}")

        # 10. 新批练完 + 判定合适 → 解错题
        for _ in range(batch2["question_count"]):
            r = c.post(f"/api/agent/batches/{batch2['id']}/start-question", headers=AH2)
            sid = r.json()["session"]["id"]
            for _ in range(4):
                c.post(
                    f"/api/agent/sessions/{sid}/messages",
                    json={"content": "好的，我确认一下您的需求，稍后给您报价。"},
                    headers=AH2,
                )
            c.post(f"/api/agent/sessions/{sid}/finish", headers=AH2)
        r = c.get(f"/api/agent/batches/{batch2['id']}", headers=AH2)
        items2 = [{"question_id": x["question_id"], "passed": True} for x in r.json()["items"]]
        r = c.post(f"/api/admin/batches/{batch2['id']}/review", json={"items": items2}, headers=AH)
        assert r.status_code == 200, r.text
        prog = c.get("/api/agent/batch-progress", headers=AH2).json()
        assert prog["mistake_count"] == 0, prog
        print(f"[6] 判定合适解错题 OK：剩余错题 {prog['mistake_count']}")

        print("\nALL TESTS PASSED ✅（错题本闭环完整）")


if __name__ == "__main__":
    main()

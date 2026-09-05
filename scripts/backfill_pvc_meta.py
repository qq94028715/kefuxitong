"""回填 PVC 题目（id 9-21）的 scenario/difficulty/outcome/key_points。

之前因为脚本不在 backend/ 目录跑，pydantic-settings 没找到 .env，
LLM 没真正调用，全走了默认值。这里重新提取并 update。
"""
import os
import sys
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))

logging.basicConfig(level=logging.WARNING)

from app.ai.llm import chat  # noqa: E402
from app.models import Question  # noqa: E402
from app.database import SessionLocal  # noqa: E402

EXTRACT_PROMPT = """你是淘宝 PVC 标牌店「中科立得旗舰店」的资深客服主管。请根据下面一段客户和客服的真实聊天记录，提炼出：

1. scenario（2-4 行客户画像/场景描述）：客户身份、需求场景、关注点（颜色/数量/价格/材质/配件/工艺/打样/物流/付款等）
2. difficulty（easy/medium/hard）：客户议价/复杂定制=hard，常规问价/定制=medium，简单报价=easy
3. outcome（成交/未成交/跟进中）：最终成交状态
4. key_points（3-5 个客服应答要点，逗号分隔）：本对话客服做得好的关键点

输出严格 JSON，不要 markdown 包裹：
{"scenario":"...","difficulty":"...","outcome":"...","key_points":"..."}

聊天记录：
"""


def extract_meta(script_text: str) -> dict:
    raw = chat(
        [
            {"role": "system", "content": "你是淘宝 PVC 标牌店资深客服主管，输出严格 JSON。"},
            {"role": "user", "content": EXTRACT_PROMPT + script_text},
        ],
        temperature=0.2,
        max_tokens=500,
    )
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        meta = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [parse fail] {e}; raw head: {raw[:120]}")
        return None
    meta.setdefault("scenario", "")
    meta.setdefault("difficulty", "medium")
    meta.setdefault("outcome", "")
    meta.setdefault("key_points", "")
    if meta["difficulty"] not in ("easy", "medium", "hard"):
        meta["difficulty"] = "medium"
    return meta


def main():
    db = SessionLocal()
    try:
        targets = db.query(Question).filter(Question.id >= 9).filter(Question.id <= 21).all()
        print(f"[scan] 待回填 {len(targets)} 题 (id 9-21)")
        updated = 0
        for q in targets:
            print(f"\n[#{q.id}] {q.title[:50]}")
            meta = extract_meta(q.script_text)
            if not meta:
                print(f"  -> LLM 跳过")
                continue
            q.scenario = meta["scenario"]
            q.difficulty = meta["difficulty"]
            # 把 outcome 拼到 scenario 末尾便于查看（数据库无 outcome 字段）
            if meta["outcome"]:
                q.scenario = q.scenario + f"\n[结果] {meta['outcome']}"
            if meta["key_points"]:
                q.scenario = q.scenario + f"\n[要点] {meta['key_points']}"
            updated += 1
            print(f"  -> {meta['difficulty']} | {meta['scenario'][:80]}")
        db.commit()
        print(f"\n[done] 已回填 {updated}/{len(targets)} 题")
    finally:
        db.close()


if __name__ == "__main__":
    main()

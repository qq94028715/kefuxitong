"""PVC 聊天记录批量入题库。

从 D:\胡杰文件夹\聊天记录\ 解析 13 条 PVC 聊天记录，
用 LLM 提取 scenario 和 difficulty，写入 question 表（PVC 分类 id=1）。

用法：
    cd backend && ../backend/.venv/Scripts/python.exe ../scripts/import_pvc_chats.py
"""
import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime

# 让脚本能 import app，且强制从 backend/ 目录加载 .env
ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(str(BACKEND_DIR))  # pydantic-settings 默认在 cwd 找 .env

from app.config import settings  # noqa: E402
from app.ai.llm import chat  # noqa: E402
from app.models import Category, Question  # noqa: E402
from app.database import SessionLocal  # noqa: E402


CHATS_DIR = Path(r"D:\胡杰文件夹\聊天记录")

AGENT_PATTERN = re.compile(r"^中科立得旗舰店[:：]")  # 客服
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
URL_PATTERN = re.compile(r"https?://[^\s]+|item\.taobao\.com[^\s]*")
HEADERS = {"聊天对象", "聊天内容", "聊天时间"}  # PVC1 顶部表头


def is_image_or_meta(line: str) -> bool:
    """图片链接/淘宝商品链接/系统提示，返回 True 表示跳过。"""
    if not line:
        return True
    if URL_PATTERN.search(line):
        return True
    if line.startswith("当前用户来自"):
        return True
    if line.startswith("当前用户"):
        return True
    return False


def parse_chat_file(path: Path) -> list[dict]:
    """解析一个聊天 txt → [{role, content}, ...]。

    规则：每 3 行为一条消息 (sender, content, timestamp)；
    跳过表头、图片链接、系统提示。
    """
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 去表头
    if lines[:3] == ["聊天对象", "聊天内容", "聊天时间"]:
        lines = lines[3:]

    messages = []
    i = 0
    while i < len(lines):
        sender = lines[i]
        content = lines[i + 1] if i + 1 < len(lines) else ""
        # 时间戳可选
        ts = ""
        if i + 2 < len(lines) and TIMESTAMP_PATTERN.match(lines[i + 2]):
            ts = lines[i + 2]
            i += 3
        else:
            i += 2

        if not content:
            continue
        if is_image_or_meta(content):
            continue
        if content in HEADERS:
            continue
        # 短到 1 字符的可能是图片残留
        if len(content) < 1:
            continue

        role = "agent" if AGENT_PATTERN.match(sender) else "customer"
        messages.append({"role": role, "content": content, "time": ts, "speaker": sender})
    return messages


def format_script(messages: list[dict]) -> str:
    """把消息列表格式化成 script_text：客户/客服对话，每行一个角色。"""
    return "\n".join(
        f"[{'客户' if m['role'] == 'customer' else '客服'}] {m['content']}"
        for m in messages
    )


EXTRACT_PROMPT = """你是淘宝 PVC 标牌店「中科立得旗舰店」的资深客服主管。请根据下面一段客户和客服的真实聊天记录，提炼出：

1. scenario（2-4 行客户画像/场景描述）：客户身份、需求场景、关注点（颜色/数量/价格/材质/配件/工艺/打样/物流/付款等）
2. difficulty（easy/medium/hard）：客户议价/复杂定制=hard，常规问价/定制=medium，简单报价=easy
3. outcome（成交/未成交/跟进中）：最终成交状态
4. key_points（3-5 个客服应答要点，逗号分隔）：本对话客服做得好的关键点（如果成交）或需要改进的点（如果未成交）

输出严格 JSON，不要 markdown 包裹，键名固定：
{"scenario":"...","difficulty":"...","outcome":"...","key_points":"..."}

聊天记录：
"""


def extract_meta(script_text: str) -> dict:
    """调 LLM 提取 scenario/difficulty/outcome/key_points。失败兜底。"""
    raw = chat(
        [
            {"role": "system", "content": "你是淘宝 PVC 标牌店资深客服主管，输出严格 JSON。"},
            {"role": "user", "content": EXTRACT_PROMPT + script_text},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    if not raw:
        return {
            "scenario": "客户就 PVC 标牌定制进行咨询。",
            "difficulty": "medium",
            "outcome": "成交",
            "key_points": "",
        }
    text = raw.strip()
    # 容错去掉 markdown
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # 提取首个 { 到最后 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        meta = json.loads(text)
    except json.JSONDecodeError:
        meta = {
            "scenario": "客户就 PVC 标牌定制进行咨询。",
            "difficulty": "medium",
            "outcome": "成交",
            "key_points": "",
        }
    # 兜底字段
    meta.setdefault("scenario", "")
    meta.setdefault("difficulty", "medium")
    meta.setdefault("outcome", "")
    meta.setdefault("key_points", "")
    if meta["difficulty"] not in ("easy", "medium", "hard"):
        meta["difficulty"] = "medium"
    return meta


def derive_title(filename: str, messages: list[dict], meta: dict) -> str:
    """用文件名 + 第一句客户问题生成标题。"""
    # 文件名去掉扩展名 + 后缀
    stem = filename.rsplit(".", 1)[0]
    # 第一条客户消息
    first_customer = next((m["content"] for m in messages if m["role"] == "customer"), "")
    first = first_customer[:30].strip()
    if first:
        return f"{stem}｜{first}…"
    return stem


def main():
    if not CHATS_DIR.exists():
        print(f"[!] 目录不存在: {CHATS_DIR}")
        sys.exit(1)

    files = sorted([p for p in CHATS_DIR.iterdir() if p.suffix == ".txt"])
    # 跳过「知识点」类
    files = [p for p in files if "知识点" not in p.name]
    print(f"[scan] 共 {len(files)} 条聊天记录")
    for p in files:
        print(f"  - {p.name}")

    db = SessionLocal()
    try:
        pvc_cat = db.query(Category).filter(Category.name == "PVC训练").first()
        if not pvc_cat:
            print("[!] 未找到 PVC 分类（id=1 应已存在）")
            sys.exit(1)
        print(f"[cat] PVC 分类 id={pvc_cat.id}")

        imported = 0
        skipped = 0
        for path in files:
            messages = parse_chat_file(path)
            if len(messages) < 4:
                print(f"  [skip] {path.name}: 仅 {len(messages)} 条有效消息")
                skipped += 1
                continue

            script_text = format_script(messages)
            meta = extract_meta(script_text)
            title = derive_title(path.name, messages, meta)

            # 查重：同 source 不重复导入
            existing = (
                db.query(Question)
                .filter(Question.category_id == pvc_cat.id)
                .filter(Question.title.like(f"{path.stem}%"))
                .first()
            )
            if existing:
                print(f"  [dup]  {path.name}: 已存在（id={existing.id}）")
                skipped += 1
                continue

            q = Question(
                category_id=pvc_cat.id,
                source_material_id=None,
                title=title,
                scenario=meta["scenario"],
                script_text=script_text,
                source_type="uploaded",
                skill_id=None,
                difficulty=meta["difficulty"],
                related_skill_ids="[]",
            )
            db.add(q)
            imported += 1
            outcome_label = {"成交": "✅", "未成交": "❌", "跟进中": "🔄"}.get(
                meta["outcome"], "·"
            )
            print(f"  [ok]   {path.name}: {meta['difficulty']:6s} {outcome_label} {title[:50]}")
            print(f"         scenario: {meta['scenario'][:80]}")

        db.commit()
        print(f"\n[done] 新增 {imported} 题，跳过 {skipped} 条")
        print(f"[tot]  PVC 分类现有题目数: {db.query(Question).filter(Question.category_id == pvc_cat.id).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

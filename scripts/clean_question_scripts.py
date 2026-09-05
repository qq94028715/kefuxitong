#!/usr/bin/env python
"""
清洗 question.script_text 脏数据。

清洗规则复用 simulator._clean_script_text（已通过 v0.14 验证）：
  - 去时间戳行（如 "[2026-09-04 19:52:34]"）
  - 去"图片"/"卡片"占位
  - 去系统提示（"请使用快捷短语"/"客服小蜜正在输入"等）
  - 去微信/千牛消息分隔线（---/===/###）
  - 去 URL（http/https 链接）
  - 折叠多余空行

用法：
  # 仅查看清洗效果（不入库）
  .venv/Scripts/python.exe scripts/clean_question_scripts.py

  # 真正入库（先备份数据库）
  .venv/Scripts/python.exe scripts/clean_question_scripts.py --commit

  # 只清洗指定题（如只清洗 PVC 9-21）
  .venv/Scripts/python.exe scripts/clean_question_scripts.py --ids 9,10,11

  # 只看清洗前后对比（不入库、不打印细节）
  .venv/Scripts/python.exe scripts/clean_question_scripts.py --report
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 切到 backend 目录，让 app.* 能 import（沿用现有 scripts 约定）
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.ai.simulator import _clean_script_text  # noqa: E402

DB_PATH = BACKEND_DIR / "data" / "kefuxitong.db"


def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def backup_db(db_path: Path) -> Path:
    """备份数据库到 data/backup_YYYYMMDD_HHMMSS/，返回备份文件路径。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db_path.parent / f"backup_{ts}"
    backup_dir.mkdir(exist_ok=True)
    dst = backup_dir / db_path.name
    shutil.copy2(db_path, dst)
    return dst


def fetch_questions(cur: sqlite3.Cursor, ids: list[int] | None) -> list[dict]:
    if ids:
        placeholders = ",".join("?" * len(ids))
        rows = cur.execute(
            f"select id, title, script_text from question "
            f"where script_text is not null and length(script_text)>0 "
            f"and id in ({placeholders}) order by id",
            ids,
        ).fetchall()
    else:
        rows = cur.execute(
            "select id, title, script_text from question "
            "where script_text is not null and length(script_text)>0 order by id"
        ).fetchall()
    return [{"id": r[0], "title": r[1], "script_text": r[2]} for r in rows]


def clean_one(q: dict) -> tuple[str, str]:
    """清洗单条剧本，返回 (清洗前, 清洗后)。"""
    before = q["script_text"]
    after = _clean_script_text(before)
    return before, after


def render_diff(qid: int, title: str, before: str, after: str, max_chars: int = 600) -> str:
    """渲染单条清洗前后对比。"""
    head = f"── Q{qid}: {title[:40]}"
    bar = "─" * max(len(head), 60)
    body = [
        head,
        bar,
        f"  原长度: {len(before):5d}  →  清洗后: {len(after):5d}  "
        f"(减少 {len(before) - len(after)} 字符，{100 * (1 - len(after) / max(len(before), 1)):.1f}%)",
        "",
        "  ── 清洗后内容 ──",
    ]
    for line in (after or "(空)").splitlines():
        body.append(f"    {line}")
    if len(after) > max_chars:
        body.append(f"    …(后省略 {len(after) - max_chars} 字符)")
    return "\n".join(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="清洗 question.script_text")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="真正写回数据库（默认只 dry-run 预览）",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="只清洗指定题 id，逗号分隔，如 '9,10,11'",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="只输出汇总报告，不打印每条清洗前后细节",
    )
    parser.add_argument(
        "--safe-ratio",
        type=float,
        default=0.3,
        help="安全阈值：清洗后字符数 / 原字符数 < 该比例则跳过（避免误洗好数据）。默认 0.3",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="即使清洗后变空/过短也强制写库（危险，默认禁用）",
    )
    args = parser.parse_args()

    ids = [int(x) for x in args.ids.split(",")] if args.ids else None

    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    questions = fetch_questions(cur, ids)
    if not questions:
        print("没有需要清洗的题。")
        conn.close()
        return

    _print_section(f"开始清洗 {len(questions)} 道题（{'COMMIT 模式' if args.commit else 'DRY-RUN 模式'}）")
    if ids:
        print(f"限定 id: {ids}")

    cleaned_count = 0
    unchanged_count = 0
    become_empty_count = 0
    skipped_dangerous = 0  # 清洗后字符数比例过低、被安全阈值跳过的题
    total_before = 0
    total_after = 0
    diffs: list[tuple[int, str, str, str]] = []  # (id, title, before, after)
    skipped: list[tuple[int, str, int, int]] = []  # (id, title, before_len, after_len)
    will_write: list[tuple[int, str, str, str]] = []  # 真正会 UPDATE 的题

    for q in questions:
        before, after = clean_one(q)
        total_before += len(before)
        total_after += len(after)
        if before == after:
            unchanged_count += 1
            continue
        if not after.strip():
            become_empty_count += 1

        # 安全阈值：清洗后字符数 < 原 * ratio 则跳过（防误洗）
        ratio = len(after) / max(len(before), 1)
        if ratio < args.safe_ratio and not args.all:
            skipped_dangerous += 1
            skipped.append((q["id"], q["title"], len(before), len(after)))
            diffs.append((q["id"], q["title"], before, after))  # 仍展示给主人看
            continue

        cleaned_count += 1
        diffs.append((q["id"], q["title"], before, after))
        will_write.append((q["id"], q["title"], before, after))

    # 报告
    _print_section("汇总")
    print(f"  待处理题目数:     {len(questions)}")
    print(f"  有变化的题目数:   {cleaned_count + skipped_dangerous}")
    print(f"    ├ 将入库:       {cleaned_count}")
    print(f"    └ 安全跳过:     {skipped_dangerous}（清洗后过短，未达阈值 {args.safe_ratio:.0%}）")
    print(f"  无变化的题目数:   {unchanged_count}")
    print(f"  清洗后变空的题:   {become_empty_count}（需重点检查）")
    print(f"  清洗前总字符数:   {total_before}")
    print(f"  清洗后总字符数:   {total_after}")
    if total_before:
        ratio = 100 * (1 - total_after / total_before)
        print(f"  总体减少:         {total_before - total_after} 字符 ({ratio:.1f}%)")

    # 安全跳过清单
    if skipped and not args.report:
        _print_section(f"⚠ 安全跳过的题（清洗后过短，未达阈值 {args.safe_ratio:.0%}）")
        for qid, title, before_len, after_len in skipped:
            ratio = after_len / max(before_len, 1)
            print(f"  Q{qid}: 清洗前 {before_len} → 清洗后 {after_len} ({ratio:.0%})  {title[:50]}")
        print(f"\n  原因：清洗函数 _ROLE_RE 只识别 [客户]/[客服] 方括号格式，")
        print(f"  早期结构化文本（客户：/客服 (xxx)：）会被误判丢弃。")
        print(f"  这些题本身较干净，未入库清洗。如需强制覆盖，请加 --all --safe-ratio=0。")

    # 详细 diff
    if not args.report and diffs:
        _print_section(f"逐题清洗对比（共 {len(diffs)} 条）")
        for qid, title, before, after in diffs:
            print(render_diff(qid, title, before, after))

    # COMMIT
    if args.commit:
        if not will_write:
            print("\n  没有需要入库的题，跳过写入。")
        else:
            _print_section("写入数据库")
            backup_path = backup_db(DB_PATH)
            print(f"  已备份 → {backup_path}")
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 加一列 cleaned_at 记录本次清洗时间（幂等可重跑）
            cols = [r[1] for r in cur.execute("PRAGMA table_info(question)")]
            if "script_text_cleaned_at" not in cols:
                cur.execute("ALTER TABLE question ADD COLUMN script_text_cleaned_at TEXT")
                print("  已加列: question.script_text_cleaned_at")

            n_written = 0
            for qid, _title, _before, after in will_write:
                cur.execute(
                    "UPDATE question SET script_text = ?, script_text_cleaned_at = ? WHERE id = ?",
                    (after, ts, qid),
                )
                n_written += 1
            conn.commit()
            print(f"  已 UPDATE {n_written} 条记录")
            print(f"  备份文件: {backup_path}")
            print(f"  完成时间: {ts}")
            if skipped_dangerous:
                print(f"  跳过 {skipped_dangerous} 条（清洗后过短，已保留原数据）")
    else:
        _print_section("DRY-RUN 结束")
        print("  数据库未被修改。预览如需真正入库，请加 --commit 参数重跑。")
        if will_write:
            print(f"  预计入库: {len(will_write)} 条")
        if skipped_dangerous:
            print(f"  安全跳过: {skipped_dangerous} 条（未达阈值）")

    conn.close()


if __name__ == "__main__":
    main()
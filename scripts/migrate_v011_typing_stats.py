"""v0.11 数据库迁移：给 chat_message 加 8 个键入统计字段（全部 nullable）。

幂等设计：检查列是否存在再 ADD COLUMN，避免重复加报错。

用法：
    python scripts/migrate_v011_typing_stats.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "kefuxitong.db"

NEW_COLUMNS = [
    ("first_keystroke_at", "DATETIME"),
    ("last_keystroke_at", "DATETIME"),
    ("keystroke_count", "INTEGER"),
    ("char_count", "INTEGER"),
    ("is_paste", "BOOLEAN"),
    ("is_quick_reply", "BOOLEAN"),
    ("typed_duration_ms", "INTEGER"),
    ("response_duration_ms", "INTEGER"),
]


def main() -> None:
    if not DB_PATH.exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        print("   请先启动一次后端服务（首次启动会自动建表）")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    # 查 chat_message 已有的列
    cur.execute("PRAGMA table_info(chat_message)")
    existing = {row[1] for row in cur.fetchall()}
    print(f"📋 chat_message 当前列数: {len(existing)}")

    added = []
    skipped = []
    for col_name, col_type in NEW_COLUMNS:
        if col_name in existing:
            skipped.append(col_name)
            continue
        # SQLite 不允许 ADD COLUMN 带 NOT NULL；用 nullable 默认 NULL
        sql = f"ALTER TABLE chat_message ADD COLUMN {col_name} {col_type}"
        cur.execute(sql)
        added.append(col_name)
        print(f"  ✅ ADD COLUMN {col_name} {col_type}")

    conn.commit()
    # 验证
    cur.execute("PRAGMA table_info(chat_message)")
    after = {row[1] for row in cur.fetchall()}
    print(f"\n📋 迁移后列数: {len(after)}")
    print(f"   新增: {added}")
    print(f"   跳过（已存在）: {skipped}")

    # 老数据兼容检查：数一下历史 agent 消息有几条
    cur.execute("SELECT COUNT(*) FROM chat_message WHERE role='agent'")
    print(f"\n📦 历史客服消息: {cur.fetchone()[0]} 条（键入字段均为 NULL，统计时按空处理）")

    conn.close()


if __name__ == "__main__":
    main()

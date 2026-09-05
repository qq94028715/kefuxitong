"""从 PVC 知识库（category_id=1）削掉"抗UV级"相关边缘内容。

主人反馈：抗UV级属于1% 客户才会遇到的细分需求，知识库铺得太多，
会诱导 AI 客户主动问剧本外的问题（如 UV/发黄/8年/贵15% 等）。

保留：
- UV 打印工艺（属于 product_specs.工艺 / required_questions[4]，是另一回事）

操作：复制 v9 → v10，精确删除/改写含抗UV级的字段，不动其他。
"""
import sqlite3
import json
import os
import shutil
from datetime import datetime

# 项目根
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "backend")
DB_PATH = os.path.join(BACKEND_DIR, "data", "kefuxitong.db")


def load_pvc_knowledge(db):
    row = db.execute(
        "select id, version, content_json from knowledge "
        "where category_id=1 order by version desc limit 1"
    ).fetchone()
    return row  # (id, version, content_json_text)


def drop_uv(obj: dict) -> dict:
    """精确修改 PVC 知识库，去掉抗UV级相关内容。"""
    obj = json.loads(json.dumps(obj, ensure_ascii=False))  # deep copy

    # 1) product_summary: 去掉 "户外长期使用需选择抗UV级产品"
    obj["product_summary"] = (
        "PVC板材是一种成本较低、加工灵活、重量轻的塑料标识材料，"
        "适用于电力、光伏、水表、通信等行业。"
    )

    # 2) required_questions[0]: 改写，丢掉 "普通PVC或抗UV级"
    obj["required_questions"][0] = "确认客户所需PVC板的材质（如PVC/CPVC）"

    # 3) common_objections: 删 [0][1]（整条都是抗UV）
    obj["common_objections"] = [v for i, v in enumerate(obj["common_objections"]) if i not in (0, 1)]

    # 4) recommended_responses[0].guideline: 去掉"户外推荐抗UV级"
    obj["recommended_responses"][0]["guideline"] = (
        "先确认客户所需规格（厚度、数量、用途），再报价。"
    )
    # recommended_responses[1] 整条都是抗UV，删除
    obj["recommended_responses"] = [
        v for i, v in enumerate(obj["recommended_responses"]) if i != 1
    ]

    # 5) key_knowledge: 删 [2][3]（抗UV/抗老化/贵15%）
    obj["key_knowledge"] = [v for i, v in enumerate(obj["key_knowledge"]) if i not in (2, 3)]

    # 6) success_patterns[0] 整条都是抗UV，删除
    obj["success_patterns"] = [
        v for i, v in enumerate(obj["success_patterns"]) if i != 0
    ]

    # 7) failure_patterns[0]: 改写，去掉抗UV 相关
    obj["failure_patterns"][0] = {
        "scenario": "客户询问户外标识牌价格",
        "mistake": "未确认使用环境，直接报价，只说PVC防水",
        "consequence": "客户考虑后流失，因为普通PVC户外会老化，客户觉得不适用",
    }

    # 8) skills: 删 [3]抗UV级推荐 + [4]户外适用性判断（本质是抗UV判断）
    obj["skills"] = [v for i, v in enumerate(obj["skills"]) if i not in (3, 4)]

    # 备注：required_questions[4] 的"UV打印"是工艺，保留；
    #       product_specs.工艺 的"UV打印"也保留（与抗UV级不是同一概念）

    return obj


def verify(obj: dict) -> list[str]:
    """验证修改后不再含抗UV级相关关键词（UV打印除外）。"""
    keywords = ["抗UV", "抗老化", "发黄", "褪色", "贵15%"]
    text = json.dumps(obj, ensure_ascii=False)
    return [kw for kw in keywords if kw in text]


def backup_db(db_path: str) -> str:
    backup_dir = os.path.join(
        os.path.dirname(db_path),
        f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    os.makedirs(backup_dir, exist_ok=True)
    dst = os.path.join(backup_dir, os.path.basename(db_path))
    shutil.copy2(db_path, dst)
    return backup_dir


def main():
    print("=" * 70)
    print("PVC 知识库去抗UV级（新建 v10，保留 v9 历史）")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"数据库不存在：{DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    row = load_pvc_knowledge(conn)
    if not row:
        print("未找到 PVC 知识库（category_id=1）")
        conn.close()
        return

    kn_id, kn_version, content_text = row
    print(f"当前版本: id={kn_id}  version={kn_version}")

    obj = json.loads(content_text)
    print(f"原 required_questions: {len(obj['required_questions'])} 条")
    print(f"原 common_objections: {len(obj['common_objections'])} 条")
    print(f"原 recommended_responses: {len(obj['recommended_responses'])} 条")
    print(f"原 key_knowledge: {len(obj['key_knowledge'])} 条")
    print(f"原 success_patterns: {len(obj['success_patterns'])} 条")
    print(f"原 failure_patterns: {len(obj['failure_patterns'])} 条")
    print(f"原 skills: {len(obj['skills'])} 条")
    print()

    new_obj = drop_uv(obj)
    print("修改后数组长度:")
    print(f"  required_questions: {len(new_obj['required_questions'])} 条")
    print(f"  common_objections: {len(new_obj['common_objections'])} 条")
    print(f"  recommended_responses: {len(new_obj['recommended_responses'])} 条")
    print(f"  key_knowledge: {len(new_obj['key_knowledge'])} 条")
    print(f"  success_patterns: {len(new_obj['success_patterns'])} 条")
    print(f"  failure_patterns: {len(new_obj['failure_patterns'])} 条")
    print(f"  skills: {len(new_obj['skills'])} 条")
    print()

    # 验证
    leftover = verify(new_obj)
    if leftover:
        print(f"❌ 验证失败，仍残留关键词: {leftover}")
        conn.close()
        return
    print("✅ 验证通过：无残留抗UV级关键词（UV打印已保留）")
    print()

    # 确认 dry-run 还是 commit
    if "--commit" not in os.sys.argv:
        print("=" * 70)
        print("DRY-RUN：未写入数据库")
        print("预览完毕，加 --commit 真正入库：")
        print(f"  python {os.path.basename(__file__)} --commit")
        print("=" * 70)
        conn.close()
        return

    # 备份
    backup_dir = backup_db(DB_PATH)
    print(f"✅ 已备份 → {backup_dir}")

    # 写入新版本 v10（不动 v9，保留历史）
    new_version = kn_version + 1
    new_content = json.dumps(new_obj, ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 沿用 v9 的 source_material_ids
    src_ids_row = cur.execute(
        "select source_material_ids from knowledge where id=?"
    , (kn_id,)).fetchone()
    src_ids = src_ids_row[0] if src_ids_row else None
    cur.execute(
        "INSERT INTO knowledge (category_id, content_json, version, source_material_ids, created_at, prompt_version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            1,
            new_content,
            new_version,
            src_ids,
            now,
            "v1.0",
        ),
    )
    conn.commit()
    print(f"✅ 已写入新版本: version={new_version}  created_at={now}")
    print()

    # 二次验证数据库
    cur2 = conn.execute(
        "select content_json from knowledge where category_id=1 order by version DESC limit 1"
    )
    latest = json.loads(cur2.fetchone()[0])
    leftover2 = verify(latest)
    if leftover2:
        print(f"❌ 数据库二次验证失败: {leftover2}")
    else:
        print("✅ 数据库二次验证通过")
        print(f"   新版本 ID: {cur.lastrowid}  version={new_version}")

    conn.close()
    print()
    print("=" * 70)
    print("完成。后端会自动加载最新版（get_knowledge_for_training 取 max version）")
    print("=" * 70)


if __name__ == "__main__":
    main()
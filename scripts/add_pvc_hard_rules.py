"""把《PVC 标牌代打业务 - 客服沟通标准话术手册》的规则写入知识库。

改动内容（新建 v11，不动 v10，遵守知识库版本化约定）：
1. required_questions 补「代打三要素」：尺寸 / 打印方式 / 孔位
2. 新增 hard_rules：5 条可直接判分的红线（含建议扣分值）
3. failure_patterns 补 2 条：一次性问多题、未出样就量产

用法：
    python scripts/add_pvc_hard_rules.py            # dry-run，只打印差异
    python scripts/add_pvc_hard_rules.py --apply    # 真正写入（自动备份 data/）
"""
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "backend" / "data" / "kefuxitong.db"
CATEGORY_KEYWORD = "PVC"

# 代打三要素：现有 required_questions 是「板材」角度（材质/厚度/使用环境），
# 缺了代打业务真正要确认的尺寸、打印方式、孔位
NEW_REQUIRED_QUESTIONS = [
    "确认标牌尺寸（常规 32*68mm，或客户定制尺寸）",
    "确认打印方式（白底黑字、单面还是双面打印）",
    "确认孔位（单孔 / 双孔 / 无孔）",
]

# 5 条红线：来自话术手册，违反即扣分，可直接作为评分依据
HARD_RULES = [
    {
        "rule": "一问一答：禁止一次性抛出多个问题",
        "detail": "尺寸、颜色、打印方式、孔位、数量必须逐个确认，客户答完一个再问下一个。"
                  "一次性问完（如『尺寸颜色数量打印方式孔位都要什么』）直接扣分。",
        "deduct": 15,
    },
    {
        "rule": "尺寸确认三要素同步：发实物图 + 报出 32*68mm + 请客户确认",
        "detail": "只问『要多大』而不发图、不报具体尺寸，视为标准动作未执行。",
        "deduct": 15,
    },
    {
        "rule": "数量 > 1000 片：必须先核对内容表格，并主动提出语音沟通",
        "detail": "大批量直接报价、不核对表格，存在整批打印错误报废的风险。",
        "deduct": 10,
    },
    {
        "rule": "议价权限上限：每片最多让 0.05 元，且须说明是向领导申请的最大权限",
        "detail": "超权限让价、或轻易让步却不明示底线，视为违规。",
        "deduct": 10,
    },
    {
        "rule": "出样 → 客户明确确认 → 才安排批量生产",
        "detail": "未出样、或发了样牌但没等客户确认就量产，是返工高发点。",
        "deduct": 15,
    },
]

NEW_FAILURE_PATTERNS = [
    {
        "scenario": "客户首次咨询，需求不明确",
        "mistake": "一次性抛出尺寸、颜色、打印方式、孔位、数量多个问题",
        "consequence": "客户答不全或直接不回，对话冷场流失",
    },
    {
        "scenario": "客户确认订单后",
        "mistake": "未出样或发了样牌没等客户确认就安排批量生产",
        "consequence": "内容/排版有误导致整批返工，成本与交期双失",
    },
]

# 注意：sales_process 现有条目不带序号（如「确认需求（规格、数量、用途）」），保持一致
SALES_PROCESS_APPEND = "出样并等客户确认后再批量生产"


def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)

    row = con.execute(
        "select k.id, k.version, k.content_json, c.id, c.name "
        "from knowledge k join category c on c.id = k.category_id "
        "where c.name like ? order by k.version desc limit 1",
        (f"%{CATEGORY_KEYWORD}%",),
    ).fetchone()
    if not row:
        print("未找到 PVC 品类知识库")
        return

    kid, ver, content_json, cat_id, cat_name = row
    k = json.loads(content_json)
    print(f"当前：knowledge id={kid} version={ver} 品类={cat_name}\n")

    new_k = json.loads(json.dumps(k, ensure_ascii=False))  # 深拷贝
    new_ver = ver + 1

    # 1. 补代打三要素（插入到数量之前，保持询问顺序自然）
    rq = list(new_k.get("required_questions") or [])
    for item in NEW_REQUIRED_QUESTIONS:
        if item not in rq:
            rq.append(item)
    new_k["required_questions"] = rq

    # 2. 新增红线
    new_k["hard_rules"] = HARD_RULES

    # 3. 补失败模式
    fp = list(new_k.get("failure_patterns") or [])
    for item in NEW_FAILURE_PATTERNS:
        if item not in fp:
            fp.append(item)
    new_k["failure_patterns"] = fp

    # 4. 销售流程补出样确认
    sp = list(new_k.get("sales_process") or [])
    if SALES_PROCESS_APPEND not in sp:
        sp.append(SALES_PROCESS_APPEND)
    new_k["sales_process"] = sp

    print("=" * 60)
    print("差异预览")
    print("=" * 60)
    print(f"version: {ver} -> {new_ver}")
    print(f"\nrequired_questions: {len(k.get('required_questions') or [])} 条"
          f" -> {len(rq)} 条")
    for item in NEW_REQUIRED_QUESTIONS:
        print(f"  + {item}")
    print(f"\n新增 hard_rules {len(HARD_RULES)} 条：")
    for r in HARD_RULES:
        print(f"  - [扣 {r['deduct']} 分] {r['rule']}")
    print(f"\nfailure_patterns: {len(k.get('failure_patterns') or [])} 条"
          f" -> {len(fp)} 条")
    print(f"\nsales_process 新增：{SALES_PROCESS_APPEND}")

    if not apply:
        print("\n[dry-run] 未写入。确认无误后加 --apply 执行。")
        return

    # 备份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backend" / "data" / f"backup_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB, backup_dir / "kefuxitong.db")
    print(f"\n已备份数据库到 {backup_dir}")

    # 继承上一版的素材来源与 prompt 版本，避免新版本元数据为空
    prev = con.execute(
        "select source_material_ids, prompt_version from knowledge where id=?", (kid,)
    ).fetchone()
    prev_src, prev_pv = (prev or (None, None))

    cur = con.cursor()
    cur.execute(
        "insert into knowledge (category_id, content_json, version, source_material_ids, prompt_version) "
        "values (?, ?, ?, ?, ?)",
        (cat_id, json.dumps(new_k, ensure_ascii=False), new_ver, prev_src, prev_pv),
    )
    con.commit()
    print(f"已写入 knowledge version={new_ver} (id={cur.lastrowid})")

    check = con.execute(
        "select version from knowledge where category_id=? order by version desc limit 1",
        (cat_id,),
    ).fetchone()
    print(f"当前最高版本：{check[0]}（get_knowledge_for_training 会自动取这个）")
    con.close()


if __name__ == "__main__":
    main()

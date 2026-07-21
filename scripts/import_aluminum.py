"""一次性入库脚本：创建「铝板腐蚀与激光雕刻」品类 + 导入 7 个 MD 材料 + LLM 提取知识。"""
import os
import sys
from pathlib import Path

# 先切到 backend 目录加载 .env
backend_dir = Path(__file__).resolve().parent.parent / "backend"
os.chdir(str(backend_dir))
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.database import SessionLocal
from app.models import Category, Material
from app.ai.knowledge import extract_knowledge

MATERIALS_DIR = backend_dir.parent / "uploads" / "铝板腐蚀与激光雕刻"

FILES = [
    ("01_产品知识.md", "product", "normal"),
    ("02_销售流程SOP.md", "sop", "normal"),
    ("03_FAQ客户问题库.md", "faq", "normal"),
    ("04_报价规则.md", "product", "normal"),
    ("05_风险规则.md", "product", "normal"),
    ("06_AI客户画像.md", "training", "normal"),
    ("07_AI评分标准.md", "training", "normal"),
]

db = SessionLocal()

# 1. 创建品类
cat = Category(name="铝板腐蚀与激光雕刻", description="铝板腐蚀与激光雕刻工艺客服场景训练")
db.add(cat)
db.flush()
print(f"[1] 创建品类: {cat.name} (id={cat.id})")

# 2. 逐个写入 Material
for filename, source_type, quality in FILES:
    filepath = MATERIALS_DIR / filename
    content = filepath.read_text(encoding="utf-8")
    rel_path = f"uploads/铝板腐蚀与激光雕刻/{filename}"
    m = Material(
        category_id=cat.id,
        filename=filename,
        file_path=rel_path,
        content_text=content,
        file_type="md",
        file_size=len(content.encode("utf-8")),
        quality=quality,
        source_type=source_type,
    )
    db.add(m)
    print(f"  [2] Material: {filename} → source_type={source_type}")

db.commit()
print(f"[3] 已提交 {len(FILES)} 条 Material 记录")

# 3. LLM 提取知识
print("[4] 开始 LLM 提取知识 ...")
k, used_llm = extract_knowledge(db, cat.id)
content = k.get_content()
print(f"[5] 提取完成: version={k.version}, used_llm={used_llm}")
print(f"  required_questions={content.get('required_questions')}")
print(f"  sales_process={content.get('sales_process')}")
print(f"  product_specs keys={list(content.get('product_specs', {}).keys())}")
print(f"  recommended_responses count={len(content.get('recommended_responses', []))}")
print(f"  success_patterns count={len(content.get('success_patterns', []))}")
print(f"  failure_patterns count={len(content.get('failure_patterns', []))}")
print(f"  customer_profiles count={len(content.get('customer_profiles', []))}")
print()

# 4. 手动增强 customer_profiles（06 内容结构化为 JSON）
profiles = [
    {
        "name": "陈经理",
        "role": "设备厂家采购",
        "traits": "注重价格、关注交期，不会一次提供完整需求。第一句话通常是\"这个多少钱？\"，不会主动告诉尺寸、数量、用途",
        "first_message_style": "这个多少钱？",
        "test_focus": "客服主动引导需求的能力——能否在客户不主动给信息的情况下，一步步追问出尺寸、数量、材质、用途"
    },
    {
        "name": "工程采购",
        "role": "工程公司采购",
        "traits": "关注材质、使用寿命、工艺效果，会问专业问题。常见异议：\"为什么不用普通材料？\"\"为什么价格这么高？\"",
        "first_message_style": "你好，我们有个工程项目需要一批标识牌，想问一下你们能做铝板腐蚀吗？",
        "test_focus": "客服的专业解释能力——能否清晰说明材质区别、工艺优缺点、价格构成"
    }
]
content["customer_profiles"] = profiles
k.set_content(content)
db.commit()
print("[6] 手动增强 customer_profiles (2 个画像)")

# 5. 验证
db.refresh(k)
final = k.get_content()
print(f"[7] 最终验证: version={k.version}, prompt_version={k.prompt_version}")
print(f"  customer_profiles={len(final.get('customer_profiles', []))} 个画像")
for p in final.get("customer_profiles", []):
    print(f"    - {p.get('name')} ({p.get('role')})")

db.close()
print("\n✅ 导入完成！")

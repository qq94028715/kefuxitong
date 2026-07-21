"""金属铭牌与PVC标牌培训资料入库。

拆分策略：
- cat 2（金属铭牌训练）：8 个 MD 完整入库，scoring_dimensions 用五维
- cat 1（PVC训练）：从 01/06 提取 PVC 相关内容作为补充材料
"""
import sys
sys.path.insert(0, 'backend')
from dotenv import load_dotenv
load_dotenv('backend/.env')

from app.database import SessionLocal
from app.models import Category, Material, Knowledge
from app.ai.knowledge import extract_knowledge
from pathlib import Path
import hashlib, time

UPLOAD_BASE = Path('uploads/金属铭牌与PVC标牌')

# 金属铭牌五维评分标准
METAL_SCORING_DIMS = {
    "需求挖掘": 30,
    "产品专业": 25,
    "沟通能力": 20,
    "成交推进": 15,
    "风险控制": 10,
}

FILES = [
    ("01_产品知识.md", "product", "normal"),
    ("02_客户需求分析.md", "sop", "normal"),
    ("03_销售流程SOP.md", "sop", "normal"),
    ("04_FAQ客户问题库.md", "faq", "normal"),
    ("05_报价规则.md", "product", "normal"),
    ("06_工艺选择规则.md", "product", "normal"),
    ("07_AI客户画像.md", "training", "normal"),
    ("08_AI评分标准.md", "training", "normal"),
]

# PVC补充材料（从01和06提取PVC相关内容）
PVC_CONTENT = """# PVC标牌补充知识

## PVC标牌特点
PVC属于塑料类标识材料。
优势：成本较低、加工灵活、重量轻、适合批量制作。
常见应用：电力行业、光伏行业、水表标识、通信设备。

## PVC适用场景
适合成本敏感型客户。普通设备标识可以考虑PVC。

## 客户选择逻辑
先了解使用环境，再推荐材料。
户外长期使用优先304不锈钢，普通设备标识可以考虑PVC，高端设备推荐金属铭牌。
"""

def hash8(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]

db = SessionLocal()

# ===== 1. cat 2 金属铭牌：8 文件全部入库 =====
cat_metal = db.query(Category).filter(Category.id == 2).first()
print(f'[cat 2] 金属铭牌训练 (当前 materials={db.query(Material).filter(Material.category_id == 2).count()})')

for fname, stype, quality in FILES:
    fp = UPLOAD_BASE / fname
    text = fp.read_text(encoding='utf-8')
    h = hash8(f'{2}_{fname}_{time.time()}')
    # 检查是否已存在
    existing = db.query(Material).filter(
        Material.category_id == 2, Material.filename == fname
    ).first()
    if existing:
        print(f'  跳过已存在: {fname}')
        continue
    m = Material(
        category_id=2,
        filename=fname,
        file_path=f'uploads/金属铭牌与PVC标牌/{fname}',
        file_type='md',
        file_size=len(text.encode('utf-8')),
        content_text=text,
        quality=quality,
        source_type=stype,
    )
    db.add(m)
    print(f'  + {fname} ({stype}/{quality}, {len(text)}字)')
db.commit()

# 触发 LLM 提取 knowledge
print('\n[cat 2] 触发 LLM 知识提取...')
k, used_llm = extract_knowledge(db, 2)
content = k.get_content()
print(f'  used_llm={used_llm} version={k.version} prompt_version={k.prompt_version}')
print(f'  required_questions: {content.get("required_questions")}')
print(f'  sales_process: {content.get("sales_process")}')
print(f'  recommended_responses: {len(content.get("recommended_responses", []))} 条')
print(f'  customer_profiles: {len(content.get("customer_profiles", []))} 个')
print(f'  scoring_dimensions: {content.get("scoring_dimensions")}')

# 手动增强 scoring_dimensions 为五维，增强 customer_profiles
content['scoring_dimensions'] = METAL_SCORING_DIMS

# 增强客户画像
if not content.get('customer_profiles'):
    content['customer_profiles'] = [
        {
            "name": "陈经理",
            "role": "设备厂家采购",
            "traits": "关注价格和交期，会比较供应商，不主动提供全部信息",
            "first_message_style": "做一个铭牌多少钱？",
            "test_focus": "主动引导需求的能力，不能被动接受模糊询价"
        },
        {
            "name": "工程客户",
            "role": "工程公司采购",
            "traits": "关注材质、效果和使用寿命，常质疑价格合理性",
            "first_message_style": "你们用什么材料？户外能用多久？",
            "test_focus": "专业解释能力，是否能清晰说明材质区别和工艺优势"
        }
    ]

k.set_content(content)
db.commit()
print(f'\n[cat 2] 已增强: scoring_dimensions={METAL_SCORING_DIMS}')
print(f'  customer_profiles: {len(content["customer_profiles"])} 个')


# ===== 2. cat 1 PVC：补充材料 =====
cat_pvc = db.query(Category).filter(Category.id == 1).first()
print(f'\n[cat 1] PVC训练 (当前 materials={db.query(Material).filter(Material.category_id == 1).count()})')

existing_pvc = db.query(Material).filter(
    Material.category_id == 1, Material.filename == '金属铭牌PVC补充知识.md'
).first()
if existing_pvc:
    print('  补充材料已存在，跳过')
else:
    m = Material(
        category_id=1,
        filename='金属铭牌PVC补充知识.md',
        file_path='uploads/金属铭牌与PVC标牌/PVC补充.md',
        file_type='md',
        file_size=len(PVC_CONTENT.encode('utf-8')),
        content_text=PVC_CONTENT,
        quality='normal',
        source_type='training',
    )
    db.add(m)
    db.commit()
    print(f'  + 金属铭牌PVC补充知识.md (training, {len(PVC_CONTENT)}字)')

    # PVC不重新LLM提取（已有v6知识库），仅规则模式追加补充
    print('  PVC 已有 LLM 知识库 v6，跳过重新提取')

print('\n✅ 全部入库完成')
db.close()

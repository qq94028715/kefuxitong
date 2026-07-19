"""结构化知识提取：材料 → AI 总结 → 结构化 JSON。

核心原则（用户强调）：
不要把原始聊天记录直接喂给模拟客户。而是先由本模块用 LLM 把
材料总结成结构化知识 JSON（required_questions / common_objections /
recommended_responses / product_specs 等），simulator 与 evaluator
都只依赖这份知识，不再接触原始材料。

无 LLM 时走规则 fallback（关键词扫描），质量有限但保证流程可跑。
"""
import json
import logging

from sqlalchemy.orm import Session

from ..models import Category, Knowledge
from . import llm, prompt
from .trainer import build_training_text

logger = logging.getLogger(__name__)

# 截断长度：防止材料过长超出 LLM 上下文
MAX_MATERIAL_CHARS = 8000


def get_latest_knowledge(db: Session, category_id: int) -> Knowledge | None:
    """获取某分类最新版知识。"""
    return (
        db.query(Knowledge)
        .filter(Knowledge.category_id == category_id)
        .order_by(Knowledge.version.desc())
        .first()
    )


def get_knowledge_for_training(db: Session, category_id: int) -> dict:
    """获取训练用的知识 JSON。无知识时抛异常。"""
    k = get_latest_knowledge(db, category_id)
    if not k:
        raise ValueError("该分类尚未提取知识库，请联系管理员先上传材料并提取")
    return k.get_content()


def extract_knowledge(db: Session, category_id: int) -> tuple[Knowledge, bool]:
    """从材料提取结构化知识，存入 knowledge 表。

    返回 (knowledge 对象, 是否使用了 LLM)。
    无材料时抛 ValueError；无 LLM 时走规则 fallback。
    """
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise ValueError("分类不存在")

    text, material_ids = build_training_text(db, category_id)
    if not text:
        raise ValueError("该分类没有可用材料，请先上传材料")

    used_llm = False
    content: dict | None = None

    if llm.is_llm_enabled():
        content = _extract_with_llm(text, category.name)
        if content:
            used_llm = True
        else:
            logger.warning("LLM 调用失败，回退到规则模式")

    if not content:
        content = _extract_with_rules(text, category.name)

    # 版本号递增
    latest = get_latest_knowledge(db, category_id)
    version = (latest.version + 1) if latest else 1

    k = Knowledge(
        category_id=category_id,
        version=version,
    )
    k.set_content(content)
    k.set_source_ids(material_ids)
    db.add(k)
    db.commit()
    db.refresh(k)
    return k, used_llm


def _extract_with_llm(materials_text: str, category_name: str) -> dict | None:
    """用 LLM + knowledge.txt 提取结构化知识。"""
    p = prompt.load_prompt(
        "knowledge",
        category_name=category_name,
        materials=materials_text[:MAX_MATERIAL_CHARS],
    )
    messages = [
        {"role": "system", "content": "你是一名数据工程师，只输出 JSON，不输出任何解释。"},
        {"role": "user", "content": p},
    ]
    result = llm.chat_json(messages, temperature=0.3)
    if result and "required_questions" in result:
        return result
    return None


# ---------- 规则 fallback ----------
_FALLBACK_KEYWORDS = [
    "尺寸", "数量", "厚度", "材质", "用途", "交期", "起订量",
    "价格", "工艺", "耐温", "防水", "颜色", "规格", "数量", "字母",
]


def _extract_with_rules(text: str, category_name: str) -> dict:
    """无 LLM 时的简易提取：扫描关键词。质量有限，仅保证流程可跑。"""
    found = [k for k in _FALLBACK_KEYWORDS if k in text]
    if not found:
        found = ["尺寸", "数量", "材质", "用途"]
    # 去重保序
    seen: set[str] = set()
    required: list[str] = []
    for k in found:
        if k not in seen:
            seen.add(k)
            required.append(k)
    return {
        "category": category_name,
        "product_summary": f"{category_name}相关产品",
        "required_questions": required,
        "common_objections": ["价格", "交期"],
        "recommended_responses": [],
        "product_specs": {},
        "key_knowledge": [],
        "_note": "规则模式提取（未配置 LLM_API_KEY），质量有限。"
        "配置后重新提取可获得完整知识库。",
    }

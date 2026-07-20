"""材料处理：加载、拆分、去重。

管理员上传聊天记录 / 产品资料后，trainer 负责：
1. 加载该分类下所有材料的纯文本
2. 按段落拆分成 chunk（防止单次喂给 LLM 过长）
3. 去重（完全相同的段落只保留一个）
4. 重新拼成一段文本交给 knowledge 模块提取
"""
import re

from sqlalchemy.orm import Session

from ..models import Material


def load_all_materials(db: Session, category_id: int) -> list[Material]:
    """加载某分类下全部材料，按上传顺序。"""
    return (
        db.query(Material)
        .filter(Material.category_id == category_id)
        .order_by(Material.id)
        .all()
    )


def materials_to_text(materials: list[Material]) -> str:
    """把多个材料拼成一段文本，带文件名分隔标记。"""
    parts = []
    for m in materials:
        content = (m.content_text or "").strip()
        if not content:
            continue
        parts.append(f"【文件：{m.filename}】\n{content}")
    return "\n\n".join(parts)


def split_chunks(text: str, max_len: int = 1500) -> list[str]:
    """按空行分段，单段过长则硬切，每段不超过 max_len 字符。"""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(current) + len(p) + 2 <= max_len:
            current = (current + "\n\n" + p) if current else p
        else:
            if current:
                chunks.append(current)
            # 单段超长，硬切
            while len(p) > max_len:
                chunks.append(p[:max_len])
                p = p[max_len:]
            current = p
    if current:
        chunks.append(current)
    return chunks


def deduplicate(chunks: list[str]) -> list[str]:
    """简单去重：完全相同的段落只保留首个。"""
    seen: set[str] = set()
    result: list[str] = []
    for c in chunks:
        key = c.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(c)
    return result


def build_training_text(
    db: Session, category_id: int
) -> tuple[str, list[int]]:
    """加载分类下所有材料 → 拼接 → 拆分 → 去重 → 重新拼接。

    返回 (处理后文本, 参与的材料ID列表)。
    """
    materials = load_all_materials(db, category_id)
    if not materials:
        return "", []
    raw = materials_to_text(materials)
    chunks = deduplicate(split_chunks(raw))
    text = "\n\n".join(chunks)
    return text, [m.id for m in materials]


def build_training_text_by_quality(
    db: Session, category_id: int
) -> dict[str, tuple[str, list[int]]]:
    """按案例类型分别加载材料并处理。

    返回 {quality: (text, material_ids)} 字典。
    quality 为 excellent / normal / failed，只包含有材料的类型。
    """
    materials = load_all_materials(db, category_id)
    if not materials:
        return {}

    result: dict[str, tuple[str, list[int]]] = {}
    for quality in ("excellent", "normal", "failed"):
        subset = [m for m in materials if (m.quality or "normal") == quality]
        if not subset:
            continue
        raw = materials_to_text(subset)
        chunks = deduplicate(split_chunks(raw))
        text = "\n\n".join(chunks)
        result[quality] = (text, [m.id for m in subset])

    return result

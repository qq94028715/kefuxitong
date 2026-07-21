"""AI 评分（evaluator）。

对话结束后，用 LLM 扮演客服主管，对整段对话结构化评分。
输出：{score, dimension_scores, advantages, mistakes, suggestions, summary}，存入 score 表。

v1.2：评分维度改为 per-category，从 knowledge JSON 的 scoring_dimensions 字段读取。
每个品类可以有不同的评分维度和权重，不再硬编码。
LLM 模式：用 score.txt prompt，维度动态注入。
规则模式：基于关键词命中度评分（检查客服是否提到必要信息）。
"""
import json

from . import llm, prompt
from .simulator import SUMMARY_THRESHOLD, RECENT_KEEP

# 默认评分维度（knowledge 未提供时兜底）
_DEFAULT_DIMENSIONS = {
    "需求确认": 30,
    "产品专业": 25,
    "报价能力": 25,
    "风险控制": 20,
}


def build_dialogue_text(messages: list, summary: str = "") -> str:
    """把对话格式化为评分用文本。summary 非空且对话较长时，用摘要替代早期内容压上下文。"""
    if not messages:
        return "（无对话内容）"
    if summary and len(messages) > SUMMARY_THRESHOLD:
        recent = messages[-RECENT_KEEP:]
        recent_text = "\n".join(
            f"{'客服' if m.role == 'agent' else '客户'}：{m.content}" for m in recent
        )
        return f"[对话历史摘要]\n{summary}\n\n[最近 {len(recent)} 条对话]\n{recent_text}"
    lines = []
    for m in messages:
        role = "客服" if m.role == "agent" else "客户"
        lines.append(f"{role}：{m.content}")
    return "\n".join(lines)


def evaluate_session(
    messages: list,
    knowledge: dict,
    category_name: str,
    conversation_summary: str = "",
) -> dict:
    """评估一次训练对话。

    返回 dict：
    {
        "score": float,               # 0~100 总分
        "dimension_scores": dict,     # 各维度分数 {"需求确认": 35, ...}
        "scoring_dimensions": dict,   # 各维度满分 {"需求确认": 30, ...}（前端渲染用）
        "advantages": list[str],      # 做得好的点
        "mistakes": list[str],        # 失误或遗漏
        "suggestions": list[str],     # 改进建议
        "summary": str,               # 一句话总评
    }
    """
    dimensions = knowledge.get("scoring_dimensions") or _DEFAULT_DIMENSIONS
    if llm.is_llm_enabled():
        result = _evaluate_with_llm(messages, knowledge, category_name, dimensions, conversation_summary)
        if result:
            return result
        # LLM 失败 → 规则 fallback
    return _evaluate_with_rules(messages, knowledge, category_name, dimensions)


def _evaluate_with_llm(
    messages: list,
    knowledge: dict,
    category_name: str,
    dimensions: dict,
    conversation_summary: str = "",
) -> dict | None:
    dialogue = build_dialogue_text(messages, conversation_summary)
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    sales_process = knowledge.get("sales_process") or []
    # 构造维度描述文本（注入 score.txt）
    dim_items = []
    for name, max_score in dimensions.items():
        dim_items.append(f"{name}（满分 {max_score} 分）")
    scoring_dimensions_text = "、".join(dim_items)
    dim_output_items = []
    for name, max_score in dimensions.items():
        dim_output_items.append(f'    "{name}": 0到{max_score}的整数')
    dim_output_text = ",\n".join(dim_output_items)
    p = prompt.load_prompt(
        "score",
        knowledge_json=knowledge_json,
        category_name=category_name,
        dialogue=dialogue,
        sales_process=json.dumps(sales_process, ensure_ascii=False),
        scoring_dimensions_text=scoring_dimensions_text,
        scoring_dimensions_output=dim_output_text,
    )
    llm_messages = [
        {
            "role": "system",
            "content": "你是一名客服主管，只输出 JSON，不输出任何解释。",
        },
        {"role": "user", "content": p},
    ]
    result = llm.chat_json(llm_messages, temperature=0.2)
    if result and "score" in result:
        return _normalize(result, dimensions)
    return None


def _normalize(data: dict, dimensions: dict) -> dict:
    """规整 LLM 返回的评分结构，确保字段类型正确。dimensions 为 {维度名: 满分}。"""

    def as_list(v) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v if x]
        if isinstance(v, str) and v:
            return [v]
        return []

    def normalize_dimension_scores(raw) -> dict:
        """规整维度分数，确保每个维度都有值且不超满分。"""
        if not isinstance(raw, dict):
            raw = {}
        result = {}
        for dim, max_score in dimensions.items():
            try:
                val = float(raw.get(dim, 0))
            except (TypeError, ValueError):
                val = 0.0
            val = max(0.0, min(max_score, val))
            result[dim] = round(val, 1)
        return result

    # 解析维度分数
    dimension_scores = normalize_dimension_scores(data.get("dimension_scores"))

    # 总分：优先用 LLM 返回的 score，但如果四维之和差异过大则用四维之和
    try:
        llm_score = float(data.get("score", 0))
    except (TypeError, ValueError):
        llm_score = 0.0
    dim_sum = sum(dimension_scores.values())
    # 如果 LLM 总分和维度之和差异超过 5 分，以维度之和为准
    if abs(llm_score - dim_sum) > 5:
        score = dim_sum
    else:
        score = llm_score
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "dimension_scores": dimension_scores,
        "scoring_dimensions": dict(dimensions),
        "advantages": as_list(data.get("advantages")),
        "mistakes": as_list(data.get("mistakes")),
        "suggestions": as_list(data.get("suggestions")),
        "summary": str(data.get("summary", "")),
    }


# ---------- 规则 fallback ----------


def _evaluate_with_rules(
    messages: list,
    knowledge: dict,
    category_name: str,
    dimensions: dict,
) -> dict:
    """无 LLM 时：基于关键词命中度评分。

    检查客服回答中是否提到了 required_questions 中的各项。
    维度从 scoring_dimensions 动态读取，不再硬编码。
    """
    required = knowledge.get("required_questions") or [
        "尺寸", "数量", "材质", "用途",
    ]
    agent_text = " ".join(m.content for m in messages if m.role == "agent")

    hit = [r for r in required if r in agent_text]
    miss = [r for r in required if r not in agent_text]
    hit_ratio = len(hit) / len(required) if required else 0

    # 按 scoring_dimensions 动态分配分数
    dim_names = list(dimensions.keys())
    dim_maxes = list(dimensions.values())
    dimension_scores: dict[str, float] = {}

    for i, (name, max_score) in enumerate(dimensions.items()):
        if i == 0:
            # 第一维度 = 需求确认，按命中比例
            dimension_scores[name] = round(max_score * hit_ratio, 1)
        else:
            # 其余维度按关键词命中数均匀分配
            all_kw = _get_dimension_keywords(name)
            kw_hits = sum(1 for k in all_kw if k in agent_text)
            dimension_scores[name] = round(min(max_score, kw_hits * 5), 1)

    score = round(sum(dimension_scores.values()), 1)

    advantages = [f"确认了「{h}」" for h in hit] or ["态度积极，有回应"]
    mistakes = [f"未确认「{m}」" for m in miss] or []
    suggestions = (
        [f"建议主动询问「{m}」" for m in miss]
        or ["整体表现合格，继续保持"]
    )
    summary = (
        f"规则评分：命中 {len(hit)}/{len(required)} 项必要信息。"
        "（配置 LLM_API_KEY 可获得 AI 主管的精细评分）"
    )
    return {
        "score": score,
        "dimension_scores": dimension_scores,
        "scoring_dimensions": dict(dimensions),
        "advantages": advantages,
        "mistakes": mistakes,
        "suggestions": suggestions,
        "summary": summary,
    }


# 维度 → 关键词映射（规则评分用）
_DIM_KEYWORD_MAP: dict[str, list[str]] = {
    "需求确认": ["尺寸", "数量", "材质", "用途", "环境", "厚度", "工艺"],
    "产品专业": ["mm", "厚度", "材质", "工艺", "PVC", "CPVC", "不锈钢", "铝",
                  "腐蚀", "丝印", "UV", "覆膜", "雕刻", "冲压", "激光", "304", "201"],
    "报价能力": ["报价", "价格", "单价", "总价", "材料成本", "利润", "成本", "元"],
    "风险控制": ["交期", "发货", "风险", "注意", "限制", "不能", "不建议", "建议",
                  "可能", "避免", "售后"],
    "沟通能力": ["您好", "请问", "好的", "没问题", "可以", "建议", "推荐"],
    "成交推进": ["报价", "交期", "下单", "定金", "发货", "联系", "微信", "样品"],
    "需求挖掘": ["尺寸", "数量", "材质", "用途", "环境", "厚度", "工艺", "要求"],
}


def _get_dimension_keywords(dim_name: str) -> list[str]:
    """获取某维度对应的关键词列表（规则评分用）。"""
    # 先精确匹配
    if dim_name in _DIM_KEYWORD_MAP:
        return _DIM_KEYWORD_MAP[dim_name]
    # 模糊匹配：含"需求" → 用需求确认词表
    if "需求" in dim_name:
        return _DIM_KEYWORD_MAP["需求确认"]
    if "产品" in dim_name or "专业" in dim_name:
        return _DIM_KEYWORD_MAP["产品专业"]
    if "报价" in dim_name:
        return _DIM_KEYWORD_MAP["报价能力"]
    if "风险" in dim_name:
        return _DIM_KEYWORD_MAP["风险控制"]
    if "沟通" in dim_name:
        return _DIM_KEYWORD_MAP["沟通能力"]
    if "成交" in dim_name:
        return _DIM_KEYWORD_MAP["成交推进"]
    # 通用兜底
    return ["价格", "尺寸", "材质", "交期"]

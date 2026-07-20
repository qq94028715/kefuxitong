"""AI 评分（evaluator）。

对话结束后，用 LLM 扮演客服主管，对整段对话结构化评分。
输出：{score, dimension_scores, advantages, mistakes, suggestions, summary}，存入 score 表。

四维评分（用户指定权重）：
- 需求确认 40 分
- 产品知识 20 分
- 销售技巧 20 分
- 成交推进 20 分

LLM 模式：用 score.txt prompt，四维评分。
规则模式：基于关键词命中度评分（检查客服是否提到必要信息）。
"""
import json

from . import llm, prompt
from .simulator import SUMMARY_THRESHOLD, RECENT_KEEP

# 四维评分维度及其满分
DIMENSIONS = {
    "需求确认": 40,
    "产品知识": 20,
    "销售技巧": 20,
    "成交推进": 20,
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
        "dimension_scores": dict,     # 四维分数 {"需求确认": 35, ...}
        "advantages": list[str],      # 做得好的点
        "mistakes": list[str],        # 失误或遗漏
        "suggestions": list[str],     # 改进建议
        "summary": str,               # 一句话总评
    }
    """
    if llm.is_llm_enabled():
        result = _evaluate_with_llm(messages, knowledge, category_name, conversation_summary)
        if result:
            return result
        # LLM 失败 → 规则 fallback
    return _evaluate_with_rules(messages, knowledge, category_name)


def _evaluate_with_llm(
    messages: list,
    knowledge: dict,
    category_name: str,
    conversation_summary: str = "",
) -> dict | None:
    dialogue = build_dialogue_text(messages, conversation_summary)
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    sales_process = knowledge.get("sales_process") or []
    p = prompt.load_prompt(
        "score",
        knowledge_json=knowledge_json,
        category_name=category_name,
        dialogue=dialogue,
        sales_process=json.dumps(sales_process, ensure_ascii=False),
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
        return _normalize(result)
    return None


def _normalize(data: dict) -> dict:
    """规整 LLM 返回的评分结构，确保字段类型正确。"""

    def as_list(v) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v if x]
        if isinstance(v, str) and v:
            return [v]
        return []

    def normalize_dimension_scores(raw) -> dict:
        """规整四维分数，确保每个维度都有值且不超满分。"""
        if not isinstance(raw, dict):
            raw = {}
        result = {}
        for dim, max_score in DIMENSIONS.items():
            try:
                val = float(raw.get(dim, 0))
            except (TypeError, ValueError):
                val = 0.0
            val = max(0.0, min(max_score, val))
            result[dim] = round(val, 1)
        return result

    # 解析四维分数
    dimension_scores = normalize_dimension_scores(data.get("dimension_scores"))

    # 总分：优先用 LLM 返回的 score，但如果四维之和差异过大则用四维之和
    try:
        llm_score = float(data.get("score", 0))
    except (TypeError, ValueError):
        llm_score = 0.0
    dim_sum = sum(dimension_scores.values())
    # 如果 LLM 总分和四维之和差异超过 5 分，以四维之和为准
    if abs(llm_score - dim_sum) > 5:
        score = dim_sum
    else:
        score = llm_score
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "dimension_scores": dimension_scores,
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
) -> dict:
    """无 LLM 时：基于关键词命中度评分。

    检查客服回答中是否提到了 required_questions 中的各项。
    四维分数按命中情况分配：
    - 需求确认（40分）：按 required_questions 命中比例
    - 产品知识（20分）：是否提到产品规格/工艺关键词
    - 销售技巧（20分）：是否有礼貌用语/确认语句
    - 成交推进（20分）：是否提到报价/交期/下单
    """
    required = knowledge.get("required_questions") or [
        "尺寸", "数量", "材质", "用途",
    ]
    agent_text = " ".join(m.content for m in messages if m.role == "agent")

    hit = [r for r in required if r in agent_text]
    miss = [r for r in required if r not in agent_text]

    # 需求确认：按命中比例
    hit_ratio = len(hit) / len(required) if required else 0
    dim_confirm = round(40 * hit_ratio, 1)

    # 产品知识：检查规格/工艺关键词
    spec_keywords = ["mm", "厚度", "材质", "工艺", "PVC", "CPVC", "不锈钢", "铝",
                     "腐蚀", "丝印", "UV", "覆膜", "雕刻", "冲压"]
    spec_hits = sum(1 for k in spec_keywords if k in agent_text)
    dim_knowledge = round(min(20, spec_hits * 5), 1)

    # 销售技巧：检查礼貌/确认用语
    skill_keywords = ["您好", "请问", "好的", "没问题", "可以", "建议", "推荐"]
    skill_hits = sum(1 for k in skill_keywords if k in agent_text)
    dim_skill = round(min(20, skill_hits * 5), 1)

    # 成交推进：检查成交关键词
    deal_keywords = ["报价", "交期", "下单", "定金", "发货", "联系", "微信", "样品"]
    deal_hits = sum(1 for k in deal_keywords if k in agent_text)
    dim_deal = round(min(20, deal_hits * 5), 1)

    dimension_scores = {
        "需求确认": dim_confirm,
        "产品知识": dim_knowledge,
        "销售技巧": dim_skill,
        "成交推进": dim_deal,
    }
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
        "advantages": advantages,
        "mistakes": mistakes,
        "suggestions": suggestions,
        "summary": summary,
    }

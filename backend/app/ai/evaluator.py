"""AI 评分（evaluator）。

对话结束后，用 LLM 扮演客服主管，对整段对话结构化评分。
输出：{score, advantages, mistakes, suggestions, summary}，存入 score 表。

LLM 模式：用 score.txt prompt，五维度评分。
规则模式：基于关键词命中度评分（检查客服是否提到必要信息）。
"""
import json

from . import llm, prompt


def build_dialogue_text(messages: list) -> str:
    """把对话格式化为评分用文本。"""
    if not messages:
        return "（无对话内容）"
    lines = []
    for m in messages:
        role = "客服" if m.role == "agent" else "客户"
        lines.append(f"{role}：{m.content}")
    return "\n".join(lines)


def evaluate_session(
    messages: list,
    knowledge: dict,
    category_name: str,
) -> dict:
    """评估一次训练对话。

    返回 dict：
    {
        "score": float,           # 0~100
        "advantages": list[str],  # 做得好的点
        "mistakes": list[str],    # 失误或遗漏
        "suggestions": list[str], # 改进建议
        "summary": str,           # 一句话总评
    }
    """
    if llm.is_llm_enabled():
        result = _evaluate_with_llm(messages, knowledge, category_name)
        if result:
            return result
        # LLM 失败 → 规则 fallback
    return _evaluate_with_rules(messages, knowledge, category_name)


def _evaluate_with_llm(
    messages: list,
    knowledge: dict,
    category_name: str,
) -> dict | None:
    dialogue = build_dialogue_text(messages)
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    p = prompt.load_prompt(
        "score",
        knowledge_json=knowledge_json,
        category_name=category_name,
        dialogue=dialogue,
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

    try:
        score = float(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
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
    """
    required = knowledge.get("required_questions") or [
        "尺寸",
        "数量",
        "材质",
        "用途",
    ]
    agent_text = " ".join(m.content for m in messages if m.role == "agent")

    hit = [r for r in required if r in agent_text]
    miss = [r for r in required if r not in agent_text]

    hit_ratio = len(hit) / len(required) if required else 0
    # 映射到 15~90 分区间
    score = round(15 + hit_ratio * 75, 1)

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
        "advantages": advantages,
        "mistakes": mistakes,
        "suggestions": suggestions,
        "summary": summary,
    }

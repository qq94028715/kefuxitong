"""AI 模拟客户（simulator）。

基于结构化知识 JSON 模拟真实客户，与客服逐句对话。
关键：不直接喂原始聊天记录，只依赖 knowledge 提取后的结构化知识。

LLM 模式：用 customer.txt prompt，多轮自然对话，会追问。
规则模式：按 required_questions 逐条问，问完结束（保证无 key 也能跑）。
"""
import json

from . import llm, prompt

# 对话结束标记（simulator 返回此串表示客户主动结束）
END_MARKER = "[END]"


def build_history_text(messages: list) -> str:
    """把对话历史格式化为文本。messages 为 ChatMessage 列表。"""
    if not messages:
        return "（对话尚未开始）"
    lines = []
    for m in messages:
        role = "客服" if m.role == "agent" else "客户"
        lines.append(f"{role}：{m.content}")
    return "\n".join(lines)


def generate_customer_reply(
    knowledge: dict,
    history: list,
    category_name: str,
    turn_count: int,
    max_turns: int,
) -> str:
    """生成 AI 客户的下一句话。

    turn_count: 已完成的对话轮数（客服已回答的次数）
    返回 END_MARKER 表示客户主动结束对话。
    """
    if llm.is_llm_enabled():
        reply = _reply_with_llm(
            knowledge, history, category_name, turn_count, max_turns
        )
        if reply:
            reply = reply.strip().strip('"').strip("'")
            # 容错：LLM 可能输出带角色名前缀
            for prefix in ("客户：", "客户:", "AI：", "AI:"):
                if reply.startswith(prefix):
                    reply = reply[len(prefix):].strip()
            return reply
        # LLM 失败 → 规则 fallback
    return _reply_with_rules(knowledge, history, turn_count, max_turns)


def _reply_with_llm(
    knowledge: dict,
    history: list,
    category_name: str,
    turn_count: int,
    max_turns: int,
) -> str | None:
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    history_text = build_history_text(history)
    p = prompt.load_prompt(
        "customer",
        knowledge_json=knowledge_json,
        category_name=category_name,
        history=history_text,
        turn_count=turn_count,
        max_turns=max_turns,
    )
    messages = [
        {
            "role": "system",
            "content": "你正在扮演客户，只输出客户说的那一句话，不要解释，不要角色名前缀。",
        },
        {"role": "user", "content": p},
    ]
    return llm.chat(messages, temperature=0.8, max_tokens=200)


# ---------- 规则 fallback ----------


def _reply_with_rules(
    knowledge: dict,
    history: list,
    turn_count: int,
    max_turns: int,
) -> str:
    """无 LLM 时：按 required_questions 逐条问，问完结束。"""
    required = knowledge.get("required_questions") or [
        "尺寸",
        "数量",
        "材质",
        "用途",
    ]
    category = knowledge.get("category", "")

    # 开场：客服还没说话
    if turn_count == 0:
        if category:
            return f"你好，我想咨询一下{category}相关的产品。"
        return "你好，我想咨询一下你们的产品。"

    # 客服已答 turn_count 次，追问下一个必要信息
    if turn_count <= len(required):
        idx = turn_count - 1
        if 0 <= idx < len(required):
            item = required[idx]
            return f"好的，那请问{item}有什么要求？"
        # 必要信息问完
        return "好的，信息我都了解了，谢谢，我先考虑下有需要再联系。" + END_MARKER

    # 超过最大轮数
    if turn_count >= max_turns:
        return END_MARKER

    return "好的，谢谢。" + END_MARKER

"""AI 模拟客户（simulator）。

基于结构化知识 JSON 模拟真实客户，与客服逐句对话。
关键：不直接喂原始聊天记录，只依赖 knowledge 提取后的结构化知识。

LLM 模式：用 customer.txt prompt，多轮自然对话，会追问。
规则模式：按 required_questions 逐条问，问完结束（保证无 key 也能跑）。

客户性格（v0.4）：每次会话随机分配一种性格，影响表达方式。
"""
import hashlib
import json
import random

from . import llm, prompt

# 对话结束标记（simulator 返回此串表示客户主动结束）
END_MARKER = "[END]"

# 客户性格列表：影响客户表达方式，让对话更真实多样
CUSTOMER_PERSONALITIES = [
    "你性格急躁，不喜欢等，说话简短直接，容易不耐烦。如果客服啰嗦或答不到点子上，你会催促。",
    "你性格犹豫，拿不定主意，经常说'再想想''不太确定'，需要客服给建议和信心才敢下单。",
    "你很挑剔，对价格、质量、交期都很敏感，会反复比较和质疑，喜欢挑毛病。",
    "你对产品完全不懂，问的问题比较基础，容易被专业术语搞晕，需要客服用大白话解释。",
    "你很懂行，会问专业问题，会对比竞品，会砍价，不容易被忽悠。",
    "你性格随和，比较好说话，但也容易被带偏，需要客服引导才能说清需求。",
]

# 长对话自动摘要阈值：超过该消息数后，早期内容用 AI 摘要替代，只保留最近 N 条
SUMMARY_THRESHOLD = 20
RECENT_KEEP = 8


def get_personality(history: list) -> str:
    """根据对话历史确定性选择客户性格。

    用客户的第一句话作为种子，保证同一会话性格固定、不同会话性格多样。
    """
    seed_str = ""
    for m in history:
        if m.role == "customer":
            seed_str = m.content or ""
            break
    if not seed_str:
        seed_str = str(len(history))
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return rng.choice(CUSTOMER_PERSONALITIES)


def build_history_text(messages: list) -> str:
    """把对话历史格式化为文本。messages 为 ChatMessage 列表。"""
    if not messages:
        return "（对话尚未开始）"
    lines = []
    for m in messages:
        role = "客服" if m.role == "agent" else "客户"
        lines.append(f"{role}：{m.content}")
    return "\n".join(lines)


def build_history_for_llm(messages: list, summary: str = "") -> str:
    """生成传给 LLM 的历史文本。

    短对话直接全量；长对话（>SUMMARY_THRESHOLD）用 AI 摘要替代早期内容、
    只保留最近 RECENT_KEEP 条，既保留上下文又压住 token 用量。
    """
    if not messages:
        return "（对话尚未开始）"
    if summary and len(messages) > SUMMARY_THRESHOLD:
        recent = messages[-RECENT_KEEP:]
        recent_text = build_history_text(recent)
        return f"[对话历史摘要]\n{summary}\n\n[最近 {len(recent)} 条对话]\n{recent_text}"
    return build_history_text(messages)


def summarize_older(messages: list, prev_summary: str, category_name: str) -> str:
    """把早期对话（除最近 RECENT_KEEP 条外）浓缩为要点摘要。

    未配置 LLM 时直接返回原摘要（不摘要）。失败时也回退到原摘要，保证不崩。
    """
    if not llm.is_llm_enabled():
        return prev_summary
    older = messages[:-RECENT_KEEP] if len(messages) > RECENT_KEEP else messages
    older_text = build_history_text(older)
    prompt_text = (
        "你是对话记录整理助手。请把以下客服与客户的对话浓缩成简洁要点，"
        "包含：客户核心需求、关注点、异议、已确认信息、待跟进事项。不超过 200 字。\n"
        f"品类：{category_name}\n"
        f"已有摘要：{prev_summary or '无'}\n\n"
        f"待整理对话：\n{older_text}"
    )
    try:
        result = llm.chat(
            [{"role": "user", "content": prompt_text}],
            temperature=0.2,
            max_tokens=300,
        )
        return (result or prev_summary).strip()
    except Exception as e:
        logger.warning("对话摘要生成失败，沿用旧摘要: %s", e)
        return prev_summary


def generate_customer_reply(
    knowledge: dict,
    history: list,
    category_name: str,
    turn_count: int,
    max_turns: int,
    conversation_summary: str = "",
) -> str:
    """生成 AI 客户的下一句话。

    turn_count: 已完成的对话轮数（客服已回答的次数）
    conversation_summary: 长对话的 AI 历史摘要（用于压缩传给 LLM 的上下文）
    返回 END_MARKER 表示客户主动结束对话。
    """
    if llm.is_llm_enabled():
        reply = _reply_with_llm(
            knowledge, history, category_name, turn_count, max_turns,
            conversation_summary=conversation_summary,
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
    conversation_summary: str = "",
) -> str | None:
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    history_text = build_history_for_llm(history, conversation_summary)
    personality = get_personality(history)
    p = prompt.load_prompt(
        "customer",
        knowledge_json=knowledge_json,
        category_name=category_name,
        history=history_text,
        turn_count=turn_count,
        max_turns=max_turns,
        customer_personality=personality,
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

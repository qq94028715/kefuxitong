"""三层路由器（Router）。

流程：
1. intent.classify()      → 判断客服回复的意图标签
2. quick_reply.get()      → 命中则毫秒级返回（无需 LLM）
3. cache.get()            → 命中则毫秒级返回（复用历史 LLM 结果）
4. llm.stream_chat()      → 前两层都 miss 才调 DeepSeek，结果进 Cache

统一输出：生成器逐个字符 yield，前端逐字接收。
Quick/Cache 命中时本地模拟 stream（逐字产出），LLM 时用真实 SSE。
"""

import json
import logging
import time
from typing import Generator

from ..config import settings
from . import llm, cache
from .intent import classify, INTENT_OTHER, INTENT_START, get_intent_label
from .prompt import load_prompt
from .quick_reply import get_reply
from .simulator import build_history_for_llm, get_personality, _build_customer_profiles_section

logger = logging.getLogger(__name__)


def generate_reply_stream(
    knowledge: dict,
    history: list,
    category_name: str,
    turn_count: int,
    max_turns: int,
    knowledge_id: int,
    conversation_summary: str = "",
) -> Generator[str, None, None]:
    """流式生成客户回复（生成器）。

    每次 yield 一个字符，前端逐字显示。
    结束时 yield "[DONE]"。
    """
    # 提取最后一条客服回复作为意图分类输入
    agent_content = ""
    for m in reversed(history):
        if m.role == "agent":
            agent_content = m.content
            break

    intent = classify(agent_content, history, knowledge, turn_count)
    logger.info(
        "Router: turn=%d intent=%s(%s)", turn_count, intent, get_intent_label(intent)
    )

    # ===== 第一层：Quick Reply =====
    if intent != INTENT_OTHER and intent != INTENT_START:
        reply = get_reply(intent, knowledge, agent_content)
        if reply:
            logger.info("Router: Quick Reply 命中 (intent=%s)", intent)
            yield from _simulated_stream(reply)
            yield "[DONE]"
            return

    # ===== 第二层：Cache =====
    cached = cache.get(intent, agent_content, knowledge_id)
    if cached:
        logger.info("Router: Cache 命中 (intent=%s)", intent)
        yield from _simulated_stream(cached)
        yield "[DONE]"
        return

    # ===== 第三层：DeepSeek =====
    logger.info("Router: Quick/Cache miss → DeepSeek (intent=%s)", intent)

    # 未配置 LLM 时：直接走兜底，避免 stream_chat yield None 导致客户沉默
    if not llm.is_llm_enabled():
        fallback = get_reply(intent, knowledge, agent_content)
        if not fallback:
            # quick_reply 也没命中 → 用规则模式生成（按 required_questions 追问）
            from .simulator import _reply_with_rules
            fallback = _reply_with_rules(knowledge, history, turn_count, max_turns)
        if not fallback:
            fallback = "好的，我再了解下。"
        logger.info("Router: LLM 未启用，走规则兜底 (intent=%s)", intent)
        yield from _simulated_stream(fallback)
        yield "[DONE]"
        return

    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    history_text = build_history_for_llm(history, conversation_summary)
    personality = get_personality(history)
    profiles_section = _build_customer_profiles_section(knowledge)
    p = load_prompt(
        "customer",
        knowledge_json=knowledge_json,
        category_name=category_name,
        history=history_text,
        turn_count=turn_count,
        max_turns=max_turns,
        customer_personality=personality,
        customer_profiles_section=profiles_section,
    )
    messages = [
        {
            "role": "system",
            "content": "你正在扮演客户，只输出客户说的那一句话，不要解释，不要角色名前缀。",
        },
        {"role": "user", "content": p},
    ]

    full_reply = ""
    try:
        for chunk in llm.stream_chat(messages, temperature=0.8, max_tokens=200):
            if chunk:  # 跳过 None（未配置或失败时）
                full_reply += chunk
                yield chunk
    except Exception as e:
        logger.error("Router: DeepSeek 流式调用失败: %s", e)
        # fallback: 用 quick_reply 兜底
        fallback = get_reply(intent, knowledge, agent_content)
        if fallback:
            yield from _simulated_stream(fallback)
        else:
            yield "好的，我再了解下。"
    else:
        # LLM 成功生成 → 进 Cache
        if full_reply.strip():
            cache.set(intent, agent_content, knowledge_id, full_reply.strip())
        elif not full_reply.strip():
            # LLM 返回空内容（如 yield None 后直接结束）→ 兜底
            fallback = get_reply(intent, knowledge, agent_content)
            if not fallback:
                from .simulator import _reply_with_rules
                fallback = _reply_with_rules(knowledge, history, turn_count, max_turns)
            if not fallback:
                fallback = "好的，我再了解下。"
            yield from _simulated_stream(fallback)

    yield "[DONE]"


def _simulated_stream(text: str) -> Generator[str, None, None]:
    """模拟流式输出（逐字产出），给 Quick/Cache 回复加打字动画。"""
    for char in text:
        yield char
        time.sleep(settings.stream_delay)

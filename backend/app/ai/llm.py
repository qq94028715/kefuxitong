"""OpenAI 兼容 LLM 客户端。

支持任何兼容 OpenAI Chat Completions API 的服务：
- DeepSeek:   base_url=https://api.deepseek.com/v1
- 通义千问:    base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
- OpenAI:     base_url=https://api.openai.com/v1
- Kimi:       base_url=https://api.moonshot.cn/v1

未配置 LLM_API_KEY 时，所有调用返回 None，上层走规则 fallback。
"""
import json
import logging
from typing import Generator, Optional

from openai import OpenAI

from ..config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> Optional[OpenAI]:
    """返回 LLM 客户端单例；未配置 API_KEY 时返回 None。"""
    global _client
    if not settings.llm_api_key:
        return None
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
        )
    return _client


def is_llm_enabled() -> bool:
    """是否启用了真实 LLM。"""
    return bool(settings.llm_api_key)


def chat(
    messages: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """调用 LLM 对话接口，返回助手回复文本。

    messages: [{"role":"system","content":"..."},{"role":"user","content":"..."}]
    未配置 LLM 或调用异常时返回 None（上层负责 fallback）。
    """
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=(
                temperature if temperature is not None else settings.llm_temperature
            ),
            max_tokens=(
                max_tokens if max_tokens is not None else settings.llm_max_tokens
            ),
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return None


def stream_chat(
    messages: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Generator[str, None, None]:
    """流式调用 LLM 对话接口，逐 token 产出。

    未配置 LLM 时 yield None 一次后退回。
    """
    client = get_client()
    if client is None:
        yield None
        return
    try:
        stream = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=(
                temperature if temperature is not None else settings.llm_temperature
            ),
            max_tokens=(
                max_tokens if max_tokens is not None else settings.llm_max_tokens
            ),
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error("LLM 流式调用失败: %s", e)
        # yield None 让上层知道失败了
        yield None


def chat_json(
    messages: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[dict]:
    """调用 LLM 并解析为 JSON dict。失败返回 None。

    容错处理：去掉 markdown 代码块、提取首个 { ... } 区间。
    """
    text = chat(messages, temperature=temperature, max_tokens=max_tokens)
    if not text:
        return None
    return _parse_json(text)


def _parse_json(text: str) -> Optional[dict]:
    """容错解析 LLM 输出的 JSON。"""
    text = text.strip()
    # 去掉 markdown 代码块 ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 兜底：提取第一个 { 到最后一个 } 之间内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        logger.error("JSON 解析失败，原文前200字: %s", text[:200])
        return None

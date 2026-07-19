"""回复缓存（Cache）。

存储 DeepSeek 生成过的客户回复，后续相似上下文命中直接复用。
Key = (intent + hash(agent_content) + knowledge_id)
命中条件：同一意图 + 同一 knowledge + 客服回答高度相似。

MVP：内存 dict + TTL，单进程适用。
后续可迁 SQLite / Redis。
"""

import hashlib
import time
from typing import Optional

# 缓存项：{key: (reply_text, created_at_timestamp)}
_cache: dict[str, tuple[str, float]] = {}

# 缓存过期时间（秒），默认 7 天
DEFAULT_TTL = 7 * 24 * 3600

# 缓存命中率统计
_hit_count = 0
_miss_count = 0


def make_key(intent: str, agent_content: str, knowledge_id: int) -> str:
    """生成缓存 key。"""
    # 对客服回复做轻量标准化（去标点、去多余空格），保证相似回答能命中
    normalized = "".join(c for c in agent_content if c.isalnum() or c.isspace())
    normalized = " ".join(normalized.split())
    # 取 hash 前 16 位作为特征
    content_hash = hashlib.md5(normalized.encode()).hexdigest()[:16]
    return f"{intent}:{content_hash}:{knowledge_id}"


def get(intent: str, agent_content: str, knowledge_id: int) -> Optional[str]:
    """查找缓存。命中返回回复文本，未命中返回 None。"""
    global _hit_count, _miss_count
    key = make_key(intent, agent_content, knowledge_id)
    entry = _cache.get(key)
    if entry is None:
        _miss_count += 1
        return None
    reply, created_at = entry
    if time.time() - created_at > DEFAULT_TTL:
        del _cache[key]
        _miss_count += 1
        return None
    _hit_count += 1
    return reply


def set(intent: str, agent_content: str, knowledge_id: int, reply: str):
    """存入缓存。"""
    key = make_key(intent, agent_content, knowledge_id)
    _cache[key] = (reply, time.time())


def invalidate(knowledge_id: int = None):
    """失效缓存。

    knowledge_id: 只失效该 knowledge 相关缓存；不传则清空全部。
    """
    global _cache
    if knowledge_id is None:
        _cache.clear()
    else:
        suffix = f":{knowledge_id}"
        keys_to_del = [k for k in _cache if k.endswith(suffix)]
        for k in keys_to_del:
            del _cache[k]


def stats() -> dict:
    """返回缓存统计。"""
    return {
        "size": len(_cache),
        "hits": _hit_count,
        "misses": _miss_count,
        "hit_rate": f"{_hit_count / max(_hit_count + _miss_count, 1) * 100:.1f}%",
    }

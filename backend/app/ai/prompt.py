"""Prompt 模板加载器。

所有 prompt 外置在 ai/prompts/*.txt，方便后台修改无需改代码。

占位符语法：{{var}}（双花括号），如 {{knowledge_json}}。
之所以不用 str.format：prompt 里大量含 JSON 示例（单花括号），
用 str.format 会冲突，需把所有 { 写成 {{，可读性差。
自定义替换只替换 {{var}}，不影响 JSON 示例的 { }。
"""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"

# 缓存，避免每次调用都读文件
_cache: dict[str, str] = {}


def load_prompt(name: str, **kwargs) -> str:
    """加载 prompt 模板并替换变量。

    name: 不含扩展名，如 "customer" → prompts/customer.txt
    kwargs: 模板变量，如 knowledge_json="...", history="..."
    """
    if name not in _cache:
        path = PROMPTS_DIR / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt 模板不存在: {path}")
        _cache[name] = path.read_text(encoding="utf-8")
    text = _cache[name]
    if kwargs:
        for key, value in kwargs.items():
            text = text.replace("{{" + key + "}}", str(value))
    return text


def reload() -> None:
    """清空缓存，下次加载重新读文件（后台改完 prompt 后调用）。"""
    _cache.clear()

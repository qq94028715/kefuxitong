"""kefuxitong AI 核心模块。

五个核心子模块：
- llm:        OpenAI 兼容 LLM 客户端
- prompt:     Prompt 模板加载器
- trainer:    材料处理（加载/拆分/去重）
- knowledge:  结构化知识提取（材料 → JSON）
- simulator:  AI 模拟客户（多轮对话）
- evaluator:  AI 评分（对话 → 结构化评分）

设计原则：聊天记录不直接喂给模拟客户，而是先由 knowledge 提取为
结构化 JSON，simulator 与 evaluator 都依赖这份知识。
"""

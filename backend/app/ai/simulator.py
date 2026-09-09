"""AI 模拟客户（simulator）。

基于结构化知识 JSON 模拟真实客户，与客服逐句对话。
关键：不直接喂原始聊天记录，只依赖 knowledge 提取后的结构化知识。

LLM 模式：用 customer.txt prompt，多轮自然对话，会追问。
规则模式：按 required_questions 逐条问，问完结束（保证无 key 也能跑）。

客户性格（v0.4）：每次会话随机分配一种性格，影响表达方式。
"""
import hashlib
import json
import logging
import random
import re

from . import llm, prompt

logger = logging.getLogger(__name__)

# 对话结束标记（simulator 返回此串表示客户主动结束）
END_MARKER = "[END]"

# 多条连发分隔符：真人微信习惯一口气分几条发，AI 用此分隔，后端拆成多条气泡
BUBBLE_SEP = "|||"


def split_customer_bubbles(text: str) -> list[str]:
    """把客户回复按 BUBBLE_SEP 拆成多条气泡内容（去空、去首尾空白）。

    未使用分隔符时返回单元素列表，行为与旧版一致。
    """
    if not text:
        return []
    parts = [p.strip() for p in text.split(BUBBLE_SEP)]
    return [p for p in parts if p]

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
    question_script: str = "",
) -> str:
    """生成 AI 客户的下一句话。

    turn_count: 已完成的对话轮数（客服已回答的次数）
    conversation_summary: 长对话的 AI 历史摘要（用于压缩传给 LLM 的上下文）
    question_script: 本题客户剧本（聊天记录原文），非空时客户按剧本蓝本衍生扮演
    返回 END_MARKER 表示客户主动结束对话。
    """
    if llm.is_llm_enabled():
        reply = _reply_with_llm(
            knowledge, history, category_name, turn_count, max_turns,
            conversation_summary=conversation_summary,
            question_script=question_script,
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
    question_script: str = "",
) -> str | None:
    knowledge_json = json.dumps(knowledge, ensure_ascii=False, indent=2)
    history_text = build_history_for_llm(history, conversation_summary)
    personality = get_personality(history)
    profiles_section = _build_customer_profiles_section(knowledge)
    # 剧本清洗一次，同时供「剧本纪律」与「语气范本」使用
    cleaned = _clean_script_text(question_script) if question_script else ""
    script_section = _build_question_script_section(question_script, cleaned)
    style_section = _build_speaking_style_section(cleaned)
    p = prompt.load_prompt(
        "customer",
        knowledge_json=knowledge_json,
        category_name=category_name,
        history=history_text,
        turn_count=turn_count,
        max_turns=max_turns,
        customer_personality=personality,
        customer_profiles_section=profiles_section,
        question_script_section=script_section,
        speaking_style_section=style_section,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你正在扮演真实客户在微信上和客服聊天。"
                "只输出客户说的那句话，要短、要口语，不要解释，不要角色名前缀，"
                "不要用您好/请问这类客服腔。"
            ),
        },
        {"role": "user", "content": p},
    ]
    return llm.chat(messages, temperature=0.85, max_tokens=180)


# ---------- 剧本清洗与话题提取 ----------

# 剧本行角色前缀，兼容三种格式：
#   [客户] xxx        （方括号格式，13 道）
#   客户：xxx          （无昵称 md 格式，8 道）
#   客户 (华胤钢结构)：xxx（带昵称 md 格式）
_ROLE_RE = re.compile(r"^\[?\s*(客户|客服)\s*\]?\s*(?:\([^)]*\))?\s*[:：]?\s*")
# 噪声：卡片消息 / 图片 / 视频占位
_SCRIPT_NOISE = (
    "【卡片消息】", "【图片】", "【视频】", "[图片]", "[视频]", "<img",
    "[表情]", "【表情】", "[文件]", "[语音]",
)
# 时间戳：2026-09-04 16:53:29  或  2026-9-4 16:53  等
_TS_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$")
# 短时间串（仅时分，无日期）如 "16:53:29"
_TS_RE_SHORT = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
# URL / 图片链接 / 电商商品链接
_URL_RE = re.compile(r"https?://\S+|item\.taobao\.com\S*|//\S+\.(jpg|png|jpeg|gif|webp)", re.I)
# 客户短应答，无信息量，提取话题时忽略
_CUSTOMER_STOP = {
    "嗯", "嗯嗯", "嗯好", "好", "好的", "好嘞", "可以", "行", "行的",
    "ok", "OK", "哦", "噢", "哦哦", "谢谢", "谢谢了", "再见", "拜拜",
}


def _clean_script_text(script: str) -> str:
    """清洗剧本脏数据：剔除时间戳/卡片/图片/链接/空行，只保留客服客户的真实文字。

    剧本由 format_script 生成，每行以 [客户] 或 [客服] 开头。清洗后仍保持
    该行格式，供后续提取话题与注入 prompt。脏行直接丢弃（不影响其他行）。
    """
    out = []
    for ln in script.splitlines():
        t = ln.strip()
        if not t:
            continue
        m = _ROLE_RE.match(t)
        if not m:
            continue  # 非标准角色行，丢弃
        body = t[m.end():].strip()
        if not body:
            continue
        # 噪声识别
        if body in _SCRIPT_NOISE or any(n in body for n in ("【卡片消息】", "【图片】", "【视频】")):
            continue
        if _TS_RE.match(body) or _TS_RE_SHORT.match(body):
            continue
        if _URL_RE.search(body):
            continue
        # 纯符号/纯数字且无中文，大概率是图片残留
        if not re.search(r"[\u4e00-\u9fffA-Za-z]", body):
            continue
        out.append(f"[{m.group(1)}] {body}")
    return "\n".join(out)


def _extract_customer_topics(cleaned: str) -> list[str]:
    """从清洗后的剧本提取客户真实说过的话题清单（去重、去废话、截断）。"""
    topics: list[str] = []
    seen: set[str] = set()
    for ln in cleaned.splitlines():
        if not ln.startswith("[客户]"):
            continue
        body = ln[len("[客户]"):].strip()
        if not body or len(body) < 3:
            continue
        if body in _CUSTOMER_STOP:
            continue
        if body in seen:
            continue
        seen.add(body)
        topics.append(body)
    return topics[:12]


def _pick_style_samples(cleaned: str) -> list[str]:
    """从清洗后的剧本中挑出「典型真人短句」作为语气范本。

    只取 4~22 字的客户台词——太短（嗯/好）没有风格信息，太长是客户在讲背景、
    不是典型口语。剔除图片视频占位与链接。
    """
    samples: list[str] = []
    seen: set[str] = set()
    for ln in cleaned.splitlines():
        if not ln.startswith("[客户]"):
            continue
        body = ln[len("[客户]"):].strip()
        if not (4 <= len(body) <= 28):
            continue
        if body in _CUSTOMER_STOP or body in seen:
            continue
        if _URL_RE.search(body):
            continue
        if any(n in body for n in _SCRIPT_NOISE):
            continue
        seen.add(body)
        samples.append(body)
    return samples[:8]


# 真人说话规则：写死的硬约束，与剧本话题无关，任何训练都生效
_SPEAKING_RULES = """【真人说话规则】（优先级高于上面一切任务描述）
1. 短。一句话尽量 15 字以内。能一个词答完，就不要写完整句子。
   客服问「平面的还是凹陷的」→ 只回「凹陷」，不要加「吧」「应该行」「要那种有质感的」。
2. 直接甩信息，不铺垫、不解释动机、不讲背景故事。
   对：尺寸200*140 4块 304材质
   错：我们公司最近有个项目，想做几块标牌，尺寸大概是……
3. 禁用客服腔：您好、请问、我想咨询一下、能了解一下吗、麻烦您、感谢、方便的话、亲。
4. 不反问。不要把问题抛回给客服。要问就另起一条消息。
5. 可以省略主语，用空格代替标点，句尾不打句号。
6. 口语词自然使用：吧、哈、就行、看下、对不对、没问题吧、大概、差不多。
7. 一条消息里可以连说两三件事（真人就是这么发的）：
   看下按多少钱一张算 是不是还是这个开发票
8. 要连发多条时（真人经常一口气分几条发），用 ||| 分隔，最多 3 条。
   例：在吗|||我想做几块不锈钢标牌|||尺寸200*140
   只在自然该连发时才分，不要每轮都分。

【真人会做的事】（在剧本话题范围内自然做，不要生硬堆砌，不要每轮都做）
- 客服要参数就直接给，不问为什么
- 聊到一半追加需求：哦对了 还要四角开孔
- 有工期压力就说出具体时间：今天能出样吗 急用／5点下班前要
- 拿不准时求一句安心：这个排版没问题的吧
- 描述不清时发图：[图片] 要这种效果
- 偶尔提一句别家比价：隔壁给我报XX
- 需要请示：我问下项目部
"""


def _build_speaking_style_section(cleaned: str) -> str:
    """构造「真人说话风格」注入段：硬规则 + 从真实剧本提取的语气范本。

    cleaned 为空（无剧本）时只注入硬规则，不影响自由训练流程。
    """
    samples = _pick_style_samples(cleaned)
    if not samples:
        return _SPEAKING_RULES
    sample_block = (
        "【语气范本】（下面是从真实聊天记录里摘的客户原话，"
        "照这个味道和长度说话，但不要照抄内容）\n"
        + "\n".join(f"- {s}" for s in samples)
    )
    return f"{_SPEAKING_RULES}\n{sample_block}"


def _build_question_script_section(question_script: str, cleaned: str = "") -> str:
    """构造客户剧本注入段落（清洗 + 客户关注点清单 + 强约束纪律）。

    剧本非空时：清洗脏数据 → 提取客户真实话题 → 指示 AI 客户严格以剧本
    为准扮演，禁止问剧本之外的问题、禁止重复已确认信息。
    为空时返回空串，不影响无剧本的自由训练旧流程。

    cleaned 由调用方传入已清洗文本（与语气范本共用同一次清洗），为空则内部清洗。
    """
    if not question_script or not question_script.strip():
        return ""
    if not cleaned:
        cleaned = _clean_script_text(question_script)
    if not cleaned:
        return ""
    topics = _extract_customer_topics(cleaned)
    topics_section = ""
    if topics:
        topics_section = (
            "【剧本中客户真实提出/关心过的话题（你只能在这些话题内与客服沟通）】\n"
            + "\n".join(f"- {t}" for t in topics)
            + "\n\n"
        )
    return (
        "【客户剧本参考（真实聊天记录，你就是其中的那位客户）】\n"
        "下面是一段真实客服与客户的聊天记录，你就是其中的那位客户。\n\n"
        "以下【剧本纪律】优先于上文『根据知识库产生需求』的通用说明，务必遵守：\n"
        "1. 你的身份、需求、关注点和说话风格，完全以剧本中的客户为准。\n"
        "   剧本客户没提过的产品、材质、规格、服务，你一律不主动涉及。\n"
        "2. 你只能围绕剧本中客户真实提出过的话题与客服沟通；\n"
        "   严禁凭空提出剧本之外的新需求或新问题。\n"
        "3. 客服已经回答清楚、你也认可的信息（如寿命、材质、交期、价格、数量），\n"
        "   绝对不要再重复问；顺着客服的上一句回答自然承接下一句。\n"
        "4. 不要因为知识库里写了某种参数，就在剧本客户没问到的情况下主动抛出。\n"
        "5. 如果剧本中的客户最终成交，你倾向促成；如果流失，在合适时机表达\n"
        "   犹豫、质疑或离开意向，考察客服能否挽回。\n\n"
        f"{topics_section}"
        "【剧本原文（已清洗，仅保留客服/客户真实文字，脏数据已剔除）】\n"
        f"{cleaned}"
    )


def _build_customer_profiles_section(knowledge: dict) -> str:
    """从 knowledge 的 customer_profiles 字段构造画像注入文本。

    knowledge 含 customer_profiles 数组时渲染为一段引导文本；
    否则返回空串，不影响现有使用默认性格的品类。
    """
    profiles = knowledge.get("customer_profiles") or []
    if not profiles:
        return ""
    parts = ["你可以从以下客户类型中选择一种进行模拟："]
    for p in profiles:
        if isinstance(p, dict):
            name = p.get("name", "")
            role = p.get("role", "")
            traits = p.get("traits", "")
            first_style = p.get("first_message_style", "")
            test_focus = p.get("test_focus", "")
            line = f"- {name}"
            if role:
                line += f"（{role}）"
            line += f"：{traits}"
            if first_style:
                line += f"。典型第一句话风格：{first_style}"
            if test_focus:
                line += f"。重点测试：{test_focus}"
            parts.append(line)
        elif isinstance(p, str):
            parts.append(f"- {p}")
    parts.append("根据你选择的类型，调整你的说话方式和关注点，保持角色一致性。")
    return "\n".join(parts)


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

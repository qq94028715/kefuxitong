"""快速回复话术库（Quick Reply）。

按意图标签存储预定义的客户回复话术。
每个意图有多条话术，随机选取一条增加多样性。
变量（如 category_name）从 knowledge 中动态填充。

话术来源：
- MVP：人工预配常见话术
- 后续：从管理员上传的真实语料中自动提取
"""

import random

from .intent import (
    INTENT_START,
    INTENT_ASK_SPEC,
    INTENT_ASK_PRICE,
    INTENT_ASK_MOQ,
    INTENT_ASK_DELIVERY,
    INTENT_ASK_PROCESS,
    INTENT_ASK_USAGE,
    INTENT_CONFIRM,
    INTENT_COMPLAIN,
    INTENT_NEGOTIATE,
    INTENT_END,
)


# 话术模板库：key = 意图标签，value = [话术模板列表]
# 模板中用 {{var}} 占位，运行时从 knowledge 或上下文填充
TEMPLATES = {
    INTENT_START: [
        "你好，我想了解一下{{category}}相关的产品。",
        "你好，请问你们做{{category}}吗？",
        "你好，我想咨询一下{{category}}，能给我介绍一下吗？",
    ],
    INTENT_ASK_SPEC: [
        "你们{{category}}的尺寸规格有哪些？厚度是多少？",
        "这种{{category}}的尺寸、厚度和材质能说下吗？",
        "规格上有什么要求？比如尺寸多大、多厚？",
        "我需要了解一下具体的尺寸和厚度参数。",
    ],
    INTENT_ASK_PRICE: [
        "这个{{category}}怎么算价格？是论张还是论面积？",
        "不同规格的价格差别大吗？能报个价吗？",
        "{{category}}的价格怎么定的？有报价表吗？",
    ],
    INTENT_ASK_MOQ: [
        "{{category}}起订量是多少？最少要做多少？",
        "数量少了能做吗？MOQ大概多少？",
        "起订量有没有要求？少量做会不会加价？",
    ],
    INTENT_ASK_DELIVERY: [
        "交期大概要多久？排产周期长吗？",
        "从下单到出货一般要几天？急的话能加急吗？",
        "{{category}}的货期正常多久？有加急服务吗？",
    ],
    INTENT_ASK_PROCESS: [
        "{{category}}能做什么工艺处理？比如覆膜、UV？",
        "上面能印刷吗？可以用丝印还是数码印？",
        "工艺方面有什么选择？覆膜、打孔、烫金能做吗？",
    ],
    INTENT_ASK_USAGE: [
        "这种{{category}}一般用在什么场景？户外能用吗？",
        "如果贴在室外，防水耐晒吗？能用多久？",
        "{{category}}主要用于什么场合？对耐温性有要求吗？",
    ],
    INTENT_CONFIRM: [
        "好的，那我确认一下：{{spec_hint}}，对吗？",
        "明白了，那这个规格没问题吧？",
        "了解了，那还有其他需要注意的吗？",
    ],
    INTENT_COMPLAIN: [
        "嗯…这个价格比我想的贵了不少。",
        "交期太久了，我们挺急的。",
        "厚度感觉不够，能加厚吗？",
        "材质方面我有点担心，品质能保证吗？",
    ],
    INTENT_NEGOTIATE: [
        "我们量还可以再大点，价格能再低吗？",
        "长期合作的话，有没有优惠？",
        "对比过别家，你们价格偏高，能谈吗？",
        "如果能便宜点，我这边可以定下来。",
    ],
    INTENT_END: [
        "好的，信息我都了解了，谢谢。我先考虑下，有需要再联系。",
        "清楚了，我再对比一下，有问题再找你。",
        "谢谢你，我先回去确认下需求再联系。",
    ],
}


def get_reply(intent: str, knowledge: dict, agent_content: str = "") -> str | None:
    """根据意图获取快速回复。

    返回话术文本，如果该意图没有预设话术则返回 None → 走 Cache 或 DeepSeek。
    """
    templates = TEMPLATES.get(intent)
    if not templates:
        return None

    template = random.choice(templates)
    return _fill_template(template, knowledge, agent_content)


def _fill_template(template: str, knowledge: dict, agent_content: str) -> str:
    """填充模板变量。"""
    category = knowledge.get("category", "该产品")
    result = template.replace("{{category}}", category)

    # spec_hint：如果客服提到了具体规格，引用之
    if "{{spec_hint}}" in result:
        spec_hint = _extract_spec_hint(agent_content)
        result = result.replace("{{spec_hint}}", spec_hint)

    return result


def _extract_spec_hint(content: str) -> str:
    """从客服回复中提取规格摘要（用于确认场景）。"""
    import re
    specs = []
    patterns = [
        (r"(\d+\.?\d*\s*(mm|毫米|cm|厘米))", 1),
        (r"(\d+张|\d+个|\d+片|\d+套|\d+件)", 1),
    ]
    for pat, _ in patterns:
        matches = re.findall(pat, content)
        for m in matches[:2]:  # 最多取 2 个
            specs.append(m[0] if isinstance(m, tuple) else m)
    return "、".join(specs[:2]) if specs else "这些规格"

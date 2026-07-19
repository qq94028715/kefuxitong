"""意图分类器（intent）。

根据客服当前回复 + 历史对话 + knowledge，判断客户意图标签。
规则模式（关键词匹配），后续可升级为 LLM 分类。

返回意图标签，router 据此决定走 Quick Reply / Cache / DeepSeek。
"""

import re

# 意图标签
INTENT_GREETING = "greeting"
INTENT_ASK_SPEC = "ask_spec"         # 询问规格（尺寸/厚度/材质）
INTENT_ASK_PRICE = "ask_price"       # 价格
INTENT_ASK_MOQ = "ask_moq"           # 起订量
INTENT_ASK_DELIVERY = "ask_delivery" # 交期
INTENT_ASK_PROCESS = "ask_process"   # 工艺（覆膜/印刷/打孔）
INTENT_ASK_USAGE = "ask_usage"       # 用途/场景
INTENT_CONFIRM = "confirm_detail"    # 确认细节
INTENT_COMPLAIN = "complain"         # 异议/抱怨
INTENT_NEGOTIATE = "negotiate"       # 议价/谈条件
INTENT_END = "end"                   # 结束倾向
INTENT_OTHER = "other"              # 兜底 → DeepSeek

# 首次对话没有客服回复，标记为开场
INTENT_START = "start"

# 关键词规则：按优先级匹配
RULES = [
    (INTENT_END, [
        r"(谢谢|感谢|再见|拜拜|先这样|再联系|考虑一下|不需要|不用了)",
    ]),
    (INTENT_COMPLAIN, [
        r"(太贵|太慢|太薄|太厚|质量不好|不行|不合适|不对|不满意|差)",
    ]),
    (INTENT_NEGOTIATE, [
        r"(能不能便宜|最低多少|折扣|优惠|量大|长期合作|便宜)",
    ]),
    (INTENT_ASK_PRICE, [
        r"(多少钱|报价|价格|怎么算|单价|费用|什么价)",
    ]),
    (INTENT_ASK_MOQ, [
        r"(起订|最低.*量|最少.*多少|MOQ|多少.*起|最少.*订)",
    ]),
    (INTENT_ASK_DELIVERY, [
        r"(交期|多久|货期|周期|什么时候|几天|排期|出货)",
    ]),
    (INTENT_ASK_PROCESS, [
        r"(工艺|印刷|覆膜|打孔|丝印|UV|烫金|处理|加工|怎么做|怎么印)",
    ]),
    (INTENT_ASK_USAGE, [
        r"(做什么用|用途|用在|场景|环境|怎么用|贴在哪)",
    ]),
    (INTENT_ASK_SPEC, [
        r"(尺寸|厚度|规格|多大|多厚|什么材质|材质|多少克|颜色|长|宽|高|mm|cm|形)",
        r"(什么材料|防水|耐温|耐高温|耐腐蚀|耐刮)",
    ]),
    (INTENT_CONFIRM, [
        r"(确认|就这个|就这样的|可以|行|好|OK|没问题|对|是的|嗯|哦|明白了|了解)",
    ]),
]


def classify(
    agent_content: str,
    history: list,
    knowledge: dict,
    turn_count: int,
) -> str:
    """根据客服回复判断当前客户意图。

    首次对话 (turn_count==0, history 为空或无客服发言) 返回 "start"。
    """
    if not agent_content or not agent_content.strip():
        return INTENT_START

    text = agent_content.strip()

    for intent, patterns in RULES:
        for pat in patterns:
            if re.search(pat, text):
                return intent

    return INTENT_OTHER


def get_intent_label(intent: str) -> str:
    """返回可读意图标签。"""
    labels = {
        "start": "开场",
        "greeting": "寒暄",
        "ask_spec": "问规格",
        "ask_price": "问价格",
        "ask_moq": "问起订量",
        "ask_delivery": "问交期",
        "ask_process": "问工艺",
        "ask_usage": "问用途",
        "confirm_detail": "确认细节",
        "complain": "异议/抱怨",
        "negotiate": "议价",
        "end": "结束倾向",
        "other": "其他(走DeepSeek)",
    }
    return labels.get(intent, intent)

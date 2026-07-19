"""AI 训练器。

MVP 实现：基于语料库抽取问题，用文本相似度评估客服回答。
  - AI 角色：从语料库抽取「客户问题」逐一向客服提问，模拟客户。
  - 评分：对比客服回答与「标准答案」的相似度，给出分数与反馈。

后续升级路径：接入真实 LLM（OpenAI / DeepSeek / 通义千问等），
让 AI 客户根据语料上下文生成更自然的多轮追问。
接口见本文件末尾的 LLMAdapter 占位。
"""
import random
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from .models import Corpus


def pick_questions(db: Session, training_type_id: int, count: int) -> list[Corpus]:
    """从指定训练类型的语料库中随机抽取若干条作为本次训练题。"""
    pool = (
        db.query(Corpus)
        .filter(Corpus.training_type_id == training_type_id)
        .all()
    )
    if not pool:
        return []
    count = min(count, len(pool))
    return random.sample(pool, count)


def similarity(a: str, b: str) -> float:
    """文本相似度（0~1），基于序列匹配。"""
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def evaluate_answer(agent_answer: str, standard_answer: str) -> tuple[float, str]:
    """评估客服回答，返回 (得分 0~100, 反馈文本)。"""
    sim = similarity(agent_answer, standard_answer)
    score = round(sim * 100, 1)
    if sim >= 0.8:
        verdict = "回答优秀，与标准答案高度吻合。"
    elif sim >= 0.5:
        verdict = "回答基本到位，可更贴近标准表述。"
    elif sim >= 0.3:
        verdict = "回答有所偏差，建议参考标准答案。"
    else:
        verdict = "回答偏离较大，请重点学习该场景。"
    feedback = f"{verdict}\n参考答案：{standard_answer}"
    return score, feedback


# -------------------------------------------------------------------
# LLM 适配器（预留，后续接入真实 LLM 时实现）
# -------------------------------------------------------------------
class LLMAdapter:
    """LLM 适配器占位。

    后续接入真实 LLM 时，实现 generate_customer_reply 方法，
    根据语料上下文生成更自然的客户回复/追问。
    配置方式：在 .env 中设置 LLM_API_KEY / LLM_PROVIDER，
    在此选择对应实现。
    """

    @staticmethod
    def generate_customer_reply(
        corpus_list: list[Corpus],
        history: list[dict],
    ) -> str:
        raise NotImplementedError(
            "LLM 适配器尚未配置。当前使用基于语料的规则模式。"
            "接入真实 LLM 请参考 docs/DEVELOPMENT.md。"
        )

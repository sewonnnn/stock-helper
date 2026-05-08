"""대화형 후속 질문 노드

이전 답변에 대한 간단한 후속 질문을 대화 맥락만으로 답변합니다.
검색 없이 LLM 1회 호출로 짧게 응답합니다.
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import DEFAULT_MODEL, ERROR_MESSAGES
from stock_agent.utils.state import GraphState
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)

_chat_llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=0)

_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a helpful Korean stock assistant. "
        "The user is asking a follow-up question about a previous answer. "
        "Answer ONLY the specific question asked — do NOT repeat or regenerate the previous full answer. "
        "Keep your response short and focused (2-5 sentences). "
        "Always respond in Korean."
    )),
    ("human", "{question}"),
])


def chat_node(state: GraphState) -> dict:
    """대화 맥락 기반 짧은 후속 답변."""
    question = state["question"]

    try:
        draft = (_CHAT_PROMPT | _chat_llm).invoke({
            "question": question,
        }).content

        return {
            "draft_answer": draft,
            "agent_results": {"source_data": "", "source_urls": [], "agent": "chat"},
        }

    except Exception as e:
        logger.error("chat 노드 실패: %s", e, exc_info=True)
        return {
            "draft_answer": ERROR_MESSAGES["general_failed"],
            "agent_results": {"source_data": "", "source_urls": [], "agent": "chat"},
        }

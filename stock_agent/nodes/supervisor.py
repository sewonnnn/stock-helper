"""슈퍼바이저 노드: LLM 구조화 출력으로 질문을 라우팅합니다."""

import time
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.supervisor import SUPERVISOR_PROMPT
from stock_agent.utils.state import GraphState
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)
_timing_logger = get_logger("timing")


class RouteQuery(BaseModel):
    """질문 라우팅 결과"""
    datasource: str = Field(description='"company", "news", "glossary", "advisor", "general", "chat", or "reject"')


question_router = (
    ChatPromptTemplate.from_template(SUPERVISOR_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(RouteQuery)
)


def supervisor_node(state: GraphState) -> dict:
    """사용자 질문을 분류하여 적절한 에이전트로 라우팅합니다."""
    question = state["question"]
    t0 = time.perf_counter()
    try:
        result: RouteQuery = question_router.invoke({"question": question})
        _timing_logger.info("[supervisor LLM] %.0fms → %s", (time.perf_counter() - t0) * 1000, result.datasource)
        logger.info("라우팅: %s", result.datasource)
        return {"route": result.datasource}
    except Exception as e:
        _timing_logger.info("[supervisor LLM] %.0fms (실패)", (time.perf_counter() - t0) * 1000)
        logger.error("라우팅 실패, general로 폴백: %s", e)
        return {"route": "general"}

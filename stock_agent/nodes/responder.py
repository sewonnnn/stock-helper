"""최종 응답 생성 노드: StockResponse 스키마로 구조화합니다."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import DEFAULT_MODEL, UNKNOWN_RESPONSE
from stock_agent.utils.state import GraphState
from stock_agent.utils.schemas import StockResponse
from stock_agent.prompts.responder import RESPONDER_PROMPT

responder_chain = (
    ChatPromptTemplate.from_template(RESPONDER_PROMPT)
    | ChatOpenAI(model=DEFAULT_MODEL, temperature=0).with_structured_output(StockResponse)
)


def responder_node(state: GraphState) -> dict:
    """검증된 답변을 StockResponse 스키마로 구조화합니다."""
    validated = state.get("validated", False)
    draft_answer = state["draft_answer"]
    agent_results = state["agent_results"]
    route = state["route"]
    source_data = agent_results.get("source_data", "")

    # 검증 실패 + 재시도 소진 시
    if not validated:
        return {
            "final_answer": StockResponse(
                인사이트=UNKNOWN_RESPONSE,
                출처=[],
                확신도="낮음",
            )
        }

    # 구조화 응답 생성
    try:
        response: StockResponse = responder_chain.invoke({
            "validated_answer": draft_answer,
            "source_data": source_data,
            "route": route,
        })
        return {"final_answer": response}
    except Exception:
        # 구조화 실패 시 fallback
        return {
            "final_answer": StockResponse(
                인사이트=draft_answer,
                출처=[],
                확신도="중간",
            )
        }

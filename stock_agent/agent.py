"""메인 LangGraph StateGraph 조립

흐름:
  슈퍼바이저 → (company | news | general) → 검증 → 응답
  슈퍼바이저 → glossary → 직통 응답 (Self-RAG 내부 검증 완료이므로 스킵)
  검증 실패 시 → 슈퍼바이저로 복귀 (최대 1회 재시도)
"""

from langgraph.graph import StateGraph, END

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import MAX_RETRIES
from stock_agent.utils.schemas import StockResponse
from stock_agent.nodes.supervisor import supervisor_node
from stock_agent.nodes.company import company_node
from stock_agent.nodes.news import news_node
from stock_agent.nodes.glossary import glossary_node
from stock_agent.nodes.general import general_node
from stock_agent.nodes.validator import validator_node
from stock_agent.nodes.responder import responder_node


def route_by_supervisor(state: GraphState) -> str:
    """슈퍼바이저 결과에 따라 에이전트 노드를 선택합니다."""
    route = state["route"]
    mapping = {
        "company": "company",
        "news": "news",
        "glossary": "glossary",
        "general": "general",
    }
    return mapping.get(route, "general")


def check_validation(state: GraphState) -> str:
    """검증 결과에 따라 응답 or 재시도를 결정합니다."""
    if state["validated"]:
        return "responder"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return "responder"
    return "retry"


def increment_retry(state: GraphState) -> dict:
    """재시도 카운터를 증가시킵니다."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def glossary_direct_response(state: GraphState) -> dict:
    """glossary는 Self-RAG 내부에서 이미 검증 완료이므로 Responder 스킵.
    직접 StockResponse를 구성합니다."""
    draft = state["draft_answer"]
    source_data = state["agent_results"].get("source_data", "")

    sources = []
    if source_data:
        sources = ["용어집 (Pinecone RAG)"]

    return {
        "final_answer": StockResponse(
            용어설명=draft,
            출처=sources,
            확신도="높음",
        )
    }


def general_direct_response(state: GraphState) -> dict:
    """general은 웹 검색 결과를 이미 한국어로 정리했으므로 Responder 스킵.
    draft_answer를 인사이트 필드에 그대로 전달합니다."""
    import re

    draft = state["draft_answer"]
    source_data = state["agent_results"].get("source_data", "")

    # 본문에서 인라인 출처 링크 제거: [출처: 매일경제](url) → 제거
    clean_draft = re.sub(r'\s*\[출처[^\]]*\]\(https?://[^\)]+\)', '', draft)
    # 혹시 [텍스트](url) 형태도 제거
    clean_draft = re.sub(r'\s*\[([^\]]+)\]\(https?://[^\)]+\)', '', clean_draft)

    # source_data에서 URL 추출 (Tavily 원본 결과에서)
    sources = []
    urls = re.findall(r'https?://[^\s\"\'\]\,]+', source_data)
    sources = list(dict.fromkeys(urls))[:5]  # 중복 제거, 최대 5개

    return {
        "final_answer": StockResponse(
            인사이트=clean_draft,
            출처=sources,
            확신도="중간",
        )
    }


def build_graph() -> StateGraph:
    """메인 그래프를 조립하여 반환합니다."""

    workflow = StateGraph(GraphState)

    # 노드 등록
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("company", company_node)
    workflow.add_node("news", news_node)
    workflow.add_node("glossary", glossary_node)
    workflow.add_node("general", general_node)
    workflow.add_node("general_response", general_direct_response)
    workflow.add_node("glossary_response", glossary_direct_response)
    workflow.add_node("validator", validator_node)
    workflow.add_node("responder", responder_node)
    workflow.add_node("increment_retry", increment_retry)

    # 진입점
    workflow.set_entry_point("supervisor")

    # 슈퍼바이저 → 에이전트 (조건부 라우팅)
    workflow.add_conditional_edges(
        "supervisor",
        route_by_supervisor,
        {
            "company": "company",
            "news": "news",
            "glossary": "glossary",
            "general": "general",
        },
    )

    # company/news → 검증 → 응답
    workflow.add_edge("company", "validator")
    workflow.add_edge("news", "validator")

    # general → 직통 응답 (웹 검색 결과 그대로 전달)
    workflow.add_edge("general", "general_response")
    workflow.add_edge("general_response", END)

    # glossary → 직통 응답 (validator + responder 스킵)
    workflow.add_edge("glossary", "glossary_response")
    workflow.add_edge("glossary_response", END)

    # 검증 → 응답 or 재시도 (조건부)
    workflow.add_conditional_edges(
        "validator",
        check_validation,
        {
            "responder": "responder",
            "retry": "increment_retry",
        },
    )

    # 재시도 → 슈퍼바이저로 복귀
    workflow.add_edge("increment_retry", "supervisor")

    # 응답 → 종료
    workflow.add_edge("responder", END)

    return workflow.compile()


# 그래프 인스턴스
graph = build_graph()

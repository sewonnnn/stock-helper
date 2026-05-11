"""일반 시장 질문 체인 노드 (웹 검색 기반)"""

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import TRUSTED_NEWS_DOMAINS
from stock_agent.prompts.general import GENERAL_QUERY_PROMPT, GENERAL_SYNTHESIS_PROMPT
from stock_agent.tools.tavily_tools import tavily_search_general
from stock_agent.nodes._search_chain import run_search_chain


def general_node(state: GraphState) -> dict:
    """웹 검색 기반 일반 시장 질문 체인: 쿼리 생성 → 검색 → 신뢰 도메인 필터 → 합성."""
    return run_search_chain(
        question=state["question"],
        query_prompt=GENERAL_QUERY_PROMPT,
        synthesis_prompt=GENERAL_SYNTHESIS_PROMPT,
        search_tool=tavily_search_general,
        agent_name="general",
        empty_message="관련 정보를 찾을 수 없습니다.",
        error_key="general_failed",
        trusted_domains=TRUSTED_NEWS_DOMAINS,
    )

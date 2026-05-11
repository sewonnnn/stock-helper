"""뉴스 검색 체인 노드"""

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import TRUSTED_NEWS_DOMAINS
from stock_agent.prompts.news import NEWS_QUERY_PROMPT, NEWS_SYNTHESIS_PROMPT
from stock_agent.tools.tavily_tools import tavily_search_news
from stock_agent.nodes._search_chain import run_search_chain


def news_node(state: GraphState) -> dict:
    """뉴스 검색 체인: 쿼리 생성 → 검색 → 신뢰 도메인 필터 → 합성."""
    return run_search_chain(
        question=state["question"],
        query_prompt=NEWS_QUERY_PROMPT,
        synthesis_prompt=NEWS_SYNTHESIS_PROMPT,
        search_tool=tavily_search_news,
        agent_name="news",
        empty_message="최근 관련 뉴스를 찾을 수 없습니다.",
        error_key="news_failed",
        trusted_domains=TRUSTED_NEWS_DOMAINS,
    )

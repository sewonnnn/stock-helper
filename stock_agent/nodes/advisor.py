"""개인 맞춤 투자 안내 체인 노드"""

from stock_agent.utils.state import GraphState
from stock_agent.prompts.advisor import ADVISOR_SYNTHESIS_PROMPT
from stock_agent.tools.tavily_tools import tavily_search_advisor
from stock_agent.nodes._search_chain import run_search_chain


def advisor_node(state: GraphState) -> dict:
    """맞춤 투자 안내 체인: 질문 그대로 검색 → 합성."""
    return run_search_chain(
        question=state["question"],
        synthesis_prompt=ADVISOR_SYNTHESIS_PROMPT,
        search_tool=tavily_search_advisor,
        agent_name="advisor",
        empty_message="관련 투자 가이드 정보를 찾을 수 없습니다.",
        error_key="advisor_failed",
    )

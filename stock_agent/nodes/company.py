"""기업분석 에이전트 노드"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from stock_agent.utils.constants import DEFAULT_MODEL
from stock_agent.utils.state import GraphState
from stock_agent.prompts.company import COMPANY_AGENT_PROMPT
from stock_agent.tools.yfinance_tools import (
    get_stock_overview,
    get_valuation_metrics,
    get_financial_health,
    get_recent_news,
)
from stock_agent.tools.ticker_mapping import resolve_ticker

# 에이전트 생성
company_tools = [
    resolve_ticker,
    get_stock_overview,
    get_valuation_metrics,
    get_financial_health,
    get_recent_news,
]

company_agent = create_agent(
    model=ChatOpenAI(model=DEFAULT_MODEL, temperature=0),
    tools=company_tools,
    system_prompt=COMPANY_AGENT_PROMPT,
)


def company_node(state: GraphState) -> dict:
    """기업분석 에이전트를 실행합니다."""
    question = state["question"]
    result = company_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    # 마지막 AI 메시지를 답변으로 추출
    ai_messages = [m for m in result["messages"] if m.type == "ai" and m.content]
    draft = ai_messages[-1].content if ai_messages else ""

    # 도구 호출 결과를 source_data로 수집
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    source_data = "\n".join([m.content for m in tool_messages if m.content])

    return {
        "draft_answer": draft,
        "agent_results": {"source_data": source_data, "agent": "company"},
    }

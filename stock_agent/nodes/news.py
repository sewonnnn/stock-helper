"""뉴스서치 ReAct 에이전트 노드"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from stock_agent.utils.constants import DEFAULT_MODEL
from stock_agent.utils.state import GraphState
from stock_agent.prompts.news import NEWS_AGENT_PROMPT
from stock_agent.tools.tavily_tools import tavily_search
from stock_agent.tools.ticker_mapping import resolve_ticker

# ReAct 에이전트 생성
news_tools = [resolve_ticker, tavily_search]

news_agent = create_react_agent(
    model=ChatOpenAI(model=DEFAULT_MODEL, temperature=0),
    tools=news_tools,
    prompt=NEWS_AGENT_PROMPT,
)


def news_node(state: GraphState) -> dict:
    """뉴스서치 에이전트를 실행합니다."""
    question = state["question"]
    result = news_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    ai_messages = [m for m in result["messages"] if m.type == "ai" and m.content]
    draft = ai_messages[-1].content if ai_messages else ""

    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    source_data = "\n".join([m.content for m in tool_messages if m.content])

    return {
        "draft_answer": draft,
        "agent_results": {"source_data": source_data, "agent": "news"},
    }

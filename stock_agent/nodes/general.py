"""일반 시장 질문 ReAct 에이전트 노드 (웹 검색 기반)"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from stock_agent.utils.constants import DEFAULT_MODEL
from stock_agent.utils.state import GraphState
from stock_agent.prompts.general import GENERAL_AGENT_PROMPT
from stock_agent.tools.tavily_tools import tavily_search

# ReAct 에이전트 생성
general_agent = create_react_agent(
    model=ChatOpenAI(model=DEFAULT_MODEL, temperature=0),
    tools=[tavily_search],
    prompt=GENERAL_AGENT_PROMPT,
)


def general_node(state: GraphState) -> dict:
    """웹 검색 기반으로 일반 시장 질문에 답변합니다."""
    question = state["question"]
    result = general_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    ai_messages = [m for m in result["messages"] if m.type == "ai" and m.content]
    draft = ai_messages[-1].content if ai_messages else ""

    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    source_data = "\n".join([m.content for m in tool_messages if m.content])

    return {
        "draft_answer": draft,
        "agent_results": {"source_data": source_data, "agent": "general"},
    }

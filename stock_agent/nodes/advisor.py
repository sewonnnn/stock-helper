"""개인 맞춤 투자 안내 에이전트 노드"""

from langchain.agents import create_agent

from stock_agent.utils.constants import DEFAULT_MODEL
from stock_agent.utils.state import GraphState
from stock_agent.prompts.advisor import ADVISOR_AGENT_PROMPT
from stock_agent.tools.tavily_tools import tavily_search_advisor

# 에이전트 생성
advisor_agent = create_agent(
    model=DEFAULT_MODEL,
    tools=[tavily_search_advisor],
    system_prompt=ADVISOR_AGENT_PROMPT,
)


def advisor_node(state: GraphState) -> dict:
    """사용자 상황에 맞는 맞춤 투자 안내를 제공합니다."""
    question = state["question"]
    result = advisor_agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    ai_messages = [m for m in result["messages"] if m.type == "ai" and m.content]
    draft = ai_messages[-1].content if ai_messages else ""

    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    source_data = "\n".join([m.content for m in tool_messages if m.content])

    return {
        "draft_answer": draft,
        "agent_results": {"source_data": source_data, "agent": "advisor"},
    }

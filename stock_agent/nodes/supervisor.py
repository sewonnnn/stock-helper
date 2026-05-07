"""슈퍼바이저 노드: 질문을 라우팅합니다."""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.supervisor import SUPERVISOR_PROMPT
from stock_agent.utils.state import GraphState


class RouteQuery(BaseModel):
    """질문 라우팅 결과"""
    datasource: str = Field(description='"company", "news", "glossary", or "general"')


question_router = (
    ChatPromptTemplate.from_template(SUPERVISOR_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(RouteQuery)
)


def supervisor_node(state: GraphState) -> dict:
    """사용자 질문을 분류하여 적절한 에이전트로 라우팅합니다."""
    question = state["question"]
    result: RouteQuery = question_router.invoke({"question": question})
    return {"route": result.datasource}

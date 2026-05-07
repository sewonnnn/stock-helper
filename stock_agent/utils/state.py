from typing import TypedDict, Annotated
import operator

from stock_agent.utils.schemas import StockResponse


class GraphState(TypedDict):
    question: str
    chat_history: Annotated[list, operator.add]  # 턴마다 누적 (checkpointer)
    route: str
    agent_results: dict
    draft_answer: str
    validated: bool
    validation_reason: str
    hallucinated_parts: list
    retry_count: int
    final_answer: StockResponse

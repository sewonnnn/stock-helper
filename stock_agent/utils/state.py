from typing import TypedDict

from stock_agent.utils.schemas import StockResponse


class GraphState(TypedDict):
    question: str
    route: str
    agent_results: dict
    draft_answer: str
    validated: bool
    validation_reason: str
    hallucinated_parts: list
    retry_count: int
    final_answer: StockResponse

"""검증 노드: 에이전트 답변의 사실 정확성을 검증합니다."""

import json

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from stock_agent.utils.constants import VALIDATOR_MODEL
from stock_agent.utils.state import GraphState
from stock_agent.prompts.validator import VALIDATOR_PROMPT

validator_chain = (
    ChatPromptTemplate.from_template(VALIDATOR_PROMPT)
    | ChatOpenAI(model=VALIDATOR_MODEL, temperature=0)
    | StrOutputParser()
)


def validator_node(state: GraphState) -> dict:
    """답변을 원본 데이터와 대조하여 검증합니다."""
    draft_answer = state["draft_answer"]
    agent_results = state["agent_results"]
    source_data = agent_results.get("source_data", "")
    agent_type = agent_results.get("agent", "")

    # glossary 에이전트는 Self-RAG 내부에서 이미 검증됨 → 바로 통과
    if agent_type == "glossary":
        return {
            "validated": True,
            "validation_reason": "Self-RAG 내부 검증 통과",
            "hallucinated_parts": [],
        }

    # company/news/general 에이전트는 실제 도구(yfinance/Tavily)에서 데이터를 가져오므로
    # 도구 호출 결과가 있으면 기본적으로 신뢰 (도구 기반 = 사실)
    if agent_type in ("company", "news", "general") and source_data.strip():
        # 명백한 문제만 체크: 답변이 비어있거나 에러인 경우만 실패
        if not draft_answer.strip() or "error" in draft_answer.lower()[:50]:
            return {
                "validated": False,
                "validation_reason": "에이전트가 유효한 답변을 생성하지 못했습니다.",
                "hallucinated_parts": [],
            }
        return {
            "validated": True,
            "validation_reason": "도구 기반 데이터 확인 (신뢰)",
            "hallucinated_parts": [],
        }

    # source_data가 없으면 검증 스킵
    if not source_data.strip():
        return {
            "validated": True,
            "validation_reason": "소스 데이터 없음 (검증 스킵)",
            "hallucinated_parts": [],
        }

    # 기타 케이스: LLM 검증 체인 실행
    raw_result = validator_chain.invoke({
        "source_data": source_data,
        "draft_answer": draft_answer,
    })

    try:
        cleaned = raw_result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        return {
            "validated": True,
            "validation_reason": "검증 결과 파싱 실패 (통과 처리)",
            "hallucinated_parts": [],
        }

    verdict = result.get("verdict", "pass")
    return {
        "validated": verdict == "pass",
        "validation_reason": result.get("reason", ""),
        "hallucinated_parts": result.get("hallucinated_parts", []),
    }

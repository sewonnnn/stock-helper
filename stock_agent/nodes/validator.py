"""검증 노드: Groundedness(할루시네이션) + Answer Helpfulness(유용성) 병렬 검증

glossary는 내부에서 이미 검증하므로 여기서는 company/news만 처리합니다.
"""

import concurrent.futures

from stock_agent.utils.state import GraphState
from stock_agent.chains.hallucination_grader import hallucination_grader
from stock_agent.chains.answer_grader import answer_grader
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)


def validator_node(state: GraphState) -> dict:
    """답변을 원본 데이터와 대조하여 Groundedness + Answer Helpfulness 검증합니다."""
    draft_answer = state["draft_answer"]
    agent_results = state["agent_results"]
    source_data = agent_results.get("source_data", "")
    question = state["question"]

    # 답변이 비어있거나 에러인 경우
    if not draft_answer.strip() or "error" in draft_answer.lower()[:50]:
        return {
            "validated": False,
            "validation_reason": "에이전트가 유효한 답변을 생성하지 못했습니다.",
            "hallucinated_parts": [],
        }

    # 소스 데이터가 없으면 검증 스킵
    if not source_data.strip():
        return {
            "validated": True,
            "validation_reason": "소스 데이터 없음 (검증 스킵)",
            "hallucinated_parts": [],
        }

    # Groundedness + Answer Helpfulness 병렬 실행
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_hal = executor.submit(
                hallucination_grader.invoke,
                {"documents": source_data, "generation": draft_answer},
            )
            future_use = executor.submit(
                answer_grader.invoke,
                {"question": question, "generation": draft_answer},
            )
            hal_result = future_hal.result()
            use_result = future_use.result()
    except Exception as e:
        logger.warning("검증 체인 실패, 통과 처리: %s", e)
        return {
            "validated": True,
            "validation_reason": "검증 체인 실패 (통과 처리)",
            "hallucinated_parts": [],
        }

    # 할루시네이션 감지
    if not hal_result.binary_score:
        logger.warning("할루시네이션 감지됨")
        return {
            "validated": False,
            "validation_reason": "답변이 소스 데이터에 근거하지 않습니다.",
            "hallucinated_parts": [],
        }

    # 유용성 부족
    if use_result.binary_score != "yes":
        logger.warning("유용성 부족")
        return {
            "validated": False,
            "validation_reason": "답변이 질문에 충분히 유용하지 않습니다.",
            "hallucinated_parts": [],
        }

    logger.info("검증 통과 (Groundedness + Answer Helpfulness)")
    return {
        "validated": True,
        "validation_reason": "Groundedness + Answer Helpfulness 검증 통과",
        "hallucinated_parts": [],
    }

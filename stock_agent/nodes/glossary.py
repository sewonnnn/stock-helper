"""용어설명 Self-RAG 노드

내부 흐름:
검색 → Document Relevance(문서 관련성) → 답변 생성 → Groundedness(할루시네이션) + Answer Helpfulness(유용성)
실패 시 general로 폴백 (Corrective RAG 패턴)
"""

import concurrent.futures

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import MAX_RETRIES
from stock_agent.tools.rag_tools import retriever
from stock_agent.chains.retrieval_grader import retrieval_grader
from stock_agent.chains.hallucination_grader import hallucination_grader
from stock_agent.chains.answer_grader import answer_grader
from stock_agent.chains.generation import generation_chain
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)

# glossary 실패 시 general 폴백을 위한 마커
GLOSSARY_FALLBACK = "__GLOSSARY_FALLBACK__"


def _extract_current_question(question: str) -> str:
    """보강된 질문에서 [현재 질문] 부분만 추출합니다.
    Pinecone 검색 시 맥락 텍스트가 포함되면 유사도가 낮아지므로."""
    marker = "[현재 질문]"
    if marker in question:
        after = question.split(marker, 1)[1]
        end_marker = "위 대화 맥락을"
        if end_marker in after:
            after = after.split(end_marker, 1)[0]
        return after.strip()
    return question


def _filter_relevant_docs(docs: list, question: str) -> list:
    """Document Relevance: 각 문서의 관련성을 병렬로 판단하여 관련 문서만 반환합니다."""
    if not docs:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(docs)) as executor:
        futures = {
            executor.submit(
                retrieval_grader.invoke,
                {"document": doc.page_content, "question": question},
            ): doc
            for doc in docs
        }
        relevant = []
        for future in concurrent.futures.as_completed(futures):
            doc = futures[future]
            try:
                result = future.result()
                if result.binary_score == "yes":
                    relevant.append(doc)
                else:
                    logger.info("Document Relevance 비관련 문서 제외: %s", doc.metadata.get("term", ""))
            except Exception as e:
                logger.warning("Document Relevance 판단 실패, 포함 처리: %s", e)
                relevant.append(doc)
        return relevant


def glossary_node(state: GraphState) -> dict:
    """Self-RAG 흐름으로 용어를 설명합니다.

    검색 → Document Relevance → 답변 생성 → Groundedness + Answer Helpfulness (재시도 1회)
    실패 시 draft_answer에 GLOSSARY_FALLBACK 마커를 넣어 general 폴백을 트리거.
    """
    question = state["question"]
    search_query = _extract_current_question(question)
    max_retries = MAX_RETRIES

    logger.info("glossary 검색 쿼리: %s", search_query)

    # 1. Pinecone 검색 (현재 질문만 사용하여 유사도 향상)
    try:
        docs = retriever.invoke(search_query)
    except Exception as e:
        logger.error("Pinecone 검색 실패: %s", e)
        logger.info("glossary → general 폴백 (Pinecone 실패)")
        return {
            "draft_answer": GLOSSARY_FALLBACK,
            "agent_results": {"source_data": "", "agent": "glossary"},
        }

    if not docs:
        logger.info("glossary → general 폴백 (검색 결과 없음)")
        return {
            "draft_answer": GLOSSARY_FALLBACK,
            "agent_results": {"source_data": "", "agent": "glossary"},
        }

    # 2. Document Relevance: 관련 문서만 필터링
    relevant_docs = _filter_relevant_docs(docs, search_query)
    if not relevant_docs:
        logger.info("glossary → general 폴백 (관련 문서 없음)")
        return {
            "draft_answer": GLOSSARY_FALLBACK,
            "agent_results": {"source_data": "", "agent": "glossary"},
        }

    # 소스 데이터 (관련 문서만)
    source_data = "\n\n".join(doc.page_content for doc in relevant_docs)

    # 3. 답변 생성 + Groundedness + Answer Helpfulness (재시도 포함)
    for attempt in range(max_retries + 1):
        try:
            generation = generation_chain.invoke(
                {"context": source_data, "question": question}
            )
        except Exception as e:
            logger.error("용어 답변 생성 실패 (시도 %d): %s", attempt, e)
            if attempt < max_retries:
                continue
            logger.info("glossary → general 폴백 (답변 생성 실패)")
            return {
                "draft_answer": GLOSSARY_FALLBACK,
                "agent_results": {"source_data": source_data, "agent": "glossary"},
            }

        # Groundedness + Answer Helpfulness 병렬 실행
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_hal = executor.submit(
                    hallucination_grader.invoke,
                    {"documents": source_data, "generation": generation}
                )
                future_use = executor.submit(
                    answer_grader.invoke,
                    {"question": question, "generation": generation}
                )
                hallucination_result = future_hal.result()
                usefulness_result = future_use.result()
        except Exception as e:
            logger.warning("검증 체인 실패 (시도 %d): %s", attempt, e)
            return {
                "draft_answer": generation,
                "agent_results": {"source_data": source_data, "agent": "glossary"},
            }

        if not hallucination_result.binary_score:
            if attempt < max_retries:
                continue
            else:
                logger.info("glossary → general 폴백 (할루시네이션 감지)")
                return {
                    "draft_answer": GLOSSARY_FALLBACK,
                    "agent_results": {"source_data": source_data, "agent": "glossary"},
                }

        if usefulness_result.binary_score == "yes":
            return {
                "draft_answer": generation,
                "agent_results": {"source_data": source_data, "agent": "glossary"},
            }
        else:
            if attempt < max_retries:
                continue
            else:
                logger.info("glossary → general 폴백 (유용성 부족)")
                return {
                    "draft_answer": GLOSSARY_FALLBACK,
                    "agent_results": {"source_data": source_data, "agent": "glossary"},
                }

    return {
        "draft_answer": GLOSSARY_FALLBACK,
        "agent_results": {"source_data": source_data, "agent": "glossary"},
    }

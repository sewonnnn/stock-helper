"""용어설명 Self-RAG 정석 노드

내부 흐름:
검색 → ISREL(문서 관련성, 병렬) → 답변 생성 → ISSUP(할루시네이션) → ISUSE(유용성)
"""

import concurrent.futures

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import MAX_RETRIES
from stock_agent.tools.rag_tools import retriever
from stock_agent.chains.retrieval_grader import retrieval_grader
from stock_agent.chains.hallucination_grader import hallucination_grader
from stock_agent.chains.answer_grader import answer_grader
from stock_agent.chains.generation import generation_chain


def _grade_document(question: str, doc_content: str) -> tuple[str, str]:
    """단일 문서의 관련성을 판단합니다. (병렬 실행용)"""
    grade = retrieval_grader.invoke(
        {"question": question, "document": doc_content}
    )
    return (grade.binary_score, doc_content)


def glossary_node(state: GraphState) -> dict:
    """Self-RAG 정석 흐름으로 용어를 설명합니다.

    ISREL(병렬) → 답변 생성 → ISSUP → ISUSE (재시도 1회)
    """
    question = state["question"]
    max_retries = MAX_RETRIES

    # 1. Pinecone 검색
    docs = retriever.invoke(question)
    if not docs:
        return {
            "draft_answer": "용어집에서 관련 정보를 찾을 수 없습니다.",
            "agent_results": {"source_data": "", "agent": "glossary"},
        }

    # 2. ISREL: 문서 관련성 판단 (병렬 처리)
    # ThreadPoolExecutor: 여러 작업을 스레드 풀에 넣어서 동시에 실행시켜주는 도구
    relevant_contents = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(docs)) as executor:
        # 각 문서를 별도 스레드에 제출
        # futures: executor.submit()의 반환값, 아직 완료되지 않았지만 나중에 결과를 받을 수 있는 객체
        futures = [
            executor.submit(_grade_document, question, doc.page_content)
            for doc in docs
        ]
        # 완료되는 순서대로 결과 수집
        for future in concurrent.futures.as_completed(futures):
            score, content = future.result()  # 번호표로 결과 받기
            if score == "yes":
                relevant_contents.append(content)

    if not relevant_contents:
        return {
            "draft_answer": "용어집에 해당 내용이 없습니다. 다른 질문을 해주세요.",
            "agent_results": {"source_data": "", "agent": "glossary"},
        }

    # 소스 데이터
    source_data = "\n\n".join(relevant_contents)

    # 3. 답변 생성 + ISSUP + ISUSE (재시도 포함)
    for attempt in range(max_retries + 1):
        generation = generation_chain.invoke(
            {"context": source_data, "question": question}
        )

        # ISSUP + ISUSE 병렬 실행
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

        if not hallucination_result.binary_score:
            if attempt < max_retries:
                continue
            else:
                return {
                    "draft_answer": "확인 불가합니다. 정확한 정보를 생성할 수 없습니다.",
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
                return {
                    "draft_answer": generation,
                    "agent_results": {"source_data": source_data, "agent": "glossary"},
                }

    return {
        "draft_answer": "확인 불가합니다.",
        "agent_results": {"source_data": source_data, "agent": "glossary"},
    }

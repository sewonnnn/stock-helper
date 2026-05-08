"""검색 기반 체인 노드 공통 로직

news, general, advisor 노드가 공유하는 흐름:
(선택) 검색 쿼리 생성 (LIGHT_MODEL) → tavily 검색 → Document Relevance(관련성 필터) → LLM 합성 (DEFAULT_MODEL)
"""

import concurrent.futures

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from stock_agent.utils.constants import DEFAULT_MODEL, LIGHT_MODEL, ERROR_MESSAGES
from stock_agent.chains.retrieval_grader import retrieval_grader
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)


class SearchQuery(BaseModel):
    """검색 쿼리 생성 결과"""
    query: str = Field(description="검색 쿼리")


_query_llm = ChatOpenAI(model=LIGHT_MODEL, temperature=0)
_synthesis_llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=0)


def _parse_tavily_results(raw_results) -> list[dict]:
    """tavily 검색 결과를 개별 항목 리스트로 파싱합니다."""
    if not raw_results:
        return []

    results = raw_results.get("results", []) if isinstance(raw_results, dict) else []
    if not results:
        return []

    items = []
    for r in results:
        items.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        })
    return items


def _filter_relevant_results(items: list[dict], question: str) -> list[dict]:
    """Document Relevance: 각 검색 결과의 관련성을 병렬로 판단하여 관련 항목만 반환합니다."""
    if not items:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(items)) as executor:
        futures = {
            executor.submit(
                retrieval_grader.invoke,
                {"document": item["content"], "question": question},
            ): item
            for item in items
        }
        relevant = []
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                if result.binary_score == "yes":
                    relevant.append(item)
                else:
                    logger.info("비관련 결과 제외 (Document Relevance): %s", item["title"][:50])
            except Exception as e:
                logger.warning("Document Relevance 판단 실패, 포함 처리: %s", e)
                relevant.append(item)
        return relevant


def _items_to_source_data(items: list[dict]) -> tuple[str, list[str]]:
    """필터링된 항목 리스트를 source_data 텍스트와 URL 리스트로 변환합니다."""
    entries = []
    urls = []
    for item in items:
        entries.append(f"제목: {item['title']}\nURL: {item['url']}\n내용: {item['content']}")
        if item["url"]:
            urls.append(item["url"])
    source_data = "\n\n---\n\n".join(entries)
    return source_data, urls


def run_search_chain(
    question: str,
    synthesis_prompt: str,
    search_tool,
    agent_name: str,
    empty_message: str,
    error_key: str,
    query_prompt: str | None = None,
) -> dict:
    """검색 기반 체인을 실행합니다.

    Args:
        question: 사용자 질문
        synthesis_prompt: 결과 합성용 시스템 프롬프트
        search_tool: tavily 검색 도구 인스턴스
        agent_name: 에이전트 이름 (예: "news", "general", "advisor")
        empty_message: 검색 결과 없을 때 메시지
        error_key: ERROR_MESSAGES 딕셔너리 키
        query_prompt: 검색 쿼리 생성용 시스템 프롬프트 (None이면 질문을 그대로 검색)
    """
    try:
        # Step 1: 검색 쿼리 결정
        if query_prompt:
            prompt = ChatPromptTemplate.from_messages([
                ("system", query_prompt),
                ("human", "{question}"),
            ])
            query_chain = prompt | _query_llm.with_structured_output(SearchQuery)
            search_query = query_chain.invoke({"question": question}).query
        else:
            search_query = question

        logger.info("[%s] 검색 쿼리: %s", agent_name, search_query)

        # Step 2: Tavily 검색
        raw_results = search_tool.invoke(search_query)
        items = _parse_tavily_results(raw_results)

        if not items:
            return {
                "draft_answer": empty_message,
                "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
            }

        # Step 3: Document Relevance — 관련 결과만 필터링
        relevant_items = _filter_relevant_results(items, question)

        if not relevant_items:
            return {
                "draft_answer": empty_message,
                "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
            }

        source_data, source_urls = _items_to_source_data(relevant_items)

        # Step 4: LLM 합성 (DEFAULT_MODEL)
        synth_prompt = ChatPromptTemplate.from_messages([
            ("system", synthesis_prompt),
            ("human", "질문: {question}\n\n검색 결과:\n{data}"),
        ])
        draft = (synth_prompt | _synthesis_llm).invoke({
            "question": question,
            "data": source_data,
        }).content

        return {
            "draft_answer": draft,
            "agent_results": {
                "source_data": source_data,
                "source_urls": source_urls,
                "agent": agent_name,
            },
        }

    except Exception as e:
        logger.error("%s 체인 실패: %s", agent_name, e, exc_info=True)
        return {
            "draft_answer": ERROR_MESSAGES[error_key],
            "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
        }

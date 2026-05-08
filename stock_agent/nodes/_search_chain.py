"""검색 기반 체인 노드 공통 로직

news, general, advisor 노드가 공유하는 흐름:
(선택) 검색 쿼리 생성 (LIGHT_MODEL) → tavily 검색 → LLM 합성 (DEFAULT_MODEL)
"""

import json

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from stock_agent.utils.constants import DEFAULT_MODEL, LIGHT_MODEL, ERROR_MESSAGES
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)


class SearchQuery(BaseModel):
    """검색 쿼리 생성 결과"""
    query: str = Field(description="검색 쿼리")


_query_llm = ChatOpenAI(model=LIGHT_MODEL, temperature=0)
_synthesis_llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=0)


def _parse_tavily_results(raw_results) -> tuple[str, list[str]]:
    """tavily 검색 결과에서 LLM용 텍스트와 출처 URL을 분리합니다.

    Returns:
        (source_data, urls): LLM에 전달할 텍스트, 출처 URL 리스트
    """
    if not raw_results:
        return "", []

    results = raw_results.get("results", []) if isinstance(raw_results, dict) else []

    if not results:
        return str(raw_results), []

    # 각 결과에서 title, url, content를 구조화
    entries = []
    urls = []
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")
        entries.append(f"제목: {title}\nURL: {url}\n내용: {content}")
        if url:
            urls.append(url)

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

        # Step 2: Tavily 검색 + 결과 파싱
        raw_results = search_tool.invoke(search_query)
        source_data, source_urls = _parse_tavily_results(raw_results)

        if not source_data:
            return {
                "draft_answer": empty_message,
                "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
            }

        # Step 3: LLM 합성 (DEFAULT_MODEL)
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

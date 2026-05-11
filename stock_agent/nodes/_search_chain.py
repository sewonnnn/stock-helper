"""검색 기반 체인 노드 공통 로직
news, general, advisor 노드가 공유하는 흐름:
(선택) 검색 쿼리 생성 (LIGHT_MODEL) → tavily 검색 → 신뢰 도메인 필터 → LLM 합성 (DEFAULT_MODEL)
"""

from urllib.parse import urlparse

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


def _filter_trusted_items(items: list[dict], trusted_domains: list[str] | None) -> list[dict]:
    """신뢰 도메인에 속하는 검색 결과만 필터링합니다. trusted_domains가 None이면 전체 반환."""
    if not trusted_domains:
        return items
    filtered = []
    for item in items:
        try:
            host = urlparse(item["url"]).hostname or ""
            if any(host == d or host.endswith("." + d) for d in trusted_domains):
                filtered.append(item)
        except Exception:
            continue
    return filtered


def run_search_chain(
    question: str,
    synthesis_prompt: str,
    search_tool,
    agent_name: str,
    empty_message: str,
    error_key: str,
    query_prompt: str | None = None,
    fallback_on_empty: bool = False,
    trusted_domains: list[str] | None = None,
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
        fallback_on_empty: True이면 검색 결과 없을 때 LLM 자체 지식으로 답변 생성
        trusted_domains: 신뢰 도메인 목록 (LLM에 넘기기 전 필터링)
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

        # Step 2: Tavily 검색 → 신뢰 도메인 필터링
        raw_results = search_tool.invoke(search_query)
        items = _parse_tavily_results(raw_results)
        items = _filter_trusted_items(items, trusted_domains)
        logger.info("[%s] 신뢰 도메인 필터 후 결과: %d건", agent_name, len(items))

        if not items:
            if fallback_on_empty:
                # 검색 결과 없음 → LLM 자체 지식으로 폴백 답변 생성
                logger.info("[%s] 검색 결과 없음 → LLM 폴백", agent_name)
                synth_prompt = ChatPromptTemplate.from_messages([
                    ("system", synthesis_prompt),
                    ("human", "질문: {question}\n\n검색 결과:\n(검색 결과가 없습니다. 당신의 지식을 바탕으로 답변해 주세요.)"),
                ])
                draft = (synth_prompt | _synthesis_llm).invoke({
                    "question": question,
                    "data": "",
                }).content
                return {
                    "draft_answer": draft,
                    "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
                }
            return {
                "draft_answer": empty_message,
                "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
            }

        source_data, source_urls = _items_to_source_data(items)

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
                "news_items": [
                    {"title": item["title"], "url": item["url"]}
                    for item in items
                ],
                "agent": agent_name,
            },
        }

    except Exception as e:
        logger.error("%s 체인 실패: %s", agent_name, e, exc_info=True)
        return {
            "draft_answer": ERROR_MESSAGES[error_key],
            "agent_results": {"source_data": "", "source_urls": [], "agent": agent_name},
        }

"""메인 LangGraph StateGraph 조립

흐름:
  맥락 보강 → 슈퍼바이저 → (company | news) → 검증 → 응답 → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → (glossary | general | advisor) → 직통 응답 → 히스토리 저장
  검증 실패 시 → 슈퍼바이저로 복귀 (최대 1회 재시도)
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import MAX_RETRIES, TRUSTED_NEWS_DOMAINS, TRUSTED_ADVISOR_DOMAINS
from stock_agent.utils.schemas import StockResponse
from stock_agent.nodes.supervisor import supervisor_node
from stock_agent.nodes.company import company_node
from stock_agent.nodes.news import news_node
from stock_agent.nodes.glossary import glossary_node
from stock_agent.nodes.general import general_node
from stock_agent.nodes.advisor import advisor_node
from stock_agent.nodes.validator import validator_node
from stock_agent.nodes.responder import responder_node


def enrich_question(state: GraphState) -> dict:
    """이전 대화 맥락이 있으면 현재 질문 앞에 붙여서 보강합니다."""
    chat_history = state.get("chat_history", [])
    question = state["question"]

    # 이전 메시지가 없으면 (첫 메시지) 보강 불필요
    if len(chat_history) <= 1:
        return {}

    # 마지막은 현재 사용자 메시지이므로 그 이전까지만 맥락으로 사용
    previous = chat_history[:-1][-10:]  # 최근 5턴(10메시지)
    context_lines = []
    for msg in previous:
        role = "사용자" if msg.get("role") == "user" else "AI"
        context_lines.append(f"{role}: {msg.get('content', '')}")

    enriched = (
        "[이전 대화 맥락]\n"
        + "\n".join(context_lines)
        + f"\n\n[현재 질문]\n{question}\n\n"
        + "위 대화 맥락을 참고하여 현재 질문에 답변하세요. "
        + "대명사나 생략된 주어는 맥락에서 추론하세요."
    )
    return {"question": enriched}


def save_history(state: GraphState) -> dict:
    """최종 응답 요약을 chat_history에 추가합니다."""
    final_answer = state.get("final_answer")
    if not final_answer:
        return {"chat_history": [{"role": "assistant", "content": "응답 실패"}]}

    parts = []
    if final_answer.종목:
        parts.append(f"{final_answer.종목.company_name}({final_answer.종목.ticker})")
    if final_answer.가격:
        parts.append(f"현재가 ${final_answer.가격.current_price}")
    if final_answer.인사이트:
        parts.append(final_answer.인사이트[:150])
    if final_answer.용어설명:
        parts.append(final_answer.용어설명[:150])

    summary = ", ".join(parts) if parts else "응답 완료"
    return {"chat_history": [{"role": "assistant", "content": summary}]}


def route_by_supervisor(state: GraphState) -> str:
    """슈퍼바이저 결과에 따라 에이전트 노드를 선택합니다."""
    route = state["route"]
    mapping = {
        "company": "company",
        "news": "news",
        "glossary": "glossary",
        "general": "general",
        "advisor": "advisor",
    }
    return mapping.get(route, "general")


def check_validation(state: GraphState) -> str:
    """검증 결과에 따라 응답 or 재시도를 결정합니다."""
    if state["validated"]:
        return "responder"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return "responder"
    return "retry"


def increment_retry(state: GraphState) -> dict:
    """재시도 카운터를 증가시킵니다."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def _filter_by_trusted_domains(urls: list[str], trusted_domains: list[str]) -> list[str]:
    """신뢰 도메인에 속하는 URL만 필터링합니다. PDF 등 파일 링크는 제외."""
    from urllib.parse import urlparse

    _EXCLUDED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip"}

    filtered = []
    for url in urls:
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in _EXCLUDED_EXTENSIONS):
                continue
            if any(hostname == d or hostname.endswith("." + d) for d in trusted_domains):
                filtered.append(url)
        except Exception:
            continue
    return filtered


def _validate_urls(urls: list[str], timeout: float = 2.0) -> list[str]:
    """URL 목록을 병렬로 유효성 검사하여 살아있는 URL만 반환합니다."""
    if not urls:
        return []

    import concurrent.futures
    import requests

    def _check(url: str) -> str | None:
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            return url if resp.status_code < 400 else None
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as executor:
        results = executor.map(_check, urls)
        return [url for url in results if url]


def _extract_followups(text: str) -> tuple[str, list[str]]:
    """텍스트 끝에서 '후속질문: A|B|C' 패턴을 추출하고 본문과 분리합니다."""
    import re
    match = re.search(r'후속질문\s*[:：]\s*(.+)$', text, re.MULTILINE)
    if not match:
        return text, []
    followups = [q.strip() for q in match.group(1).split('|') if q.strip()][:3]
    clean_text = text[:match.start()].rstrip()
    return clean_text, followups


def glossary_direct_response(state: GraphState) -> dict:
    """glossary는 Self-RAG 내부에서 이미 검증 완료이므로 Responder 스킵.
    직접 StockResponse를 구성합니다."""
    draft = state["draft_answer"]
    source_data = state["agent_results"].get("source_data", "")

    clean_draft, followups = _extract_followups(draft)

    sources = []
    if source_data:
        sources = ["용어집 (Pinecone RAG)"]

    return {
        "final_answer": StockResponse(
            용어설명=clean_draft,
            출처=sources,
            확신도="높음",
            후속질문=followups,
        )
    }


def general_direct_response(state: GraphState) -> dict:
    """general은 웹 검색 결과를 이미 한국어로 정리했으므로 Responder 스킵.
    draft_answer를 인사이트 필드에 그대로 전달합니다."""
    import re

    draft = state["draft_answer"]
    source_data = state["agent_results"].get("source_data", "")

    # 후속질문 추출
    draft, followups = _extract_followups(draft)

    # 본문에서 인라인 출처 링크 제거: [출처: 매일경제](url) → 제거
    clean_draft = re.sub(r'\s*\[출처[^\]]*\]\(https?://[^\)]+\)', '', draft)
    # 혹시 [텍스트](url) 형태도 제거
    clean_draft = re.sub(r'\s*\[([^\]]+)\]\(https?://[^\)]+\)', '', clean_draft)

    # source_data에서 URL 추출 → 신뢰 도메인 필터 → 유효성 검사
    urls = re.findall(r'https?://[^\s\"\'\]\,]+', source_data)
    unique_urls = list(dict.fromkeys(urls))[:5]
    trusted_urls = _filter_by_trusted_domains(unique_urls, TRUSTED_NEWS_DOMAINS)
    sources = _validate_urls(trusted_urls)

    return {
        "final_answer": StockResponse(
            인사이트=clean_draft,
            출처=sources,
            확신도="중간",
            후속질문=followups,
        )
    }


def advisor_direct_response(state: GraphState) -> dict:
    """advisor는 웹 검색 기반 맞춤 안내이므로 Responder 스킵.
    draft_answer를 인사이트 필드에 그대로 전달합니다."""
    import re

    draft = state["draft_answer"]
    source_data = state["agent_results"].get("source_data", "")

    # 후속질문 추출
    draft, followups = _extract_followups(draft)

    # 본문에서 인라인 출처 링크 제거
    clean_draft = re.sub(r'\s*\[출처[^\]]*\]\(https?://[^\)]+\)', '', draft)
    clean_draft = re.sub(r'\s*\[([^\]]+)\]\(https?://[^\)]+\)', '', clean_draft)

    # source_data에서 URL 추출 → 신뢰 도메인 필터 → 유효성 검사
    urls = re.findall(r'https?://[^\s\"\'\]\,]+', source_data)
    unique_urls = list(dict.fromkeys(urls))[:5]
    trusted_urls = _filter_by_trusted_domains(unique_urls, TRUSTED_ADVISOR_DOMAINS)
    sources = _validate_urls(trusted_urls)

    return {
        "final_answer": StockResponse(
            인사이트=clean_draft,
            출처=sources,
            확신도="중간",
            후속질문=followups,
        )
    }


def build_graph():
    """메인 그래프를 조립하여 반환합니다. MemorySaver checkpointer 포함."""

    workflow = StateGraph(GraphState)

    # 노드 등록
    workflow.add_node("enrich_question", enrich_question)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("company", company_node)
    workflow.add_node("news", news_node)
    workflow.add_node("glossary", glossary_node)
    workflow.add_node("general", general_node)
    workflow.add_node("general_response", general_direct_response)
    workflow.add_node("advisor", advisor_node)
    workflow.add_node("advisor_response", advisor_direct_response)
    workflow.add_node("glossary_response", glossary_direct_response)
    workflow.add_node("validator", validator_node)
    workflow.add_node("responder", responder_node)
    workflow.add_node("increment_retry", increment_retry)
    workflow.add_node("save_history", save_history)

    # 진입점: 맥락 보강 → 슈퍼바이저
    workflow.set_entry_point("enrich_question")
    workflow.add_edge("enrich_question", "supervisor")

    # 슈퍼바이저 → 에이전트 (조건부 라우팅)
    workflow.add_conditional_edges(
        "supervisor",
        route_by_supervisor,
        {
            "company": "company",
            "news": "news",
            "glossary": "glossary",
            "general": "general",
            "advisor": "advisor",
        },
    )

    # company/news → 검증 → 응답
    workflow.add_edge("company", "validator")
    workflow.add_edge("news", "validator")

    # general → 직통 응답 → 히스토리 저장
    workflow.add_edge("general", "general_response")
    workflow.add_edge("general_response", "save_history")

    # advisor → 직통 응답 → 히스토리 저장
    workflow.add_edge("advisor", "advisor_response")
    workflow.add_edge("advisor_response", "save_history")

    # glossary → 직통 응답 → 히스토리 저장
    workflow.add_edge("glossary", "glossary_response")
    workflow.add_edge("glossary_response", "save_history")

    # 검증 → 응답 or 재시도 (조건부)
    workflow.add_conditional_edges(
        "validator",
        check_validation,
        {
            "responder": "responder",
            "retry": "increment_retry",
        },
    )

    # 재시도 → 슈퍼바이저로 복귀
    workflow.add_edge("increment_retry", "supervisor")

    # 응답 → 히스토리 저장 → 종료
    workflow.add_edge("responder", "save_history")
    workflow.add_edge("save_history", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=[StockResponse])
    return workflow.compile(checkpointer=MemorySaver(serde=serde))


# 그래프 인스턴스
graph = build_graph()

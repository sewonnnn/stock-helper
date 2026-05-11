"""메인 LangGraph StateGraph 조립

흐름 (모든 라우트가 직통 응답 패턴 — Responder LLM 없음):
  맥락 보강 → 슈퍼바이저 → company  → 직통 응답(yfinance 데이터 결정론적 매핑) → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → news     → 직통 응답 → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → general  → 직통 응답 → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → advisor  → 직통 응답 → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → chat     → 직통 응답 → 히스토리 저장
  맥락 보강 → 슈퍼바이저 → glossary → 성공: 직통 응답 / 실패: general 폴백 (Corrective RAG)
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from stock_agent.utils.state import GraphState
from stock_agent.utils.constants import TRUSTED_NEWS_DOMAINS
from stock_agent.utils.schemas import (
    StockResponse, NewsItem, TickerInfo, PriceInfo, Metric,
)
from stock_agent.nodes.supervisor import supervisor_node
from stock_agent.nodes.company import company_node
from stock_agent.nodes.news import news_node
from stock_agent.nodes.glossary import glossary_node, GLOSSARY_FALLBACK
from stock_agent.nodes.general import general_node
from stock_agent.nodes.advisor import advisor_node
from stock_agent.nodes.chat import chat_node


import time
from stock_agent.utils.logging_config import get_logger

_timing_logger = get_logger("timing")


def _needs_context(question: str, chat_history: list) -> bool:
    """LLM(LIGHT_MODEL)으로 현재 질문에 이전 대화 맥락이 필요한지 판단합니다."""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field
    from stock_agent.utils.constants import LIGHT_MODEL

    class ContextDecision(BaseModel):
        needs_context: bool = Field(description="이전 대화 맥락이 필요하면 true")

    # 최근 대화 요약 (판단용으로 간략히)
    recent = chat_history[:-1][-4:]  # 최근 2턴만
    history_summary = " / ".join(
        f"{'사용자' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')[:80]}"
        for m in recent
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You determine if a user's current question requires previous conversation context to understand.\n"
            "Return true ONLY if the question contains references that cannot be understood without context:\n"
            "- Pronouns referring to previous topics (그 회사, 이거, 그거, 아까)\n"
            "- Follow-up requests (더 알려줘, 자세히, 다른 방법)\n"
            "- Questions about previous AI answers (왜 추천해?, 그 이유)\n\n"
            "Return false if the question is self-contained with a clear topic:\n"
            "- Has a specific subject (삼성전자 분석, 공매도 위험성, ETF란?)\n"
            "- New topic unrelated to previous conversation\n"
            "- Complete question that makes sense on its own"
        )),
        ("human", "이전 대화: {history}\n\n현재 질문: {question}"),
    ])

    try:
        chain = prompt | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(ContextDecision)
        t0 = time.perf_counter()
        result = chain.invoke({"history": history_summary, "question": question})
        _timing_logger.info("[_needs_context LLM] %.0fms", (time.perf_counter() - t0) * 1000)
        return result.needs_context
    except Exception:
        return True  # 판단 실패 시 안전하게 맥락 포함


def enrich_question(state: GraphState) -> dict:
    """이전 대화 맥락이 필요한 경우에만 질문을 보강합니다."""
    t_start = time.perf_counter()
    chat_history = state.get("chat_history", [])
    question = state["question"]

    # 이전 메시지가 없으면 (첫 메시지) 보강 불필요
    if len(chat_history) <= 1:
        _timing_logger.info("[enrich_question] %.0fms (skip: 첫 메시지)", (time.perf_counter() - t_start) * 1000)
        return {}

    # LLM으로 맥락 필요 여부 판단
    if not _needs_context(question, chat_history):
        _timing_logger.info("[enrich_question] %.0fms (skip: 맥락 불필요)", (time.perf_counter() - t_start) * 1000)
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
    _timing_logger.info("[enrich_question] %.0fms (맥락 주입)", (time.perf_counter() - t_start) * 1000)
    return {"question": enriched}


def save_history(state: GraphState) -> dict:
    """최종 응답 요약을 chat_history에 추가합니다."""
    final_answer = state.get("final_answer")
    if not final_answer:
        return {"chat_history": [{"role": "assistant", "content": "응답 실패"}]}

    parts = []
    if final_answer.ticker_info:
        parts.append(f"{final_answer.ticker_info.company_name}({final_answer.ticker_info.ticker})")
    if final_answer.price:
        parts.append(f"현재가 ${final_answer.price.current_price}")
    if final_answer.insight:
        parts.append(final_answer.insight[:150])
    if final_answer.glossary:
        parts.append(final_answer.glossary[:150])

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
        "chat": "chat",
    }
    return mapping.get(route, "general")


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



# 추천 질문 추출
def _extract_followups(text: str) -> tuple[str, list[str]]:
    """텍스트 끝에서 'follow_up: A|B|C' 패턴을 추출하고 본문과 분리합니다."""
    import re
    match = re.search(r'(?:follow_up|후속질문)\s*[:：]\s*(.+)$', text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return text, []
    followups = [q.strip() for q in match.group(1).split('|') if q.strip()][:3]
    clean_text = text[:match.start()].rstrip()
    return clean_text, followups

# 회사 소개 한 줄 뽑음
def _extract_company_intro(text: str) -> tuple[str, str | None]:
    """텍스트에서 'company_intro: ...' 패턴을 추출하고 본문과 분리합니다."""
    import re
    match = re.search(r'(?:company_intro|회사소개)\s*[:：]\s*(.+)$', text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return text, None
    intro = match.group(1).strip()
    clean_text = text[:match.start()].rstrip()
    return clean_text, intro


def _level_threshold(value: float | None, low_max: float, high_min: float) -> str:
    """수치 임계값으로 level 분류. low_max 미만=낮음, high_min 초과=높음, 그 사이=보통."""
    if value is None:
        return "정보없음"
    if value < low_max:
        return "낮음"
    if value > high_min:
        return "높음"
    return "보통"


def extract_company_price_data(data: dict) -> dict:
    """yfinance data dict에서 가격·지표 구조화 데이터를 추출합니다."""
    if not data or "error" in data:
        return {}

    overview = data.get("overview", {})
    valuation = data.get("valuation", {})
    health = data.get("financial_health", {})

    ticker_info = TickerInfo(
        ticker=overview.get("ticker", ""),
        company_name=overview.get("company_name", "") or overview.get("ticker", ""),
        sector=overview.get("sector"),
        industry=overview.get("industry"),
    )

    price = None
    cur = overview.get("current_price")
    prev = overview.get("previous_close")
    if cur is not None and prev is not None:
        price = PriceInfo(
            current_price=cur,
            previous_close=prev,
            change=overview.get("change") or 0.0,
            change_percent=overview.get("change_percent") or 0.0,
            currency=overview.get("currency", "USD"),
            krw_price=overview.get("krw_price"),
            usd_krw_rate=overview.get("usd_krw_rate"),
            market_cap=overview.get("market_cap"),
            market_cap_tier=overview.get("market_cap_tier"),
        )

    metrics: list[Metric] = []
    per = valuation.get("per")
    if per is not None:
        metrics.append(Metric(name="PER", value=f"{per:.1f}", level=_level_threshold(per, 15, 25)))
    pbr = valuation.get("pbr")
    if pbr is not None:
        metrics.append(Metric(name="PBR", value=f"{pbr:.2f}", level=_level_threshold(pbr, 1, 3)))
    roe = health.get("return_on_equity")
    if roe:
        try:
            roe_val = float(roe.replace("%", "").strip())
            metrics.append(Metric(name="ROE", value=roe, level=_level_threshold(roe_val, 10, 20)))
        except ValueError:
            pass
    div_yield = valuation.get("dividend_yield")
    if div_yield is not None:
        metrics.append(Metric(name="배당수익률", value=f"{div_yield * 100:.2f}%", level=_level_threshold(div_yield * 100, 1, 4)))

    return {
        "ticker_info": ticker_info,
        "price": price,
        "key_metrics": metrics or None,
    }


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
            glossary=clean_draft,
            sources=sources,
            confidence="높음",
            follow_up=followups,
        )
    }


def news_direct_response(state: GraphState) -> dict:
    """news는 tavily 결과가 이미 구조화되어 있으므로 Responder 스킵.
    StockResponse를 직접 구성합니다."""
    import re

    draft = state["draft_answer"]
    agent_results = state["agent_results"]
    source_urls = agent_results.get("source_urls", [])
    news_items_raw = agent_results.get("news_items", [])

    # 후속질문 추출
    draft, followups = _extract_followups(draft)

    # 본문에서 인라인 출처 링크 제거
    clean_draft = re.sub(r'\s*\[출처[^\]]*\]\(https?://[^\)]+\)', '', draft)
    clean_draft = re.sub(r'\s*\[([^\]]+)\]\(https?://[^\)]+\)', '', clean_draft)

    # tavily 결과에서 NewsItem 직접 구성
    news_list = []
    for item in news_items_raw:
        url = item.get("url", "")
        title = item.get("title", "")
        if title and url:
            # URL에서 출처(도메인) 추출
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
            news_list.append(NewsItem(
                title=title,
                source=domain,
                url=url,
            ))

    # 출처 URL 필터 (신뢰 도메인만)
    sources = _filter_by_trusted_domains(source_urls, TRUSTED_NEWS_DOMAINS)

    return {
        "final_answer": StockResponse(
            news=news_list if news_list else None,
            insight=clean_draft,
            sources=sources,
            confidence="높음" if news_list else "중간",
            follow_up=followups,
        )
    }


def web_search_direct_response(state: GraphState) -> dict:
    """general·advisor 공용 직통 응답. 웹 검색 결과 기반 StockResponse 구성."""
    import re

    draft = state["draft_answer"]
    source_urls = state["agent_results"].get("source_urls", [])

    # 후속질문 추출
    draft, followups = _extract_followups(draft)

    # 본문에서 인라인 출처 링크 제거
    clean_draft = re.sub(r'\s*\[출처[^\]]*\]\(https?://[^\)]+\)', '', draft)
    clean_draft = re.sub(r'\s*\[([^\]]+)\]\(https?://[^\)]+\)', '', clean_draft)

    sources = source_urls

    return {
        "final_answer": StockResponse(
            insight=clean_draft,
            sources=sources,
            follow_up=followups,
        )
    }


def chat_direct_response(state: GraphState) -> dict:
    """chat은 대화 맥락만으로 짧게 답변하므로 Responder 스킵."""
    draft = state["draft_answer"]
    draft, followups = _extract_followups(draft)

    return {
        "final_answer": StockResponse(
            insight=draft,
            sources=[],
            confidence="중간",
            follow_up=followups,
        )
    }


def company_direct_response(state: GraphState) -> dict:
    """company는 yfinance 데이터를 결정론적으로 매핑.
    insight는 노드 합성 LLM의 draft를 그대로 사용, 구조화 필드는 코드로 추출."""
    draft = state["draft_answer"]
    agent_results = state["agent_results"]
    data = agent_results.get("data_dict") or {}

    clean_draft, followups = _extract_followups(draft)
    clean_draft, company_intro_kr = _extract_company_intro(clean_draft)

    extracted = extract_company_price_data(data)
    if not extracted:
        return {
            "final_answer": StockResponse(
                insight=clean_draft,
                follow_up=followups,
            )
        }

    return {
        "final_answer": StockResponse(
            ticker_info=extracted["ticker_info"],
            price=extracted["price"],
            key_metrics=extracted["key_metrics"],
            company_intro=company_intro_kr,
            insight=clean_draft,
            follow_up=followups,
        )
    }


def build_graph():
    """메인 그래프를 조립하여 반환합니다. MemorySaver checkpointer 포함."""

    workflow = StateGraph(GraphState)

    # 노드 등록
    workflow.add_node("enrich_question", enrich_question)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("company", company_node)
    workflow.add_node("company_response", company_direct_response)
    workflow.add_node("news", news_node)
    workflow.add_node("news_response", news_direct_response)
    workflow.add_node("glossary", glossary_node)
    workflow.add_node("general", general_node)
    workflow.add_node("general_response", web_search_direct_response)
    workflow.add_node("advisor", advisor_node)
    workflow.add_node("advisor_response", web_search_direct_response)
    workflow.add_node("chat", chat_node)
    workflow.add_node("chat_response", chat_direct_response)
    workflow.add_node("glossary_response", glossary_direct_response)
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
            "chat": "chat",
        },
    )

    # company → 직통 응답 → 히스토리 저장
    workflow.add_edge("company", "company_response")
    workflow.add_edge("company_response", "save_history")

    # news → 직통 응답 → 히스토리 저장
    workflow.add_edge("news", "news_response")
    workflow.add_edge("news_response", "save_history")

    # general → 직통 응답 → 히스토리 저장
    workflow.add_edge("general", "general_response")
    workflow.add_edge("general_response", "save_history")

    # advisor → 직통 응답 → 히스토리 저장
    workflow.add_edge("advisor", "advisor_response")
    workflow.add_edge("advisor_response", "save_history")

    # chat → 직통 응답 → 히스토리 저장
    workflow.add_edge("chat", "chat_response")
    workflow.add_edge("chat_response", "save_history")

    # glossary → 성공이면 직통 응답, 실패면 general 폴백 (Corrective RAG)
    def route_glossary(state: GraphState) -> str:
        if state.get("draft_answer") == GLOSSARY_FALLBACK:
            return "general"
        return "glossary_response"

    workflow.add_conditional_edges(
        "glossary",
        route_glossary,
        {
            "glossary_response": "glossary_response",
            "general": "general",
        },
    )
    workflow.add_edge("glossary_response", "save_history")

    # 히스토리 저장 → 종료
    workflow.add_edge("save_history", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=[StockResponse])
    return workflow.compile(checkpointer=MemorySaver(serde=serde))


# 그래프 인스턴스
graph = build_graph()

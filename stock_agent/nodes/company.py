"""기업분석 체인 노드

에이전트(create_agent) 대신 체인으로 구현하여 LLM 호출을 최소화합니다.
흐름: 코드 기반 티커 해석 → (실패 시 LLM 추론) → yfinance info 단일 호출 → LLM 합성
"""

import json
import re
import time

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from langchain_core.callbacks.manager import dispatch_custom_event

from stock_agent.utils.constants import DEFAULT_MODEL, LIGHT_MODEL, ERROR_MESSAGES
from stock_agent.utils.state import GraphState
from stock_agent.prompts.company import COMPANY_SYNTHESIS_PROMPT
from stock_agent.tools.yfinance_tools import get_company_data
from stock_agent.tools.ticker_mapping import TICKER_MAP
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)
_timing_logger = get_logger("timing")


# ── LLM 티커 추론 (TICKER_MAP에 없는 기업용) ──

class TickerResult(BaseModel):
    """LLM 티커 추론 결과"""
    ticker: str = Field(description="주식 티커 (예: AAPL, 005930.KS). 모르면 UNKNOWN")
    company_name: str = Field(description="기업명 (예: Apple Inc., 삼성전자)")


_TICKER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a stock ticker resolver. Extract the company name from the question "
        "and return its ticker symbol.\n"
        "- US stocks: ticker like AAPL, TSLA, NVDA, PANW\n"
        "- Korean stocks: 6-digit code + .KS or .KQ (e.g., 005930.KS)\n"
        "- Use conversation context to resolve pronouns like '그 회사', '이 회사'\n"
        "- If unknown, set ticker to 'UNKNOWN'\n"
        "- Return only ONE company (the primary one asked about)"
    )),
    ("human", "{question}"),
])

_ticker_llm = ChatOpenAI(model=LIGHT_MODEL, temperature=0)
_synthesis_llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=0)


# ── 헬퍼 함수 ──

def _extract_current_question(question: str) -> str:
    """보강된 질문에서 [현재 질문] 부분만 추출합니다."""
    marker = "[현재 질문]"
    if marker in question:
        after = question.split(marker, 1)[1]
        end_marker = "위 대화 맥락을"
        if end_marker in after:
            after = after.split(end_marker, 1)[0]
        return after.strip()
    return question


_ACTION_PATTERNS = [
    '분석해줘', '분석해', '분석', '시가총액 알려줘', '시가총액',
    '주가 알려줘', '주가', '뉴스 알려줘', '뉴스', '어때?', '어때',
    '알려줘', '해줘', '보여줘', '현재가', '재무', '매출', '최근', '오늘',
    'per', 'pbr', 'eps', '배당', '차트',
]


def _extract_user_company_name(question: str) -> str:
    """질문에서 사용자가 입력한 기업명 부분을 추출합니다."""
    current_q = _extract_current_question(question)
    candidate = current_q.strip().lower()
    for p in sorted(_ACTION_PATTERNS, key=len, reverse=True):
        candidate = candidate.replace(p, '').strip()
    return candidate or current_q.strip()


def _try_code_resolve(question: str) -> str | None:
    """코드 기반 티커 해석. TICKER_MAP 매칭 → 영문 티커 → 한국 종목코드."""
    current_q = _extract_current_question(question)
    q = current_q.strip().lower()

    # TICKER_MAP 키 매칭 (긴 이름 우선 → 부분 매칭 방지)
    for name in sorted(TICKER_MAP.keys(), key=len, reverse=True):
        if name in q:
            return TICKER_MAP[name]

    # 영문 티커 패턴 (2~5자 영문)
    m = re.search(r'\b([A-Za-z]{2,5})\b', current_q)
    if m:
        return m.group(1).upper()

    # 6자리 한국 종목코드
    m = re.search(r'\b(\d{6})\b', current_q)
    if m:
        return f"{m.group(1)}.KS"

    return None


# ── 메인 노드 ──

def company_node(state: GraphState) -> dict:
    """기업분석 체인: 티커 해석 → 데이터 수집 → LLM 합성."""
    question = state["question"]
    t_node = time.perf_counter()

    try:
        # Step 1: 코드 기반 티커 해석
        t0 = time.perf_counter()
        ticker = _try_code_resolve(question)
        _timing_logger.info("[company:1 code-resolve] %.1fms → %s", (time.perf_counter() - t0) * 1000, ticker or "MISS")

        # Step 2: 실패 시 LLM 추론 (TICKER_MAP에 없는 기업 대응)
        if not ticker:
            logger.info("코드 기반 해석 실패, LLM 추론 시작")
            t0 = time.perf_counter()
            chain = _TICKER_PROMPT | _ticker_llm.with_structured_output(TickerResult)
            result = chain.invoke({"question": question})
            _timing_logger.info("[company:2 ticker-LLM] %.0fms → %s", (time.perf_counter() - t0) * 1000, result.ticker)
            ticker = result.ticker
            if ticker == "UNKNOWN":
                name = _extract_user_company_name(question)
                return {
                    "draft_answer": f"'{name}'에 해당하는 기업을 찾을 수 없습니다.",
                    "agent_results": {"source_data": "", "agent": "company"},
                }

        logger.info("티커 해석 완료: %s", ticker)

        # Step 3: yfinance 데이터 수집 (info 1회 호출)
        t0 = time.perf_counter()
        data = get_company_data(ticker)
        _timing_logger.info("[company:3 yfinance] %.0fms", (time.perf_counter() - t0) * 1000)
        source_json = json.dumps(data, ensure_ascii=False, default=str)

        # 에러 → 유효하지 않은 티커
        if "error" in data:
            return {
                "draft_answer": f"'{ticker}' 기업 데이터를 가져올 수 없습니다. 기업명을 확인해 주세요.",
                "agent_results": {"source_data": source_json, "data_dict": data, "agent": "company"},
            }

        # Step 3.5: 주가 데이터 + 회사소개 + 후속질문을 먼저 클라이언트에 전송 (LLM 합성 전)
        from stock_agent.agent import extract_company_price_data
        price_data = extract_company_price_data(data)
        if price_data:
            # Pydantic 모델을 dict로 변환
            event_payload = {}
            if price_data.get("ticker_info"):
                event_payload["ticker_info"] = price_data["ticker_info"].model_dump(exclude_none=True)
            if price_data.get("price"):
                event_payload["price"] = price_data["price"].model_dump(exclude_none=True)
            if price_data.get("key_metrics"):
                event_payload["key_metrics"] = [m.model_dump() for m in price_data["key_metrics"]]

            # 후속질문: 회사명 기반 기본 질문
            short_name = data["overview"].get("company_name", "").split("(")[0].strip() or ticker
            event_payload["follow_up"] = [
                f"{short_name} 최근 뉴스",
                f"{short_name} 배당금 정보",
                f"{short_name} 경쟁사 비교",
            ]

            dispatch_custom_event("company_data", event_payload)

        # Step 4: LLM 합성 (GPT-4o 1회, .stream()으로 astream_events 토큰 캡처)
        prompt = ChatPromptTemplate.from_messages([
            ("system", COMPANY_SYNTHESIS_PROMPT),
            ("human", "질문: {question}\n\n수집된 데이터:\n{data}"),
        ])
        t0 = time.perf_counter()
        chunks = []
        for chunk in (prompt | _synthesis_llm).stream(
            {"question": question, "data": source_json},
            config={"tags": ["synthesis"]},
        ):
            token = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if token:
                chunks.append(token)
        draft = "".join(chunks)
        _timing_logger.info("[company:4 synthesis-LLM] %.0fms", (time.perf_counter() - t0) * 1000)
        _timing_logger.info("[company TOTAL] %.0fms", (time.perf_counter() - t_node) * 1000)

        return {
            "draft_answer": draft,
            "agent_results": {"source_data": source_json, "data_dict": data, "agent": "company"},
        }

    except Exception as e:
        logger.error("company 체인 실패: %s", e, exc_info=True)
        return {
            "draft_answer": ERROR_MESSAGES["company_failed"],
            "agent_results": {"source_data": "", "agent": "company"},
        }



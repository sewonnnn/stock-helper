"""FastAPI 서버 진입점"""

import warnings
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

import asyncio
import json
import time
import uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import difflib

from stock_agent.agent import (
    graph, enrich_question, save_history,
    _extract_followups, _extract_company_intro,
    _filter_by_trusted_domains, _validate_urls,
    company_direct_response, news_direct_response,
    general_direct_response, advisor_direct_response,
    chat_direct_response,
)
from stock_agent.nodes.supervisor import question_router
from stock_agent.nodes.company import company_prepare, company_stream_synthesis
from stock_agent.nodes._search_chain import search_prepare, search_stream_synthesis, search_stream_fallback
from stock_agent.nodes.chat import chat_stream
from stock_agent.nodes.glossary import glossary_validated
from stock_agent.tools.tavily_tools import tavily_search_news, tavily_search_general, tavily_search_advisor
from stock_agent.prompts.news import NEWS_QUERY_PROMPT, NEWS_SYNTHESIS_PROMPT
from stock_agent.prompts.general import GENERAL_QUERY_PROMPT, GENERAL_SYNTHESIS_PROMPT
from stock_agent.prompts.advisor import ADVISOR_QUERY_PROMPT, ADVISOR_SYNTHESIS_PROMPT
from stock_agent.utils.schemas import StockResponse, NewsItem, TickerInfo, PriceInfo, Metric
from stock_agent.utils.constants import (
    DISCLAIMER, UNKNOWN_RESPONSE, ERROR_MESSAGES, MAX_QUESTION_LENGTH,
    TRUSTED_NEWS_DOMAINS, TRUSTED_ADVISOR_DOMAINS,
)
from stock_agent.tools.ticker_mapping import TICKER_MAP
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)
_timing_logger = get_logger("timing")

app = FastAPI(title="주식 멘토 AI", version="1.0.0")

# CORS 설정 — Vercel 프론트엔드에서 Render 백엔드 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://stock-helper-henna.vercel.app",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=MAX_QUESTION_LENGTH)
    thread_id: str | None = None  # 대화 스레드 ID (없으면 새로 생성)


class ChatResponse(BaseModel):
    success: bool
    data: StockResponse | None = None
    route: str | None = None
    thread_id: str | None = None  # 프론트에서 이후 요청에 재사용
    error: str | None = None


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Pydantic 검증 실패 시 사용자 친화적 에러 반환"""
    return JSONResponse(
        status_code=200,
        content={
            "success": False,
            "error": ERROR_MESSAGES["input_too_long"],
            "data": None,
            "route": None,
            "thread_id": None,
        },
    )


def _check_company_typo(question: str) -> StockResponse | None:
    """기업명 오타를 빠르게 감지하여 유사 기업을 추천합니다. LLM 호출 없이 즉시 반환."""
    q = question.strip().lower()

    # 금융 용어/질문 패턴이 포함되어 있으면 오타 감지 스킵 (그래프에서 처리)
    _FINANCE_TERMS = {
        'etf', '공매도', '배당', '배당금', '인플레이션', '디플레이션', '금리',
        '채권', '선물', '옵션', '펀드', '인덱스', '포트폴리오', '분산투자',
        '적립식', '거치식', '증거금', '레버리지', '공모주', '우선주', '보통주',
        '시가총액', '유상증자', '무상증자', '액면분할', '자사주', '코스피',
        '코스닥', '나스닥', 's&p500', '다우존스', '환율', '원달러',
    }
    _QUESTION_SUFFIXES = {'뭐야', '뭐야?', '뭔가요', '뭔가요?', '란?', '란', '이란',
                          '종류', '장점', '단점', '위험', '위험성', '경향', '특징',
                          '차이', '비교', '추천', '시작', '방법', '전략'}
    if any(term in q for term in _FINANCE_TERMS):
        return None
    if any(q.endswith(s) for s in _QUESTION_SUFFIXES):
        return None
    if len(q) <= 2:
        return None

    # 액션 키워드 제거하여 기업명 후보 추출
    action_patterns = [
        '분석해줘', '분석해', '분석', '시가총액 알려줘', '시가총액',
        '주가 알려줘', '주가', '뉴스 알려줘', '뉴스', '어때?', '어때',
        '알려줘', '해줘', '보여줘', '현재가', '재무', '매출', '최근', '오늘',
        'per', 'pbr', 'eps', '배당', '차트',
    ]
    candidate = q
    for p in sorted(action_patterns, key=len, reverse=True):
        candidate = candidate.replace(p, '').strip()

    if not candidate or len(candidate) < 2:
        return None

    # candidate에 질문 패턴이 남아있으면 기업명이 아님
    _QUESTION_REMNANTS = {'뭐야', '뭔가', '뭐', '란?', '란', '이란', '인가', '인가요',
                          '종류', '장점', '단점', '위험', '경향', '특징', '차이', '비교'}
    if any(r in candidate for r in _QUESTION_REMNANTS):
        return None

    # 정확히 매칭 → 오타 아님, 정상 진행
    if candidate in TICKER_MAP:
        return None

    # candidate 안에 알려진 기업명이 포함되어 있으면 → 오타 아님, 그래프에서 처리
    # (예: "애플 지표", "삼성전자의 경쟁사", "테슬라 최근 실적")
    for name in TICKER_MAP:
        if name in candidate:
            return None

    # 영문 대문자 1-5자 (티커 형태) → 정상 진행
    if candidate.isascii() and candidate.upper().isalpha() and 1 <= len(candidate) <= 5:
        return None

    # 유사 매칭 (TICKER_MAP에 없지만 비슷한 이름이 있는 경우 → 오타 추천)
    close_matches = difflib.get_close_matches(candidate, TICKER_MAP.keys(), n=3, cutoff=0.4)
    if close_matches:
        followups = [f"{m} 분석해줘" for m in close_matches[:3]]
        return StockResponse(
            insight=f"'{candidate}'에 해당하는 기업을 찾지 못했습니다. 혹시 아래 기업을 찾으셨나요?",
            sources=[],
            confidence="낮음",
            follow_up=followups,
        )

    # TICKER_MAP에 없고 유사 매칭도 없으면 → 그래프에서 처리 (yfinance에 있을 수 있음)
    return None


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """사용자 질문을 처리하여 구조화된 응답을 반환합니다."""
    thread_id = request.thread_id or str(uuid.uuid4())

    if not request.question.strip():
        return ChatResponse(
            success=False,
            error="질문을 입력해 주세요.",
            thread_id=thread_id,
        )

    logger.info("질문 수신 [thread=%s]: %s", thread_id, request.question[:100])

    # 기업명 오타 빠른 감지 — LLM 호출 없이 즉시 추천 반환
    typo_response = _check_company_typo(request.question)
    logger.info("오타 감지 결과: %s", typo_response)
    if typo_response:
        return ChatResponse(
            success=True, data=typo_response, route="company", thread_id=thread_id
        )

    try:
        t_total = time.perf_counter()
        result = graph.invoke(
            {
                "question": request.question,
                "chat_history": [{"role": "user", "content": request.question}],
                "retry_count": 0,
                "agent_results": {},
                "draft_answer": "",
                "validated": False,
                "validation_reason": "",
                "hallucinated_parts": [],
                "route": "",
                "final_answer": None,
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        final_answer = result.get("final_answer")
        route = result.get("route", "")
        _timing_logger.info("[graph TOTAL] %.0fms (route=%s)", (time.perf_counter() - t_total) * 1000, route)
        if final_answer:
            return ChatResponse(
                success=True, data=final_answer, route=route, thread_id=thread_id
            )
        else:
            return ChatResponse(
                success=True,
                data=StockResponse(
                    insight=UNKNOWN_RESPONSE,
                    confidence="낮음",
                    disclaimer=DISCLAIMER,
                ),
                thread_id=thread_id,
            )
    except Exception as e:
        logger.error("graph.invoke 실패: %s", e, exc_info=True)
        return ChatResponse(
            success=False,
            error=ERROR_MESSAGES["server_error"],
            thread_id=thread_id,
        )


def _sse_event(event: str, data: dict) -> str:
    """SSE 형식 문자열 생성."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_company_data_event(data_dict: dict) -> dict:
    """yfinance data_dict에서 프론트용 구조화 데이터를 구성합니다."""
    from stock_agent.agent import _level_threshold
    overview = data_dict.get("overview", {})
    valuation = data_dict.get("valuation", {})

    result = {}
    # ticker_info
    result["ticker_info"] = {
        "ticker": overview.get("ticker", ""),
        "company_name": overview.get("company_name", "") or overview.get("ticker", ""),
        "sector": overview.get("sector"),
        "industry": overview.get("industry"),
    }
    # price
    cur = overview.get("current_price")
    prev = overview.get("previous_close")
    if cur is not None and prev is not None:
        result["price"] = {
            "current_price": cur,
            "previous_close": prev,
            "change": overview.get("change") or 0.0,
            "change_percent": overview.get("change_percent") or 0.0,
            "currency": overview.get("currency", "USD"),
            "krw_price": overview.get("krw_price"),
            "usd_krw_rate": overview.get("usd_krw_rate"),
            "market_cap": overview.get("market_cap"),
            "market_cap_tier": overview.get("market_cap_tier"),
        }
    # key_metrics (PER only)
    per = valuation.get("per")
    if per is not None:
        result["key_metrics"] = [{"name": "PER", "value": f"{per:.2f}", "level": _level_threshold(per, 15, 25)}]

    return result


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """SSE 스트리밍 응답 엔드포인트."""
    thread_id = request.thread_id or str(uuid.uuid4())

    if not request.question.strip():
        async def empty_gen():
            yield _sse_event("done", {"error": "질문을 입력해 주세요."})
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    logger.info("[stream] 질문 수신 [thread=%s]: %s", thread_id, request.question[:100])

    # 기업명 오타 빠른 감지
    typo_response = _check_company_typo(request.question)
    if typo_response:
        async def typo_gen():
            yield _sse_event("meta", {"route": "company", "thread_id": thread_id})
            yield _sse_event("done", {
                "insight": typo_response.insight,
                "follow_up": typo_response.follow_up or [],
            })
        return StreamingResponse(typo_gen(), media_type="text/event-stream")

    async def event_generator():
        try:
            # Step 1: enrich question (맥락 보강)
            state = {
                "question": request.question,
                "chat_history": [{"role": "user", "content": request.question}],
            }
            enriched = await asyncio.to_thread(enrich_question, state)
            question = enriched.get("question", request.question)

            # Step 2: supervisor routing
            route_result = await asyncio.to_thread(question_router.invoke, {"question": question})
            route = route_result.datasource
            logger.info("[stream] 라우팅: %s", route)

            yield _sse_event("meta", {"route": route, "thread_id": thread_id})

            # Step 3+4+5: 라우트별 데이터 수집 + 스트리밍 합성
            full_text = ""
            prep = None

            if route == "company":
                # 데이터 수집 (블로킹 → 스레드 위임)
                prep = await asyncio.to_thread(company_prepare, question)
                if prep["error"]:
                    yield _sse_event("chunk", {"text": prep["error"]})
                    yield _sse_event("done", {"follow_up": []})
                    return

                # 구조화 데이터 전송
                data_event = _build_company_data_event(prep["data_dict"])
                yield _sse_event("data", data_event)

                # LLM 합성 스트리밍
                for chunk in company_stream_synthesis(question, prep["source_json"]):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_text += token
                        yield _sse_event("chunk", {"text": token})

            elif route == "news":
                prep = await asyncio.to_thread(search_prepare, question, NEWS_QUERY_PROMPT, tavily_search_news, TRUSTED_NEWS_DOMAINS)
                if prep.get("error") or prep.get("empty"):
                    yield _sse_event("chunk", {"text": "최근 관련 뉴스를 찾을 수 없습니다."})
                    yield _sse_event("done", {"follow_up": []})
                    return

                # 뉴스 항목 데이터 전송
                from urllib.parse import urlparse
                news_list = []
                for item in prep["news_items"]:
                    if item.get("title") and item.get("url"):
                        domain = urlparse(item["url"]).netloc.replace("www.", "")
                        news_list.append({"title": item["title"], "source": domain, "url": item["url"]})
                yield _sse_event("data", {"news": news_list})

                # LLM 합성 스트리밍
                for chunk in search_stream_synthesis(question, prep["source_data"], NEWS_SYNTHESIS_PROMPT):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_text += token
                        yield _sse_event("chunk", {"text": token})

            elif route == "general":
                prep = await asyncio.to_thread(search_prepare, question, GENERAL_QUERY_PROMPT, tavily_search_general, TRUSTED_NEWS_DOMAINS)
                if prep.get("empty") and not prep.get("error"):
                    # 검색 결과 없으면 LLM 자체 지식으로 폴백하지 않음
                    yield _sse_event("chunk", {"text": "관련 정보를 찾을 수 없습니다."})
                    yield _sse_event("done", {"follow_up": []})
                    return

                for chunk in search_stream_synthesis(question, prep["source_data"], GENERAL_SYNTHESIS_PROMPT):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_text += token
                        yield _sse_event("chunk", {"text": token})

            elif route == "advisor":
                prep = await asyncio.to_thread(search_prepare, question, ADVISOR_QUERY_PROMPT, tavily_search_advisor, TRUSTED_ADVISOR_DOMAINS)
                if prep.get("empty") and not prep.get("error"):
                    # advisor는 fallback 지원
                    for chunk in search_stream_fallback(question, ADVISOR_SYNTHESIS_PROMPT):
                        token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        if token:
                            full_text += token
                            yield _sse_event("chunk", {"text": token})
                else:
                    for chunk in search_stream_synthesis(question, prep["source_data"], ADVISOR_SYNTHESIS_PROMPT):
                        token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        if token:
                            full_text += token
                            yield _sse_event("chunk", {"text": token})

            elif route == "chat":
                for chunk in chat_stream(question):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_text += token
                        yield _sse_event("chunk", {"text": token})

            elif route == "glossary":
                gloss_result = await asyncio.to_thread(glossary_validated, question)
                if gloss_result["fallback"]:
                    # RAG 실패 → general 폴백
                    route = "general"
                    yield _sse_event("meta", {"route": "general", "thread_id": thread_id})
                    prep = await asyncio.to_thread(search_prepare, question, GENERAL_QUERY_PROMPT, tavily_search_general, TRUSTED_NEWS_DOMAINS)
                    if prep.get("empty") and not prep.get("error"):
                        yield _sse_event("chunk", {"text": "관련 정보를 찾을 수 없습니다."})
                        yield _sse_event("done", {"follow_up": []})
                        return
                    for chunk in search_stream_synthesis(question, prep["source_data"], GENERAL_SYNTHESIS_PROMPT):
                        token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        if token:
                            full_text += token
                            yield _sse_event("chunk", {"text": token})
                else:
                    # 검증 완료된 답변을 단어 단위로 흘려보내기 (타이핑 효과)
                    validated_text = gloss_result["text"]
                    words = validated_text.split(' ')
                    for i, word in enumerate(words):
                        token = word if i == 0 else ' ' + word
                        full_text += token
                        yield _sse_event("chunk", {"text": token})
                        await asyncio.sleep(0.03)

            else:
                # 알 수 없는 라우트 → general로 폴백
                yield _sse_event("chunk", {"text": UNKNOWN_RESPONSE})
                yield _sse_event("done", {"follow_up": []})
                return

            # Step 6: 후처리 — follow_up, company_intro 추출
            clean_text, followups = _extract_followups(full_text)
            done_data = {"follow_up": followups}

            if route == "company":
                clean_text, company_intro = _extract_company_intro(clean_text)
                if company_intro:
                    done_data["company_intro"] = company_intro

            # 출처 URL (news, general, advisor)
            if route in ("news", "general", "advisor"):
                source_urls = prep.get("source_urls", []) if prep else []
                if source_urls:
                    if route == "news":
                        trusted_urls = _filter_by_trusted_domains(source_urls, TRUSTED_NEWS_DOMAINS)
                    elif route == "advisor":
                        trusted_urls = _filter_by_trusted_domains(source_urls, TRUSTED_ADVISOR_DOMAINS)
                    else:
                        trusted_urls = source_urls  # general은 이미 필터 완료
                    done_data["sources"] = await asyncio.to_thread(_validate_urls, trusted_urls)

            # clean_text (follow_up, company_intro 제거 후) 전달
            done_data["clean_insight"] = clean_text

            yield _sse_event("done", done_data)

        except asyncio.CancelledError:
            logger.info("[stream] 클라이언트 연결 끊김 (CancelledError)")
        except Exception as e:
            logger.error("[stream] 오류: %s", e, exc_info=True)
            try:
                yield _sse_event("error", {"message": ERROR_MESSAGES["server_error"]})
            except Exception:
                pass  # 연결 끊긴 경우 무시

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """프론트엔드 HTML 반환"""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

"""FastAPI 서버 진입점"""

import warnings
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

import asyncio
import json
import uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import difflib

from stock_agent.agent import graph
from stock_agent.utils.schemas import StockResponse
from stock_agent.utils.constants import (
    UNKNOWN_RESPONSE, ERROR_MESSAGES, MAX_QUESTION_LENGTH,
)
from stock_agent.tools.ticker_mapping import TICKER_MAP
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)

app = FastAPI(title="주식 멘토 AI", version="1.0.0")

# CORS 설정 — Vercel 프론트엔드에서 Render 백엔드 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://stock-helper.*\.vercel\.app",
    allow_origins=[
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=MAX_QUESTION_LENGTH)
    thread_id: str | None = None  # 대화 스레드 ID (없으면 새로 생성)


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


# ── SSE 스트리밍 (LangGraph astream_events) ──

# 합성 LLM 토큰을 스트리밍할 노드 목록
_STREAMING_NODES = {"company", "news", "general", "advisor", "chat"}


def _sse_event(event: str, data: dict) -> str:
    """SSE 형식 문자열 생성."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(request: ChatRequest):
    """LangGraph astream_events 기반 SSE 스트리밍 엔드포인트."""
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
            yield _sse_event("chunk", {"text": typo_response.insight})
            done_data = typo_response.model_dump(exclude_none=True)
            yield _sse_event("done", done_data)
        return StreamingResponse(typo_gen(), media_type="text/event-stream")

    async def event_generator():
        route = None
        final_answer = None

        input_state = {
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
        }
        config = {"configurable": {"thread_id": thread_id}}

        next_task = None
        try:
            aiter = graph.astream_events(input_state, config, version="v2").__aiter__()
            next_task = asyncio.ensure_future(aiter.__anext__())

            while True:
                # 10초마다 heartbeat — 이벤트 흐름과 무관하게 전송
                done, _ = await asyncio.wait({next_task}, timeout=10)
                if not done:
                    yield ": heartbeat\n\n"
                    continue

                try:
                    event = next_task.result()
                except StopAsyncIteration:
                    break

                next_task = asyncio.ensure_future(aiter.__anext__())

                kind = event["event"]
                metadata = event.get("metadata", {})
                node_name = metadata.get("langgraph_node", "")

                # 라우트 감지: supervisor 노드 완료 시
                if kind == "on_chain_end" and node_name == "supervisor" and not route:
                    output = event.get("data", {}).get("output")
                    if isinstance(output, dict) and "route" in output:
                        route = output["route"]
                    elif hasattr(output, "datasource"):
                        route = output.datasource
                    elif hasattr(output, "route"):
                        route = output.route
                    if route:
                        yield _sse_event("meta", {"route": route, "thread_id": thread_id})

                # company 주가 데이터 선행 전송
                elif kind == "on_custom_event" and event.get("name") == "company_data":
                    yield _sse_event("data", event.get("data", {}))

                # 합성 LLM 토큰 스트리밍 (synthesis 태그가 있는 호출만)
                elif kind == "on_chat_model_stream" and node_name in _STREAMING_NODES:
                    tags = event.get("tags", [])
                    if "synthesis" not in tags:
                        continue
                    chunk_data = event.get("data", {}).get("chunk")
                    if chunk_data:
                        token = chunk_data.content if hasattr(chunk_data, 'content') else ""
                        if token:
                            yield _sse_event("chunk", {"text": token})

                # response 노드 완료 시 final_answer 캡처
                elif kind == "on_chain_end" and node_name.endswith("_response"):
                    output = event.get("data", {}).get("output", {})
                    fa = output.get("final_answer")
                    if fa:
                        final_answer = fa

            # 그래프 완료 — done 이벤트 전송
            if final_answer:
                done_data = final_answer.model_dump(exclude_none=True) if hasattr(final_answer, 'model_dump') else {}
            else:
                done_data = {"insight": UNKNOWN_RESPONSE}

            yield _sse_event("done", done_data)

        except Exception as e:
            logger.error("[stream] 오류: %s", e, exc_info=True)
            try:
                yield _sse_event("error", {"message": ERROR_MESSAGES["server_error"]})
            except Exception:
                pass
        finally:
            if next_task and not next_task.done():
                next_task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# 정적 파일 — /static/ 경로와 루트 경로 모두 서빙 (Vercel·로컬 호환)
app.mount("/static", StaticFiles(directory="static"), name="static_sub")


@app.get("/")
async def root():
    """프론트엔드 HTML 반환"""
    return FileResponse("static/index.html")


@app.get("/{filename:path}")
async def static_root(filename: str):
    """루트 경로에서도 정적 파일 서빙 (./style.css → /style.css)"""
    import os
    filepath = os.path.join("static", filename)
    if os.path.isfile(filepath):
        return FileResponse(filepath)
    return JSONResponse(status_code=404, content={"detail": "Not found"})


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

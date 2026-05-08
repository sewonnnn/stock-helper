"""FastAPI 서버 진입점"""

import warnings
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

import uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import difflib

from stock_agent.agent import graph
from stock_agent.utils.schemas import StockResponse
from stock_agent.tools.ticker_mapping import TICKER_MAP
from stock_agent.utils.constants import (
    DISCLAIMER, UNKNOWN_RESPONSE, ERROR_MESSAGES, MAX_QUESTION_LENGTH,
)
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)

app = FastAPI(title="주식 멘토 AI", version="1.0.0")


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


# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """프론트엔드 HTML 반환"""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

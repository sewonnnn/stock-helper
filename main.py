"""FastAPI 서버 진입점"""

import warnings
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

import uuid
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from stock_agent.agent import graph
from stock_agent.utils.schemas import StockResponse
from stock_agent.utils.constants import DISCLAIMER, UNKNOWN_RESPONSE

app = FastAPI(title="주식 멘토 AI", version="1.0.0")


class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = None  # 대화 스레드 ID (없으면 새로 생성)


class ChatResponse(BaseModel):
    success: bool
    data: StockResponse | None = None
    route: str | None = None
    thread_id: str | None = None  # 프론트에서 이후 요청에 재사용
    error: str | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """사용자 질문을 처리하여 구조화된 응답을 반환합니다."""
    thread_id = request.thread_id or str(uuid.uuid4())

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
                    인사이트=UNKNOWN_RESPONSE,
                    확신도="낮음",
                    면책문구=DISCLAIMER,
                ),
                thread_id=thread_id,
            )
    except Exception as e:
        return ChatResponse(success=False, error=str(e), thread_id=thread_id)


# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """프론트엔드 HTML 반환"""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

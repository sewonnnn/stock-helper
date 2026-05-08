"""체인 단위 테스트 10개 — 실제 API 호출, mock 없음.

실행: pytest tests/test_chains.py -v
"""

from pprint import pprint

from dotenv import load_dotenv
load_dotenv()

from stock_agent.chains.generation import generation_chain
from stock_agent.chains.hallucination_grader import GradeHallucinations, hallucination_grader
from stock_agent.chains.retrieval_grader import GradeDocuments, retrieval_grader
from stock_agent.chains.answer_grader import GradeAnswer, answer_grader
from stock_agent.nodes.supervisor import question_router, RouteQuery
from stock_agent.tools.rag_tools import retriever


# --- Document Relevance: 문서 관련성 판단 ---

def test_retrieval_grader_answer_yes() -> None:
    """관련 있는 질문 → yes"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    res: GradeDocuments = retrieval_grader.invoke(
        {"question": question, "document": docs[0].page_content}
    )
    assert res.binary_score == "yes"


def test_retrieval_grader_answer_no() -> None:
    """무관한 질문 → no"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    res: GradeDocuments = retrieval_grader.invoke(
        {"question": "피자 만드는 법", "document": docs[0].page_content}
    )
    assert res.binary_score == "no"


# --- 답변 생성 ---

def test_generation_chain() -> None:
    """답변 생성 동작 확인"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    generation = generation_chain.invoke({"context": docs, "question": question})
    pprint(generation)
    assert generation
    assert "PER" in generation


# --- Groundedness: 할루시네이션 판단 ---

def test_hallucination_grader_answer_yes() -> None:
    """문서 기반 답변 → True (근거 있음)"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    generation = generation_chain.invoke({"context": docs, "question": question})
    res: GradeHallucinations = hallucination_grader.invoke(
        {"documents": docs, "generation": generation}
    )
    assert res.binary_score


def test_hallucination_grader_answer_no() -> None:
    """무관 답변 → False (근거 없음)"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    res: GradeHallucinations = hallucination_grader.invoke(
        {"documents": docs, "generation": "피자를 만들려면 도우부터 시작합니다"}
    )
    assert not res.binary_score


# --- Answer Helpfulness: 답변 유용성 판단 ---

def test_answer_grader_answer_yes() -> None:
    """질문에 답하는 응답 → yes"""
    question = "PER이 뭐야?"
    docs = retriever.invoke(question)
    generation = generation_chain.invoke({"context": docs, "question": question})
    res: GradeAnswer = answer_grader.invoke(
        {"question": question, "generation": generation}
    )
    assert res.binary_score == "yes"


def test_answer_grader_answer_no() -> None:
    """질문에 답 안 하는 응답 → no"""
    question = "PER이 뭐야?"
    res: GradeAnswer = answer_grader.invoke(
        {"question": question, "generation": "오늘 날씨가 좋습니다"}
    )
    assert res.binary_score == "no"


# --- 슈퍼바이저 라우팅 ---

def test_router_to_company() -> None:
    """기업 질문 → company"""
    res: RouteQuery = question_router.invoke({"question": "애플 시가총액"})
    assert res.datasource == "company"


def test_router_to_news() -> None:
    """뉴스 질문 → news"""
    res: RouteQuery = question_router.invoke({"question": "테슬라 오늘 뉴스"})
    assert res.datasource == "news"


def test_router_to_glossary() -> None:
    """용어 질문 → glossary"""
    res: RouteQuery = question_router.invoke({"question": "공매도가 뭐야?"})
    assert res.datasource == "glossary"

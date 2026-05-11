import os

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from stock_agent.utils.constants import EMBEDDING_MODEL, PINECONE_INDEX_NAME
from stock_agent.utils.logging_config import get_logger

logger = get_logger(__name__)


def get_retriever(k: int = 1):
    """Pinecone 벡터 스토어에서 retriever를 생성합니다."""
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PineconeVectorStore(
        index_name=os.getenv("PINECONE_INDEX_NAME", PINECONE_INDEX_NAME),
        embedding=embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})


class _FallbackRetriever:
    """Pinecone 초기화 실패 시 빈 결과를 반환하는 폴백 리트리버."""

    def invoke(self, query: str) -> list:
        logger.warning("폴백 리트리버 사용 중 (Pinecone 미연결)")
        return []


# 모듈 로드 시 retriever 인스턴스 생성
try:
    retriever = get_retriever()
except Exception as e:
    logger.error("Pinecone 초기화 실패, 폴백 리트리버 사용: %s", e)
    retriever = _FallbackRetriever()

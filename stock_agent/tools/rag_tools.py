import os

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from stock_agent.utils.constants import EMBEDDING_MODEL, PINECONE_INDEX_NAME


def get_retriever(k: int = 3):
    """Pinecone 벡터 스토어에서 retriever를 생성합니다."""
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PineconeVectorStore(
        index_name=os.getenv("PINECONE_INDEX_NAME", PINECONE_INDEX_NAME),
        embedding=embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})


# 모듈 로드 시 retriever 인스턴스 생성
retriever = get_retriever()

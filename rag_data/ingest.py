"""
Pinecone 인덱싱 스크립트 (1회 실행)

사용법:
    cd ~/stock-helper
    source venv/bin/activate
    python3 rag_data/ingest.py
"""

import os
import glob

from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-small"
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "stock-glossary")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "documents")


def create_index_if_not_exists():
    """Pinecone 인덱스가 없으면 생성합니다."""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    existing = [idx.name for idx in pc.list_indexes()]

    if INDEX_NAME not in existing:
        print(f"인덱스 '{INDEX_NAME}' 생성 중...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=1536,  # text-embedding-3-small 차원
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print(f"인덱스 '{INDEX_NAME}' 생성 완료!")
    else:
        print(f"인덱스 '{INDEX_NAME}' 이미 존재합니다.")


def load_documents():
    """마크다운 용어집 파일들을 로드합니다."""
    md_files = glob.glob(os.path.join(DOCS_DIR, "*.md"))
    documents = []

    for filepath in md_files:
        loader = TextLoader(filepath, encoding="utf-8")
        docs = loader.load()
        # 파일명에서 용어 이름 추출하여 메타데이터에 추가
        term_name = os.path.splitext(os.path.basename(filepath))[0]
        for doc in docs:
            doc.metadata["term"] = term_name
            doc.metadata["source"] = filepath
        documents.extend(docs)

    print(f"총 {len(documents)}개 문서 로드 완료")
    return documents


def split_documents(documents):
    """문서를 청크로 분할합니다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n## ", "\n# ", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(documents)
    print(f"총 {len(chunks)}개 청크로 분할 완료")
    return chunks


def ingest(chunks):
    """청크를 Pinecone에 인덱싱합니다."""
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = PineconeVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        index_name=INDEX_NAME,
    )
    print(f"Pinecone 인덱싱 완료! (인덱스: {INDEX_NAME})")
    return vectorstore


def main():
    print("=== Pinecone 인제스트 시작 ===")
    create_index_if_not_exists()
    documents = load_documents()
    chunks = split_documents(documents)
    ingest(chunks)
    print("=== 완료 ===")


if __name__ == "__main__":
    main()

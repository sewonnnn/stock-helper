from pinecone import Pinecone
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
import os

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# 인덱스 통계
index = pc.Index("stock-glossary")
print("=== Index Stats ===")
print(index.describe_index_stats())

# 검색 테스트
print("\n=== Search Test: 'PER이 뭐야?' ===")
query_vec = embeddings.embed_query("PER이 뭐야?")
results = index.query(vector=query_vec, top_k=3, include_metadata=True)

for i, match in enumerate(results['matches'], 1):
    print(f"\n{i}. Score: {match['score']:.4f}")
    print(f"   Metadata: {match['metadata']}")
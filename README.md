# 주식 도우미 AI

> 주식 초보자를 위한 AI 어시스턴트. LangGraph 기반 멀티 에이전트 시스템.

---

## 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 주제 | 주식 초보자를 위한 AI 어시스턴트 |
| 대상 시장 | 미국 주식 (한국 주식 일부 지원) |
| 응답 언어 | 한국어 |
| 배포 | 백엔드: Render / 프론트엔드: Vercel |

**제공 기능**

- 기업 정보 조회 (시가총액, 가격, 재무지표) -- 시각화 카드 형태로 제공
- 최신 뉴스 및 시장 분위기 분석
- 주식 용어/개념 설명 (Self-RAG 적용)
- 일반 시장/트렌드 질문 응답
- 맞춤형 투자 안내 (연령/자산 기반)
- 대화 맥락 유지 (후속 질문 자동 인식)
- SSE 스트리밍 실시간 응답
- 주식/금융 무관 질문 자동 거부
- 출처 URL 신뢰 도메인 필터링
- 용어 하이라이트 (40+개 금융 용어 인라인 툴팁)

---

## 기술 스택

| 분류 | 도구 |
|---|---|
| 오케스트레이션 | LangGraph (커스텀 StateGraph) |
| LLM (답변 합성) | OpenAI GPT-4o |
| LLM (라우팅/판단/쿼리 생성) | OpenAI GPT-4o-mini |
| 기업 데이터 | yfinance |
| 웹 검색 | Tavily API |
| 벡터 DB | Pinecone |
| 임베딩 | OpenAI text-embedding-3-small |
| 추적/디버깅 | LangSmith |
| 백엔드 | FastAPI + Uvicorn (SSE 스트리밍) |
| 프론트엔드 | HTML + CSS + Vanilla JS |
| 출력 스키마 | Pydantic Structured Output |
| 체인 | LCEL (LangChain Expression Language) |
| 테스트 | pytest + pytest-asyncio |

---

## 아키텍처

```
[브라우저] ── SSE 스트리밍 ── POST /chat
     ↓
[FastAPI 서버] ── astream_events + heartbeat
     ↓
┌───────────────────────────────────────────────────────┐
│  LangGraph StateGraph                                 │
│                                                       │
│  [맥락 보강] ── 대명사/후속질문 자동 감지              │
│       ↓                                               │
│  [슈퍼바이저] ── 7개 라우트 분류                       │
│       ↓                                               │
│  ┌───┬───┬────┬────┬─────┬────┬────┐                  │
│  ↓   ↓   ↓    ↓    ↓     ↓    ↓                      │
│ 기업 뉴스 용어 일반 투자  대화 거부                    │
│  │   │    │    │   안내    │    │                      │
│  │   │    │    │    │     │    └→ 즉시 안내 반환       │
│  │   │    │    │    │     └→ LLM 1회 (맥락 기반)      │
│  │   │    │    └────┘                                 │
│  │   │    │    Tavily 검색 → LLM 합성                 │
│  │   │    └→ Pinecone RAG → 3단계 검증                │
│  │   └→ Tavily 검색 → LLM 합성                       │
│  └→ 코드 티커 해석 → yfinance → LLM 합성             │
│       ↓                                               │
│  [직통 응답] ── 각 노드가 StockResponse 직접 구성     │
│       ↓                                               │
│  [히스토리 저장] → END                                │
└───────────────────────────────────────────────────────┘
```

### 설계 원칙

- **체인 기반 노드**: 모든 노드가 LCEL 체인으로 구현 (LLM 호출 최소화)
- **직통 응답**: 별도 Responder LLM 없이 각 노드가 StockResponse를 직접 구성
- **SSE 스트리밍**: LLM 합성 토큰을 실시간으로 클라이언트에 전송
- **모델 분리**: 답변 합성은 GPT-4o, 판단/라우팅은 GPT-4o-mini로 비용 최적화
- **맥락 보강**: LLM으로 후속 질문 여부 판단 후, 필요 시 이전 대화 맥락 주입
- **Self-RAG**: glossary 노드에 Document Relevance / Groundedness / Answer Helpfulness 3단계 검증

---

## 노드 상세

### 슈퍼바이저 (supervisor)

사용자 질문을 7개 카테고리로 분류:

| 라우트 | 설명 | 예시 |
|---|---|---|
| `company` | 특정 기업의 가격/시총/재무지표 | "애플 분석해줘" |
| `news` | 특정 기업의 최신 뉴스 | "테슬라 최근 뉴스" |
| `glossary` | 주식 용어/개념 설명 | "PER이 뭐야?" |
| `general` | 일반 시장/트렌드/기업 분석 질문 | "요즘 인기 있는 주식?" |
| `advisor` | 맞춤형 투자 안내 (개인 맥락 포함) | "24살 월 50만원 투자 전략" |
| `chat` | 인사, 이전 답변에 대한 후속 질문 | "왜 그래?", "더 알려줘" |
| `reject` | 주식/금융과 무관한 질문 | "앰플 추천해줘" |

### 기업분석 (company)

체인으로 구현하여 LLM 호출 최소화:

1. **코드 기반 티커 해석**: TICKER_MAP 매칭 → 영문 티커 패턴 → 한국 종목코드
2. **LLM 티커 추론** (코드 실패 시): GPT-4o-mini로 티커 추론
3. **yfinance 데이터 수집**: `get_company_data()` 단일 호출
4. **주가 데이터 선행 전송**: LLM 합성 전에 가격/지표/후속질문을 SSE로 먼저 전송
5. **LLM 합성**: GPT-4o로 핵심 요약 생성 (스트리밍)

### 뉴스/일반/투자안내 (news, general, advisor)

공용 검색 체인 (`_search_chain.py`)으로 구현:

1. **검색 쿼리 생성**: GPT-4o-mini로 최적 검색어 생성 (현재 연도 자동 포함)
2. **Tavily 검색**: 신뢰 도메인 한정, 소셜미디어 제외
3. **LLM 합성**: GPT-4o로 검색 결과 기반 답변 생성 (스트리밍)

### 용어설명 (glossary) -- Self-RAG

Pinecone 검색 후 3단계 검증:

```
[질문] → [Pinecone 검색] → [Document Relevance: 관련성?]
                              ├─ No → general 폴백 (웹 검색)
                              └─ Yes → [답변 생성]
                                         → [Groundedness: 근거?]
                                           ├─ No → 재생성 (1회)
                                           └─ Yes → [Answer Helpfulness: 유용?]
                                                     ├─ No → 재생성 (1회)
                                                     └─ Yes → 최종 응답
```

---

## 폴더 구조

```
stock-helper/
├── main.py                          # FastAPI 진입점 (SSE 스트리밍)
├── requirements.txt
│
├── stock_agent/
│   ├── agent.py                     # 그래프 조립 + 직통 응답 함수들
│   │
│   ├── nodes/
│   │   ├── supervisor.py            # 7개 라우트 분류
│   │   ├── company.py               # 기업분석 체인
│   │   ├── news.py                  # 뉴스 검색 체인
│   │   ├── general.py               # 일반 질문 체인
│   │   ├── advisor.py               # 맞춤형 투자 안내 체인
│   │   ├── glossary.py              # 용어설명 Self-RAG
│   │   ├── chat.py                  # 대화형 후속 질문
│   │   └── _search_chain.py         # 검색 공용 체인 (news/general/advisor)
│   │
│   ├── chains/
│   │   ├── retrieval_grader.py      # Document Relevance
│   │   ├── hallucination_grader.py  # Groundedness
│   │   ├── answer_grader.py         # Answer Helpfulness
│   │   └── generation.py           # 용어 답변 생성 체인
│   │
│   ├── tools/
│   │   ├── yfinance_tools.py        # 주식 데이터 도구
│   │   ├── tavily_tools.py          # 웹 검색 도구
│   │   ├── rag_tools.py             # Pinecone RAG 검색
│   │   └── ticker_mapping.py        # 한↔영 종목명 매핑 (100+개)
│   │
│   ├── prompts/                     # 각 노드별 프롬프트
│   │
│   └── utils/
│       ├── state.py                 # GraphState 정의
│       ├── constants.py             # 상수 (모델, 도메인, 면책문구)
│       ├── schemas.py               # Pydantic 모델 (StockResponse)
│       └── logging_config.py        # 로깅 설정
│
├── rag_data/
│   ├── documents/                   # 한국어 용어집 마크다운 (26개)
│   └── ingest.py                    # Pinecone 인덱싱 스크립트
│
├── tests/
│   └── test_chains.py               # 체인 단위 테스트
│
└── static/
    ├── index.html                   # 메인 HTML
    ├── app.js                       # 채팅 로직, SSE 처리, DOM 렌더링
    ├── style.css                    # 스타일
    └── glossary.json                # 용어 하이라이트 데이터
```

---

## LLM 사용처

| 용도 | 모델 | 파일 |
|---|---|---|
| 라우팅 (질문 분류) | GPT-4o-mini | `nodes/supervisor.py` |
| 맥락 필요 판단 | GPT-4o-mini | `agent.py` |
| 티커 추론 (TICKER_MAP 미스 시) | GPT-4o-mini | `nodes/company.py` |
| 검색 쿼리 생성 (news/general/advisor) | GPT-4o-mini | `nodes/_search_chain.py` |
| 기업분석 합성 | GPT-4o | `nodes/company.py` |
| 뉴스/일반/투자안내 합성 | GPT-4o | `nodes/_search_chain.py` |
| 대화 후속 답변 | GPT-4o | `nodes/chat.py` |
| RAG 검증 (관련성/근거/유용성) | GPT-4o-mini | `chains/*.py` |
| RAG 답변 생성 | GPT-4o-mini | `chains/generation.py` |

---

## SSE 스트리밍

`POST /chat` 엔드포인트가 SSE(Server-Sent Events)로 응답:

| 이벤트 | 데이터 | 설명 |
|---|---|---|
| `meta` | `{route, thread_id}` | 라우트 분류 결과 |
| `data` | `{ticker_info, price, key_metrics, follow_up}` | company 주가 데이터 (LLM 합성 전 선행 전송) |
| `chunk` | `{text}` | LLM 합성 토큰 (실시간 스트리밍) |
| `done` | `StockResponse` | 최종 응답 (구조화 데이터) |
| `error` | `{message}` | 에러 메시지 |

10초 간격 heartbeat로 Render 프록시 타임아웃 방지.

---

## 환경 변수

```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=stock-glossary
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=stock-helper
LANGSMITH_TRACING=true
```

---

## 실행 방법

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 2. 의존성 설치
pip install -r requirements.txt

# 3. (최초 1회) 용어집 Pinecone 인덱싱
python rag_data/ingest.py

# 4. 서버 실행
python main.py
# → http://localhost:8000 에서 접속
```

---

## 테스트

```bash
pytest tests/test_chains.py -v
```

실제 API 호출 기반 테스트:
- Document Relevance: 관련 문서 판단
- 답변 생성: 동작 확인
- Groundedness: 할루시네이션 판단
- Answer Helpfulness: 답변 유용성 판단
- 슈퍼바이저 라우팅: 카테고리 분류

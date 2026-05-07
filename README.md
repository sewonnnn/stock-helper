# 주식 도우미 AI

> 주식 초보자를 위한 AI 어시스턴트. LangGraph 기반 멀티 에이전트 시스템.

---

## 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 주제 | 주식 초보자를 위한 AI 어시스턴트 |
| 대상 시장 | 미국 주식 (한국 주식 일부 지원) |
| 응답 언어 | 한국어 (데이터는 영문, LLM이 한국어로 변환/요약) |

**제공 기능**

- 기업 정보 조회 (시가총액, 가격, 재무지표) — 시각화 카드 형태로 제공
- 최신 뉴스 및 시장 분위기 분석
- 주식 용어/개념 설명 (Self-RAG 정석 적용)
- 일반 시장/트렌드 질문 응답
- 맞춤형 투자 안내 (연령/자산 기반)
- 모든 답변에 출처 + 면책문구
- 할루시네이션 검증 + 1회 재시도
- 용어 하이라이트 (40+개 금융 용어 인라인 툴팁)
- 출처 URL 신뢰 도메인 필터링 + 유효성 검사

---

## 기술 스택

| 분류 | 도구 |
|---|---|
| 오케스트레이션 | LangGraph (커스텀 StateGraph) |
| LLM (답변 생성) | OpenAI GPT-4o |
| LLM (라우팅/검증/grading) | OpenAI GPT-4o-mini |
| 기업 데이터 | yfinance |
| 웹 검색 | Tavily API |
| 벡터 DB | Pinecone |
| 임베딩 | OpenAI text-embedding-3-small |
| 추적/디버깅 | LangSmith |
| 백엔드 | FastAPI + Uvicorn |
| 프론트 | HTML + Tailwind CDN + Vanilla JS |
| 출력 검증 | Pydantic Structured Output |
| 체인 | LCEL (LangChain Expression Language) |
| 테스트 | pytest + pytest-asyncio |

---

## 아키텍처

```
[브라우저 HTML UI] ─ 채팅창 + 추천 버튼 + 시각화 카드 응답
     ↓ POST /chat
[FastAPI 서버]
     ↓ graph.invoke()
┌──────────────────────────────────────────────────┐
│  LangGraph 메인 그래프 (커스텀 StateGraph)        │
│                                                  │
│  [슈퍼바이저 노드] ── 5개 라우트 분류             │
│          ↓                                       │
│    ┌─────┼─────┬──────────┬──────────┐           │
│    ↓     ↓     ↓          ↓          ↓           │
│ [기업] [뉴스] [용어]   [일반]    [어드바이저]     │
│ ReAct  ReAct  Self-RAG  ReAct     ReAct          │
│ yfinance Tavily Pinecone Tavily   Tavily         │
│    │     │       ↓        ↓          ↓           │
│    │     │    직통응답  직통응답   직통응답        │
│    └─────┘                                       │
│       ↓                                          │
│  [검증 노드] ── 할루시네이션 체크                 │
│       ↓                                          │
│    ┌──┴──┐                                       │
│  통과   실패 (max 1회 재시도)                     │
│    ↓     ↓                                       │
│ [응답]  슈퍼바이저로 복귀 (실패 이유 피드백)      │
└──────────────────────────────────────────────────┘
```

### 설계 원칙

- **메인은 커스텀 StateGraph**: 분기/검증/재시도를 명시적으로 제어
- **서브는 `create_react_agent`**: 도구 호출은 표준 ReAct 패턴
- **glossary 에이전트에 Self-RAG 정석 적용**: ISREL → ISSUP → ISUSE 3단계 전부 구현
- **LCEL 체인 + LangGraph 결합**: 단순 LLM 호출은 LCEL, 복잡한 제어 흐름은 LangGraph
- **검증 분기**: company/news는 검증 노드 경유, glossary/general/advisor는 직통 응답
- **모델 분리**: 답변 생성은 GPT-4o, 판단/라우팅은 GPT-4o-mini로 비용 최적화
- **출처 신뢰성**: 신뢰 도메인 필터링 + URL 유효성 검사 (병렬 HEAD 요청)

---

## 폴더 구조

```
stock-helper/
├── .env.example
├── .gitignore
├── requirements.txt
├── PLAN.md                          # 본 문서
├── main.py                          # FastAPI 진입점
│
├── stock_agent/
│   ├── __init__.py
│   ├── agent.py                     # 그래프 조립 (build_graph)
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── state.py                 # GraphState 정의
│   │   ├── constants.py             # 상수 (모델, 도메인, 면책문구)
│   │   └── schemas.py              # Pydantic 모델 (StockResponse)
│   │
│   ├── chains/
│   │   ├── __init__.py
│   │   ├── retrieval_grader.py     # ISREL (문서 관련성)
│   │   ├── hallucination_grader.py # ISSUP (할루시네이션 판단)
│   │   ├── answer_grader.py        # ISUSE (답변 유용성)
│   │   └── generation.py           # 용어 답변 생성 체인
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── supervisor.py           # 5개 라우트 분류
│   │   ├── company.py              # 기업분석 ReAct 에이전트
│   │   ├── news.py                 # 뉴스 검색 ReAct 에이전트
│   │   ├── glossary.py             # 용어설명 Self-RAG 에이전트
│   │   ├── general.py              # 일반 시장/트렌드 질문
│   │   ├── advisor.py              # 맞춤형 투자 안내
│   │   ├── validator.py            # 사실 검증
│   │   └── responder.py            # 최종 응답 포맷팅
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── yfinance_tools.py       # 주식 데이터 도구 (5개)
│   │   ├── tavily_tools.py         # 웹 검색 도구
│   │   ├── rag_tools.py            # Pinecone RAG 검색
│   │   └── ticker_mapping.py       # 한↔영 종목명 매핑 (100+개)
│   │
│   └── prompts/
│       ├── __init__.py
│       ├── supervisor.py
│       ├── company.py
│       ├── news.py
│       ├── glossary.py
│       ├── general.py
│       ├── advisor.py
│       ├── retrieval_grader.py
│       ├── hallucination_grader.py
│       ├── answer_grader.py
│       ├── validator.py
│       └── responder.py
│
├── rag_data/
│   ├── documents/                  # 한국어 용어집 마크다운 (26개)
│   │   ├── per.md
│   │   ├── pbr.md
│   │   ├── eps.md
│   │   ├── roe.md
│   │   ├── rsi.md
│   │   ├── etf.md
│   │   ├── 공매도.md
│   │   ├── 배당.md
│   │   └── ... (18개 더)
│   └── ingest.py                   # Pinecone 인덱싱 스크립트
│
├── tests/
│   ├── __init__.py
│   └── test_chains.py              # 체인 단위 테스트 (10개)
│
└── static/
    └── index.html                  # 프론트엔드 (단일 파일)
```

---

## 노드 상세

### 슈퍼바이저 (supervisor)

사용자 질문을 5개 카테고리로 분류:

| 라우트 | 설명 | 예시 |
|---|---|---|
| `company` | 특정 기업의 가격/시총/재무지표 | "애플 시가총액?" |
| `news` | 최신 뉴스/시장 분위기 | "테슬라 오늘 뉴스" |
| `glossary` | 주식 용어/개념 설명 | "PER이 뭐야?" |
| `general` | 일반 시장/트렌드 질문 | "요즘 인기 있는 주식?" |
| `advisor` | 맞춤형 투자 안내 (개인 맥락 포함) | "24살 연봉 3200 투자 전략" |

### 기업분석 에이전트 (company)

ReAct 패턴으로 yfinance 도구 5개를 질문에 맞게 선택 호출:

| 도구 | 반환 데이터 |
|---|---|
| `get_stock_overview` | 회사명, 섹터, 현재가, 시가총액, 52주 범위, 거래량 |
| `get_valuation_metrics` | PER, Forward PER, PBR, EPS, 배당수익률 |
| `get_financial_health` | 매출, 영업이익, 순이익, 성장률, 이익률 |
| `get_recent_news` | yfinance 자체 뉴스 (보조 소스) |
| `resolve_ticker` | 한국어 종목명 → 티커 심볼 변환 |

### 뉴스서치 에이전트 (news)

Tavily API로 최근 1주 뉴스 검색. 신뢰 도메인 한정.

### 용어설명 에이전트 (glossary) — Self-RAG 정석 적용

Pinecone 검색 후 Self-RAG 3단계 grading 적용:

```
[질문] → [Pinecone 검색] → [ISREL: 관련성?]
                              ├─ No → "용어집에 없음" fallback
                              └─ Yes → [답변 생성 (GPT-4o)]
                                         → [ISSUP: 근거 있음?]
                                           ├─ No → 재생성 (1회)
                                           └─ Yes → [ISUSE: 유용?]
                                                     ├─ No → 재생성 (1회)
                                                     └─ Yes → 최종 응답
```

### 일반 질문 에이전트 (general)

Tavily API로 최근 1개월 범위 검색. 웹 검색 결과를 한국어로 정리하여 직통 응답.

### 어드바이저 에이전트 (advisor)

사용자의 개인 맥락(나이, 자산, 목표 등)을 감지하여 맞춤형 투자 안내 제공. Tavily API로 최근 1년 범위, 금융 교육/증권사 도메인 포함 검색.

### 검증 노드 (validator)

company/news 에이전트 출력에 대한 사실 검증:
- 원본 도구 데이터 vs 답변 숫자 대조
- 사실/인용 근거 확인
- 출처 URL 진위 확인
- 하나라도 틀리면 fail → 1회 재시도

### 응답 포맷터 (responder)

검증 통과된 답변을 StockResponse 스키마에 맞게 구조화 (company/news만 경유).

---

## 응답 흐름 분기

| 에이전트 | 검증 | 응답 |
|---|---|---|
| company | validator → responder | 구조화된 StockResponse |
| news | validator → responder | 구조화된 StockResponse |
| glossary | 내부 Self-RAG (ISREL/ISSUP/ISUSE) | 직통 응답 (용어설명 필드) |
| general | 없음 | 직통 응답 (인사이트 필드) |
| advisor | 없음 | 직통 응답 (인사이트 필드) |

general/advisor의 직통 응답에서도 출처 URL은 신뢰 도메인 필터링 + HEAD 요청 유효성 검사를 거침.

---

## 모델 배정

| 노드/체인 | 모델 | 이유 |
|---|---|---|
| 슈퍼바이저 (라우팅) | GPT-4o-mini | 5지 분류라 mini로 충분 |
| 기업분석 에이전트 | GPT-4o | 자연스러운 한국어 필요 |
| 뉴스서치 에이전트 | GPT-4o | 자연스러운 한국어 필요 |
| 일반 질문 에이전트 | GPT-4o | 자연스러운 한국어 필요 |
| 어드바이저 에이전트 | GPT-4o | 자연스러운 한국어 필요 |
| glossary 답변 생성 | GPT-4o | 용어 설명 품질 필요 |
| ISREL (문서 관련성) | GPT-4o-mini | yes/no 판단 |
| ISSUP (할루시네이션) | GPT-4o-mini | bool 판단 |
| ISUSE (답변 유용성) | GPT-4o-mini | yes/no 판단 |
| 검증 노드 | GPT-4o-mini | 숫자 대조 단순 비교 |
| responder (최종 출력) | GPT-4o | 구조화 출력 품질 |

---

## 신뢰 도메인

### 뉴스 도메인 (16개)

미국/글로벌: Reuters, Bloomberg, CNBC, WSJ, Yahoo Finance, MarketWatch, FT, Barron's
한국: 한경, 매경, 서울경제, 연합인포맥스, 조선비즈, 머니투데이

### 어드바이저 추가 도메인 (8개)

뉴스 도메인 + Investopedia, NerdWallet, KB증권, 삼성증권, 미래에셋, NH투자, 신한투자, 토스증권, 뱅크샐러드

### 제외 도메인 (11개)

Facebook, Instagram, YouTube, Twitter/X, TikTok, Reddit, 나무위키, 네이버 블로그/카페, 티스토리

---

## 프론트엔드

단일 HTML 파일 (Tailwind CDN + Vanilla JS)로 구현된 채팅 UI.

### 주요 기능

- **시각화 카드 응답**: 가격 카드 (등락 색상), 핵심 지표 칩 그리드, 52주 범위 바, 뉴스 카드
- **용어 하이라이트**: 40+개 금융 용어에 인라인 툴팁 (호버/클릭으로 정의 표시)
- **추천 질문 버튼**: 초기 화면에 6개 추천 질문 표시 (첫 메시지 후 사라짐)
- **로딩 애니메이션**: 순환 로딩 메시지 ("질문 분석 중..." → "데이터 조회 중..." → ...)
- **반응형 레이아웃**: 모바일 대응
- **출처 표시**: 신뢰 도메인 URL 링크 + 확신도 표시

### 응답 카드 구성

질문 종류에 따라 채워진 섹션만 조건부 렌더링:

| 섹션 | 사용 라우트 |
|---|---|
| 종목 정보 (티커, 섹터) | company, news |
| 가격 카드 (등락 색상, 시총) | company |
| 52주 범위 바 | company |
| 핵심 지표 칩 그리드 | company |
| 회사 소개 | company |
| 뉴스 카드 | news |
| 인사이트 | company, news, general, advisor |
| 용어 설명 | glossary |

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

### API

```
POST /chat
Request:  {"question": "string"}
Response: {"success": bool, "data": StockResponse | null, "route": string, "error": string | null}
```

---

## 테스트

```bash
pytest tests/test_chains.py -v
```

실제 API 호출 기반 테스트 10개:
- ISREL: 관련 문서 yes/no 판단 (2개)
- 답변 생성: 동작 확인 (1개)
- ISSUP: 할루시네이션 판단 (2개)
- ISUSE: 답변 유용성 판단 (2개)
- 슈퍼바이저 라우팅: company/news/glossary (3개)

---

## 핵심 설계 포인트

- **멀티 에이전트 협업**: 5개 도메인 전문 에이전트 분리
- **Self-RAG 정석**: glossary 에이전트에 ISREL/ISSUP/ISUSE 3단계 전부 구현
- **이중 검증 체계**: Self-RAG 내부 검증 + 메인 그래프 검증 노드 (역할 분리)
- **비용 최적화**: GPT-4o / GPT-4o-mini 이원화
- **시각화 우선 응답**: 텍스트 대신 카드/지표 칩/범위 바
- **신뢰 도메인 한정**: Tavily `include_domains`로 신뢰 소스만 사용
- **출처 검증**: URL 유효성 검사 (병렬 HEAD 요청)
- **모르면 "확인 불가"**: 추측 금지, 정직성 우선
- **LangSmith 추적**: 모든 단계 디버깅 가능

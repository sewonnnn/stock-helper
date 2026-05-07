# 주식 도우미 AI — 프로젝트 계획서

> 주식 초보자를 위한 AI 어시스턴트. LangGraph 기반 멀티 에이전트 시스템.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 주제 | 주식 초보자를 위한 AI 어시스턴트 |
| 대상 시장 | 미국 주식 |
| 응답 언어 | 한국어 (데이터는 영문, LLM이 한국어로 변환/요약) |
| 개발 기간 | 2일 (총 16시간) |

**제공 기능**

- 기업 정보 조회 (시가총액, 가격, 재무지표) — **시각화 카드 형태로 제공**
- 최신 뉴스 및 시장 분위기 분석
- 주식 용어/개념 설명 (**Self-RAG 정석 적용**)
- 모든 답변에 출처 + 면책문구
- 할루시네이션 검증 + 1회 재시도

---

## 2. 기술 스택

| 분류 | 도구 | 비용 |
|---|---|---|
| 오케스트레이션 | LangGraph | 무료 |
| LLM (답변 생성) | OpenAI GPT-4o | ~$3 (개발+시연) |
| LLM (라우팅/검증/grading) | OpenAI GPT-4o-mini | 미미 |
| 기업 데이터 | yfinance | 무료 |
| 웹 검색 | Tavily API | 무료 (1,000회/월) |
| 벡터 DB | Pinecone (Starter) | 무료 |
| 임베딩 | OpenAI text-embedding-3-small | 미미 |
| 추적/디버깅 | LangSmith | 무료 |
| 백엔드 | FastAPI | 무료 |
| 프론트 | HTML + Tailwind CDN + Vanilla JS | 무료 |
| 출력 검증 | Pydantic Output Parser | 무료 |
| 체인 | LCEL (LangChain Expression Language) | 무료 |
| 테스트 | pytest + pytest-asyncio | 무료 |

---

## 3. 아키텍처

```
[브라우저 HTML UI] ─ 채팅창 + 추천 버튼 + 시각화 카드 응답
     ↓ POST /chat
[FastAPI 서버]
     ↓ graph.invoke()
┌────────────────────────────────────────────┐
│  LangGraph 메인 그래프 (커스텀 StateGraph)  │
│                                            │
│  [슈퍼바이저 노드] ── 어떤 에이전트?         │
│          ↓                                 │
│    ┌─────┼─────┬──────────┐                │
│    ↓     ↓     ↓          ↓                │
│  [기업분석][뉴스서치][용어설명]              │
│   ReAct   ReAct   Self-RAG 정석             │
│  yfinance Tavily  (ISREL→ISSUP→ISUSE)      │
│    │      │       │                        │
│    └──────┼───────┘                        │
│           ↓                                │
│    [검증 노드] ── 할루시네이션 체크          │
│           ↓                                │
│      ┌──┴──┐                               │
│    통과   실패 (max 1회 재시도)             │
│      ↓     ↓                               │
│   [응답]  슈퍼바이저로 (실패 이유 피드백)   │
│           재시도 후에도 실패 → "확인 불가"  │
└────────────────────────────────────────────┘
```

### 설계 원칙

- **메인은 커스텀 StateGraph**: 분기/검증/재시도를 명시적으로 제어
- **서브는 `create_react_agent`**: 도구 호출은 표준 ReAct 패턴이라 prebuilt가 효율적
- **glossary 에이전트에 Self-RAG 정석 적용**: ISREL → ISSUP → ISUSE 3단계 전부 구현
- **LCEL 체인 + LangGraph 결합**: responder, validator, supervisor 노드에서 체인 활용
- **검증 노드 + 1회 재시도**: 답변 사실 확인 후 실패 시 1회 재시도 → 그래도 실패하면 "확인 불가"
- **시각화 우선 응답**: 텍스트 나열 대신 카드/지표 칩/범위 바로 표시
- **모델 분리**: 답변 생성은 GPT-4o, 판단/라우팅은 GPT-4o-mini로 비용 최적화

### 이전 프로젝트 구조와의 차이 (참고)

이전 Self-RAG 패턴과 이번 멀티 에이전트 패턴 비교:

| 이전 (Self-RAG 패턴) | 이번 (멀티 에이전트 + Self-RAG 정석 적용) |
|---|---|
| `retrieve.py` — 벡터 검색 | `glossary.py` 에이전트 내부에 통합 |
| `grade_documents.py` — 문서 관련성 평가 | `chains/retrieval_grader.py` (ISREL) |
| `generate.py` — 답변 생성 | `chains/generation.py` + `responder.py` (Output Parser + 시각화 스키마) |
| (없음) | `chains/hallucination_grader.py` (ISSUP) ★ 신규 |
| (없음) | `chains/answer_grader.py` (ISUSE) ★ 신규 |
| `web_search.py` — Tavily 검색 | `news.py` 에이전트로 통합 |

**Self-RAG 정석 적용 의미**: glossary 에이전트 내부에 "검색 → 문서 관련성 평가(ISREL) → 답변 생성 → 할루시네이션 판단(ISSUP) → 답변 유용성 판단(ISUSE)" 흐름을 미니 그래프로 구현. 메인 그래프의 검증 노드는 **모든 에이전트**의 숫자/사실/출처를 대조하는 별도 역할.

---

## 4. 폴더 구조 (LangGraph 공식 권장 구조 기반)

```
stock-helper/
├── .env
├── .env.example
├── requirements.txt
├── README.md
├── PLAN.md                       # 본 문서
├── main.py                       # FastAPI 진입점
│
├── stock_agent/                   # ★ 공식 권장 패키지 구조
│   ├── __init__.py
│   ├── agent.py                   # 그래프 조립 (build_graph)
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── state.py               # GraphState 정의
│   │   ├── constants.py           # 상수 모음 (모델 분리 포함)
│   │   └── schemas.py             # Pydantic 모델 (시각화 친화적)
│   │
│   ├── chains/                    # ★ 신규 - Self-RAG 체인 + grader
│   │   ├── __init__.py
│   │   ├── retrieval_grader.py    # ISREL 체인 + GradeDocuments 스키마
│   │   ├── hallucination_grader.py # ISSUP 체인 + GradeHallucinations 스키마
│   │   ├── answer_grader.py       # ISUSE 체인 + GradeAnswer 스키마
│   │   └── generation.py          # 용어 답변 생성 체인
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── supervisor.py          # 라우팅 결정 (LCEL 체인)
│   │   ├── company.py             # 기업분석 ReAct + 노드 wrapper
│   │   ├── news.py                # 뉴스서치 ReAct + 노드 wrapper
│   │   ├── glossary.py            # 용어설명 Self-RAG 정석 미니 그래프 + 노드 wrapper
│   │   ├── validator.py           # 사실 검증 (LCEL 체인)
│   │   └── responder.py           # 최종 응답 (LCEL 체인 + Output Parser)
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── yfinance_tools.py      # 4개 도구로 분리
│   │   ├── tavily_tools.py
│   │   ├── rag_tools.py
│   │   └── ticker_mapping.py      # 한↔영 종목명 매핑
│   │
│   └── prompts/
│       ├── __init__.py
│       ├── supervisor.py
│       ├── validator.py
│       ├── company.py
│       ├── news.py
│       ├── glossary.py
│       ├── retrieval_grader.py    # ★ ISREL 프롬프트 (doc_grader.py에서 이름 변경)
│       ├── hallucination_grader.py # ★ ISSUP 프롬프트 (신규)
│       ├── answer_grader.py       # ★ ISUSE 프롬프트 (신규)
│       └── responder.py
│
├── rag_data/                      # 코드 아닌 데이터
│   ├── documents/                 # 한국어 용어집 마크다운
│   │   ├── per.md
│   │   ├── pbr.md
│   │   ├── 공매도.md
│   │   └── ... (20~30개)
│   └── ingest.py                  # Pinecone 인덱싱 (1회 실행)
│
├── tests/                         # ★ 신규 - 체인 단위 테스트
│   ├── __init__.py
│   └── test_chains.py             # 실제 API 호출 테스트 10개
│
└── static/
    └── index.html                 # 프론트 단일 파일
```

---

## 5. 컴포넌트 상세

### 5.1 GraphState (utils/state.py)

```python
from typing import TypedDict
from stock_agent.utils.schemas import StockResponse

class GraphState(TypedDict):
    question: str              # 사용자 질문
    route: str                 # 슈퍼바이저 결정
    agent_results: dict        # 에이전트별 결과
    draft_answer: str          # 초안 답변
    validated: bool            # 검증 통과 여부
    validation_reason: str     # 실패 이유
    hallucinated_parts: list   # 문제 있는 문장
    retry_count: int           # 재시도 횟수
    final_answer: StockResponse # 최종 출력
```

### 5.2 Constants (utils/constants.py)

```python
# 모델 설정 — ★ 모델 분리 적용
DEFAULT_MODEL = "gpt-4o"             # 서브 에이전트 답변 생성, responder
LIGHT_MODEL = "gpt-4o-mini"          # 라우팅, grading, 검증
VALIDATOR_MODEL = "gpt-4o-mini"      # 검증 노드
EMBEDDING_MODEL = "text-embedding-3-small"

# 그래프 설정
MAX_RETRIES = 1

# Pinecone
PINECONE_INDEX_NAME = "stock-glossary"

# Tavily 신뢰 도메인
TRUSTED_NEWS_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "ft.com",
    "barrons.com",
]

# 면책문구
DISCLAIMER = (
    "본 내용은 투자 권유가 아닙니다. "
    "투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다."
)

# 응답 메시지
UNKNOWN_RESPONSE = "확인 불가합니다. 정확한 데이터를 찾을 수 없습니다."
```

#### 모델 배정표

| 노드/체인 | 모델 | 이유 |
|---|---|---|
| 슈퍼바이저 (라우팅) | gpt-4o-mini | 3지 분류라 mini로 충분 |
| 기업분석 에이전트 (답변) | gpt-4o | 자연스러운 한국어 필요 |
| 뉴스서치 에이전트 (답변) | gpt-4o | 자연스러운 한국어 필요 |
| glossary 답변 생성 | gpt-4o | 용어 설명 품질 필요 |
| ISREL (문서 관련성) | gpt-4o-mini | yes/no 판단 |
| ISSUP (할루시네이션) | gpt-4o-mini | bool 판단 |
| ISUSE (답변 유용성) | gpt-4o-mini | yes/no 판단 |
| 검증 노드 | gpt-4o-mini | 숫자 대조 단순 비교 |
| responder (최종 출력) | gpt-4o | 구조화 출력 품질 |

### 5.3 yfinance 도구 4개 분리 (tools/yfinance_tools.py)

ReAct 에이전트가 질문 종류에 따라 필요한 도구만 선택 호출하도록 4개로 분리:

```python
@tool
def get_stock_overview(ticker: str) -> dict:
    """기업 개요 + 현재가 + 시가총액. 가장 자주 쓰이는 도구.
    반환: 회사명, 섹터, 산업, 사업 설명, 현재가, 전일 종가, 등락률,
          시가총액, 52주 최고/최저, 거래량
    """

@tool
def get_valuation_metrics(ticker: str) -> dict:
    """밸류에이션 지표.
    반환: PER, Forward PER, PBR, EPS, 배당수익률, 배당성향
    """

@tool
def get_financial_health(ticker: str) -> dict:
    """재무 건전성.
    반환: 매출, 영업이익, 순이익, 매출 성장률(YoY), 영업이익률, 순이익률
    """

@tool
def get_recent_news(ticker: str, limit: int = 5) -> list:
    """yfinance 자체 뉴스 (Tavily 외 보조 소스).
    반환: 제목, 링크, 발행일, 발행처
    """
```

**왜 4개인가:**
- "애플 시총?" → `get_stock_overview` 1개만 호출
- "테슬라 PER이랑 매출 성장률" → 2개 호출
- 너무 잘게 쪼개면 호출 횟수 증가 → 비용/속도 손해
- 4개가 균형점

### 5.4 서브 에이전트 (모두 create_react_agent 기반)

| 에이전트 | 도구 | 역할 |
|---|---|---|
| 기업분석 | yfinance 도구 4개 + 티커 매핑 | 정확한 숫자 조회 |
| 뉴스서치 | Tavily (신뢰 도메인 한정) + 티커 매핑 | 최신 뉴스/이슈/시장 분위기 |
| 용어설명 | Pinecone RAG 검색 + Self-RAG 정석 (3단계 grading) | Self-RAG 정석 적용 |

### 5.5 Self-RAG 정석 적용 (nodes/glossary.py)

용어설명 에이전트 내부에 Self-RAG **정석** 흐름을 미니 그래프로 구현:

```
[질문]
  ↓
[Pinecone 검색] ── 상위 K개 문서
  ↓
[ISREL: 문서 관련성 판단] ── 각 문서가 질문과 관련 있는가?
  ↓
  ├─ 관련 없음 → "용어집에 없음" fallback 응답
  └─ 관련 있음 → [답변 생성] (generation_chain, GPT-4o)
                    ↓
                 [ISSUP: 할루시네이션 판단] ── 생성이 문서에 근거하는가?
                    ↓
                    ├─ 근거 없음 → 재생성 (1회)
                    └─ 근거 있음 → [ISUSE: 답변 유용성 판단] ── 질문에 실제로 답하는가?
                                    ↓
                                    ├─ 유용하지 않음 → 재생성 (1회)
                                    └─ 유용함 → 최종 응답 반환
```

#### Self-RAG 체인 3개 (chains/ 디렉토리)

```python
# chains/retrieval_grader.py — ISREL
class GradeDocuments(BaseModel):
    binary_score: str  # "yes" / "no"

retrieval_grader = (
    ChatPromptTemplate.from_template(RETRIEVAL_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL).with_structured_output(GradeDocuments)
)

# chains/hallucination_grader.py — ISSUP
class GradeHallucinations(BaseModel):
    binary_score: bool  # True = 근거 있음

hallucination_grader = (
    ChatPromptTemplate.from_template(HALLUCINATION_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL).with_structured_output(GradeHallucinations)
)

# chains/answer_grader.py — ISUSE
class GradeAnswer(BaseModel):
    binary_score: str  # "yes" / "no"

answer_grader = (
    ChatPromptTemplate.from_template(ANSWER_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL).with_structured_output(GradeAnswer)
)

# chains/generation.py — 답변 생성
generation_chain = (
    ChatPromptTemplate.from_template(GLOSSARY_PROMPT)
    | ChatOpenAI(model=DEFAULT_MODEL)
    | StrOutputParser()
)
```

#### 메인 그래프 검증 노드와의 관계

- **Self-RAG 내부 ISSUP**: glossary 에이전트 **내부**에서 생성된 답변이 검색 문서에 근거하는지 판단
- **메인 그래프 검증 노드**: **모든 에이전트** 출력에 대한 숫자/사실/출처 URL 대조
- 역할이 다르므로 이중 검증이 아님

### 5.6 LCEL 체인 활용 위치

**responder 노드 (필수)**

```python
responder_chain = (
    ChatPromptTemplate.from_template(RESPONDER_PROMPT)
    | ChatOpenAI(model=DEFAULT_MODEL).with_structured_output(StockResponse)
)
```

**validator 노드 (권장)**

```python
validator_chain = (
    ChatPromptTemplate.from_template(VALIDATOR_PROMPT)
    | ChatOpenAI(model=VALIDATOR_MODEL)
    | JsonOutputParser()
)
```

**supervisor 노드**

```python
supervisor_chain = (
    ChatPromptTemplate.from_template(SUPERVISOR_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL)
    | StrOutputParser()
)
```

### 5.7 검증 노드

- 별도 LLM 호출 (LCEL 체인, **GPT-4o-mini**)
- 도구 원본 데이터 vs 답변 대조
- JSON 반환: `{verdict, reason, hallucinated_parts}`
- 체크 항목:
  1. 답변 속 숫자가 원본 데이터에 실제로 있는가?
  2. 답변 속 사실/인용이 원본에 있는가?
  3. 추측해서 만든 부분이 있는가?
  4. 출처 URL이 진짜인가?

### 5.8 재시도 로직

- 검증 실패 → 슈퍼바이저로 복귀
- 실패 이유를 다음 시도 프롬프트에 피드백
- `MAX_RETRIES=1` (constants에서 관리) → 무한루프 차단
- 최종 실패 → "확인 불가합니다" + 면책문구

### 5.9 Output Parser — 시각화 친화적 스키마 (utils/schemas.py)

응답을 텍스트 한 덩어리가 아니라 **시각화 가능한 구조**로 출력:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from stock_agent.utils.constants import DISCLAIMER

class TickerInfo(BaseModel):
    ticker: str                  # "AAPL"
    company_name: str            # "Apple Inc."
    sector: Optional[str] = None
    industry: Optional[str] = None

class PriceInfo(BaseModel):
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    market_cap: Optional[str] = None      # "$2.84T"
    market_cap_tier: Optional[Literal["대형주", "중형주", "소형주"]] = None

class RangeInfo(BaseModel):
    low_52w: float
    high_52w: float
    current: float
    position_percent: float       # 0~100, 범위 내 위치 %
    interpretation: str           # "저점 대비 +11%, 고점 대비 -23%"

class Metric(BaseModel):
    name: str                     # "PER"
    value: str                    # "28.5배"
    level: Literal["높음", "보통", "낮음", "정보없음"]
    note: Optional[str] = None    # "업계 평균(20배) 대비"

class NewsItem(BaseModel):
    title: str
    source: str                   # "Reuters"
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None # 1줄 한국어 요약

class StockResponse(BaseModel):
    """질문 종류에 따라 일부 필드만 채워질 수 있음 (모두 Optional).
    프론트는 채워진 필드만 렌더링."""

    종목: Optional[TickerInfo] = None
    가격: Optional[PriceInfo] = None
    범위_52주: Optional[RangeInfo] = None
    핵심지표: Optional[list[Metric]] = None
    회사소개: Optional[str] = None
    뉴스: Optional[list[NewsItem]] = None
    인사이트: Optional[str] = Field(
        None, description="LLM이 종합한 한국어 해석. 초보자가 이해하기 쉽게."
    )
    용어설명: Optional[str] = None       # 용어 질문일 때만
    출처: list[str] = []
    확신도: Literal["높음", "중간", "낮음"] = "중간"
    면책문구: str = DISCLAIMER
```

**핵심**: 모든 도메인 필드를 Optional로 둬서 질문 종류에 따라 일부만 채움.
- "애플 시총?" → `종목`, `가격`만 채움
- "PER 어때?" → `종목`, `핵심지표`, `인사이트` 채움
- "PER이 뭐야?" → `용어설명`만 채움
- "엔비디아 분석" → 거의 모든 필드 채움

### 5.10 티커 매핑 (tools/ticker_mapping.py)

- 주요 미국 종목 50개 한국어 → 티커 딕셔너리 (하드코딩)
- 영문 티커 직접 입력 fallback
- 매핑 실패 시 "확인 불가"

```python
TICKER_MAP = {
    "애플": "AAPL", "apple": "AAPL",
    "테슬라": "TSLA", "tesla": "TSLA",
    "엔비디아": "NVDA", "nvidia": "NVDA",
    # ... 50개
}
```

### 5.11 RAG (Pinecone)

- 한국어 마크다운 용어집 20~30개 (직접 작성)
- 임베딩: `text-embedding-3-small`
- 인덱스명: `stock-glossary`
- 용어 예시: PER, PBR, EPS, ROE, 시가총액, 공매도, 배당, 액면분할, 상한가, 서킷브레이커, ETF, 인덱스펀드 등

### 5.12 프론트엔드 — 시각화 카드 응답

**응답 카드 레이아웃**

```
┌─────────────────────────────────────────┐
│  본 내용은 투자 권유가 아닙니다          │  ← 상단 고정 배너
├─────────────────────────────────────────┤
│  AAPL · Apple Inc.                      │  ← 종목
│  Tech / Consumer Electronics            │
│                                         │
│  ┌─ $182.45  ▲+1.28% ─────────────────┐│  ← 가격 카드 (등락 색상)
│  │ 시가총액  $2.84T  (대형주)          ││
│  └─────────────────────────────────────┘│
│                                         │
│  52주 범위                              │  ← 범위 바 (SVG)
│  $164 ●━━━━━●━━━━ $237                 │
│        ↑ 저점 대비 +11%                 │
│                                         │
│  핵심 지표                              │  ← 지표 칩 그리드
│  ┌──────┬──────┬──────┬──────┐         │
│  │ PER  │ PBR  │ EPS  │ 배당  │         │
│  │28.5  │45.2  │$6.43 │0.45% │         │
│  │ 高   │ 高   │  -   │ 낮음  │         │
│  └──────┴──────┴──────┴──────┘         │
│                                         │
│  회사 소개                              │  ← 텍스트 섹션
│  애플은 아이폰, 맥, 서비스 사업을       │
│  운영하는 글로벌 IT 기업입니다...       │
│                                         │
│  최근 뉴스                              │  ← 뉴스 카드 (출처 링크)
│  • [Reuters] 애플, 신형 비전프로 출시   │
│  • [CNBC] AI 기능 강화 발표             │
│  • [Bloomberg] 중국 매출 회복 신호      │
│                                         │
│  핵심 인사이트                          │  ← LLM 종합 해석
│  PER이 업계 평균보다 높은 편이지만,     │
│  안정적인 현금흐름과 신사업 확장으로...  │
│                                         │
│  ─────────────────────────────────      │
│  출처: yfinance, Reuters, CNBC          │
│  데이터 기준: 15~20분 지연               │
└─────────────────────────────────────────┘
```

질문 종류에 따라 채워진 섹션만 표시 (조건부 렌더링).

**시각화 컴포넌트 (필수)**

| 컴포넌트 | 구현 방식 |
|---|---|
| 가격 카드 (등락 색상) | Tailwind 클래스 + 조건부 색상 |
| 시가총액 + 등급 | 텍스트 + 배지 |
| 52주 범위 바 | SVG 한 줄 (직선 + 현재 위치 점) |
| 핵심 지표 칩 그리드 | Tailwind grid + 색상 배지 (高/低/보통) |
| 뉴스 카드 | flexbox 카드 리스트 + 출처 링크 |

**시각화 컴포넌트 (선택, 시간 남으면)**

- 가격 차트: Chart.js CDN 추가, 1주/1개월/1년 탭.

**초기 화면 (추천 질문 버튼)**

- 애플 시가총액
- 테슬라 오늘 뉴스
- PER이란?
- 엔비디아 분석
- 공매도 위험성

첫 메시지 후 버튼 사라지고 채팅창만 표시.

**기술 구성**

- 단일 HTML 파일 (Tailwind CDN + Vanilla JS)
- FastAPI에 `StaticFiles`로 마운트
- 응답 받으면 섹션별로 조건부 렌더링하는 함수들

---

## 6. 환경 변수 (.env)

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

## 7. LLM 프롬프트 상세 (prompts/)

> 모든 프롬프트는 **영어**로 작성. 각 프롬프트 아래에 **한글 요약 해석** 첨부.

---

### 7.1 슈퍼바이저 (prompts/supervisor.py)

```python
SUPERVISOR_PROMPT = """You are a routing supervisor for a Korean stock assistant.

Given the user's question in Korean, classify it into exactly ONE of these categories:

- "company": Questions about specific company data (price, market cap, financials, valuation metrics like PER/PBR/EPS)
- "news": Questions about recent news, market sentiment, analyst opinions, or current events about a stock
- "glossary": Questions asking to explain a stock/finance term or concept (e.g., "PER이 뭐야?", "공매도란?")

Rules:
- If the question asks for both company data AND news, choose "company" (the company agent can handle combined queries).
- If the question is about a term/concept even if a company is mentioned (e.g., "애플의 PER이 뭐야?" is asking about PER concept), choose "glossary" ONLY if it's clearly asking for a definition. If it's asking for the actual PER value, choose "company".
- If unsure, choose "company" as the default.

User question: {question}

Respond with only the category name."""
```

**[한글 요약]**
사용자 질문을 3가지 카테고리(company/news/glossary) 중 하나로 분류하는 라우터.
- company: 특정 기업의 가격, 시총, 재무지표 등 숫자 데이터 질문
- news: 최신 뉴스, 시장 분위기, 애널리스트 의견
- glossary: 주식 용어/개념 설명 ("~이 뭐야?")
- 애매하면 company를 기본값으로 선택

---

### 7.2 기업분석 에이전트 (prompts/company.py)

```python
COMPANY_AGENT_PROMPT = """You are a stock analysis agent specializing in US equities.
You help Korean beginners understand company fundamentals.

Your task:
1. Use the provided tools to fetch accurate, real-time data for the requested company.
2. Always use the ticker_mapping tool first to resolve Korean company names to tickers.
3. Call only the tools needed to answer the question — do NOT call all tools for every query.
4. Present ALL numbers exactly as returned by the tools. Never round, estimate, or fabricate any data.
5. Respond in Korean, but keep ticker symbols and English company names as-is.

Important:
- If a tool returns an error or empty data, say "해당 데이터를 확인할 수 없습니다" instead of guessing.
- Never provide investment advice or price predictions.
- Always include the data source (yfinance) in your response.
- For market cap, also include the tier: 대형주 (>$10B), 중형주 ($2B-$10B), 소형주 (<$2B).

User question: {question}"""
```

**[한글 요약]**
미국 주식 기업 분석 에이전트. 한국어 초보자 대상.
- 티커 매핑 도구로 한글 종목명을 먼저 변환
- 질문에 필요한 도구만 선택 호출 (전부 호출 금지)
- 숫자는 도구 반환값 그대로 사용 (반올림/추측 금지)
- 데이터 없으면 "확인 불가" 응답
- 투자 조언/가격 예측 금지
- 시가총액 등급 표시 (대형주/중형주/소형주)

---

### 7.3 뉴스서치 에이전트 (prompts/news.py)

```python
NEWS_AGENT_PROMPT = """You are a financial news research agent for Korean stock beginners.

Your task:
1. Use the ticker_mapping tool first to resolve Korean company names to English names/tickers.
2. Search for recent news using the Tavily tool with the English company name or ticker.
3. Summarize each news article in 1-2 sentences in Korean.
4. Assess overall market sentiment: 긍정적 (positive), 부정적 (negative), or 중립 (neutral).

Rules:
- Only use news from trusted sources (Reuters, Bloomberg, CNBC, WSJ, Yahoo Finance, MarketWatch, FT, Barron's).
- Always include the source name and URL for each news item.
- Present facts only — never add your own market predictions or investment advice.
- If no relevant news is found, say "최근 관련 뉴스를 찾을 수 없습니다."
- Respond entirely in Korean, except for source names and URLs.
- Maximum 5 news items per response.

User question: {question}"""
```

**[한글 요약]**
금융 뉴스 검색 에이전트. 한국어 초보자 대상.
- 한글 종목명을 영문으로 변환 후 Tavily로 검색
- 각 뉴스를 한국어 1~2문장으로 요약
- 시장 분위기 판단: 긍정적/부정적/중립
- 신뢰 도메인(Reuters, Bloomberg 등)만 사용
- 출처명 + URL 필수, 투자 조언 금지
- 최대 5개 뉴스

---

### 7.4 용어설명 답변 생성 (prompts/glossary.py)

```python
GLOSSARY_PROMPT = """You are a stock market glossary expert explaining terms to Korean beginners.

Given the following context documents and a user question, provide a clear and easy-to-understand explanation in Korean.

Context:
{context}

Rules:
- Explain as if teaching someone who has never invested before.
- Use simple analogies and real-world examples when helpful.
- Include the English term in parentheses after the Korean term (e.g., 주가수익비율 (PER)).
- If a formula exists, show it simply: PER = 주가 / 주당순이익(EPS).
- Keep the explanation concise: 3-5 sentences for simple terms, up to 8 sentences for complex ones.
- ONLY use information from the provided context. Do NOT add information from your own knowledge.
- If the context doesn't contain enough information, say so honestly.

User question: {question}"""
```

**[한글 요약]**
주식 용어 설명 생성 체인. 한국어 초보자 대상.
- 검색된 문서(context)만 기반으로 답변 생성 (자체 지식 사용 금지)
- 투자 경험 없는 사람에게 설명하듯이
- 비유/실생활 예시 활용, 영문 용어 병기
- 공식이 있으면 간단히 표시
- 간단한 용어 3~5문장, 복잡한 용어 최대 8문장
- 문서에 정보 부족하면 솔직히 언급

---

### 7.5 ISREL — 문서 관련성 판단 (prompts/retrieval_grader.py)

```python
RETRIEVAL_GRADER_PROMPT = """You are a grader assessing the relevance of a retrieved document to a user question.

Retrieved document:
{document}

User question:
{question}

If the document contains keywords or semantic meaning related to the question, grade it as relevant.
Give a binary score: "yes" if relevant, "no" if not relevant.
"""
```

**[한글 요약]**
검색된 문서가 사용자 질문과 관련 있는지 판단하는 grader.
- 키워드 또는 의미적 관련성이 있으면 "yes"
- 관련 없으면 "no"
- 구조화 출력: `GradeDocuments(binary_score: str)`

---

### 7.6 ISSUP — 할루시네이션 판단 (prompts/hallucination_grader.py)

```python
HALLUCINATION_GRADER_PROMPT = """You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts.

Set of facts (retrieved documents):
{documents}

LLM generation:
{generation}

Give a binary score: true if the generation is grounded in / supported by the set of facts, false if it contains information not supported by the facts.
Strictly check that every claim in the generation can be traced back to the provided documents.
"""
```

**[한글 요약]**
생성된 답변이 검색 문서에 근거하는지 판단하는 grader.
- 답변의 모든 주장이 문서에서 추적 가능하면 true
- 문서에 없는 정보가 포함되어 있으면 false
- 구조화 출력: `GradeHallucinations(binary_score: bool)`

---

### 7.7 ISUSE — 답변 유용성 판단 (prompts/answer_grader.py)

```python
ANSWER_GRADER_PROMPT = """You are a grader assessing whether an answer addresses / is useful to resolve the user's question.

User question:
{question}

LLM generation:
{generation}

Give a binary score: "yes" if the answer is useful and addresses the question, "no" if it does not address the question or is off-topic.
"""
```

**[한글 요약]**
생성된 답변이 실제로 사용자 질문에 답하는지 판단하는 grader.
- 질문에 대한 유용한 답변이면 "yes"
- 질문과 무관하거나 엉뚱한 답변이면 "no"
- 구조화 출력: `GradeAnswer(binary_score: str)`

---

### 7.8 검증 노드 (prompts/validator.py)

```python
VALIDATOR_PROMPT = """You are a fact-checking validator for a stock information assistant.

Your job is to compare the draft answer against the original source data and verify factual accuracy.

Original source data (from tools):
{source_data}

Draft answer:
{draft_answer}

Check the following:
1. Are all numbers in the answer exactly matching the source data? (prices, percentages, market cap, etc.)
2. Are all factual claims supported by the source data?
3. Are there any fabricated or hallucinated details not present in the source?
4. Are source URLs real and properly attributed?

Respond in JSON format:
{{
    "verdict": "pass" or "fail",
    "reason": "explanation of why it passed or failed",
    "hallucinated_parts": ["list of specific hallucinated sentences, empty if passed"]
}}

Be strict: if even one number is wrong or one fact is unsupported, the verdict must be "fail".
"""
```

**[한글 요약]**
모든 에이전트 출력에 대한 사실 검증 노드.
- 원본 도구 데이터와 초안 답변을 대조
- 숫자 정확성, 사실 근거, 출처 URL 진위 확인
- 하나라도 틀리면 "fail"
- JSON 반환: verdict(pass/fail), reason(이유), hallucinated_parts(문제 문장 목록)

---

### 7.9 최종 응답 생성 (prompts/responder.py)

```python
RESPONDER_PROMPT = """You are a response formatter for a Korean stock assistant targeting beginners.

Given the validated answer and source data, produce a structured response following the StockResponse schema.

Validated answer:
{validated_answer}

Source data:
{source_data}

Question type: {route}

Rules:
1. Fill ONLY the fields relevant to the question type:
   - "company" questions: Fill 종목, 가격, 범위_52주, 핵심지표, 회사소개, 인사이트 as available
   - "news" questions: Fill 종목, 뉴스, 인사이트
   - "glossary" questions: Fill 용어설명 only
2. For 인사이트: Write 2-3 sentences in simple Korean that a beginner can understand. Explain what the numbers mean, not just state them.
3. For 핵심지표: Classify each metric level as "높음", "보통", or "낮음" based on general market standards.
4. For 확신도: Set to "높음" if data comes directly from tools, "중간" if partially inferred, "낮음" if uncertain.
5. All text must be in Korean. Keep ticker symbols and English names as-is.
6. Always include 출처 (source list) and 면책문구.
7. Never include investment advice or predictions in any field.
"""
```

**[한글 요약]**
검증 통과된 답변을 StockResponse 스키마에 맞게 구조화하는 최종 포맷터.
- 질문 유형(company/news/glossary)에 따라 필요한 필드만 채움
- 인사이트: 초보자가 이해할 수 있는 간단한 한국어 2~3문장 (숫자의 의미 설명)
- 핵심지표: 일반 시장 기준으로 높음/보통/낮음 분류
- 확신도: 도구 직접 데이터=높음, 부분 추론=중간, 불확실=낮음
- 출처 + 면책문구 필수, 투자 조언/예측 금지

---

## 8. 체인 단위 테스트 (tests/test_chains.py)

이전 프로젝트 스타일을 따름. **실제 API 호출, mock 없음.** 총 10개.


```python
from pprint import pprint
from dotenv import load_dotenv
load_dotenv()

from stock_agent.chains.generation import generation_chain
from stock_agent.chains.hallucination_grader import GradeHallucinations, hallucination_grader
from stock_agent.chains.retrieval_grader import GradeDocuments, retrieval_grader
from stock_agent.chains.answer_grader import GradeAnswer, answer_grader
from stock_agent.nodes.supervisor import question_router, RouteQuery
from stock_agent.tools.rag_tools import retriever


# --- ISREL: 문서 관련성 판단 ---

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


# --- ISSUP: 할루시네이션 판단 ---

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


# --- ISUSE: 답변 유용성 판단 ---

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
```

**실행**: `pytest tests/test_chains.py -v`

---

## 9. 일정 (총 16시간)

### 1일차 (8시간) — 백엔드 코어

| 시간 | 작업 | 결과물 |
|---|---|---|
| 1h | 환경 셋업, 폴더 구조, requirements, .env, constants.py, LangSmith 연결 | 설치 완료 |
| 2h | 기업분석 ReAct 에이전트 (yfinance 도구 4개 + 티커 매핑) | 단독 호출 동작 |
| 2h | 뉴스서치 ReAct 에이전트 (Tavily, 신뢰 도메인 한정, 한↔영 변환) | 단독 호출 동작 |
| 2.5h | 슈퍼바이저 + 메인 StateGraph (조건부 라우팅) | 두 에이전트 라우팅 동작 |
| 0.5h | LangSmith 트레이스 확인, 1일차 커밋 | 추적 확인 |

### 2일차 (8시간) — 품질 + 프론트

| 시간 | 작업 | 결과물 |
|---|---|---|
| 0.5h | 한국어 용어집 마크다운 작성 (20~30개) | .md 파일 |
| 2h | Pinecone 인덱싱 + **Self-RAG 정석 적용** glossary 에이전트 (ISREL→ISSUP→ISUSE) + chains/ 디렉토리 | RAG + Self-RAG 정석 동작 |
| 1h | 검증 노드 + 재시도 루프 + 실패 이유 피드백 | 할루시네이션 방지 동작 |
| 0.5h | **체인 단위 테스트 10개** 작성 + 실행 | `pytest` 전부 통과 |
| 1h | LCEL 체인 (responder + 시각화 스키마) + 시스템 프롬프트 + 면책 | 구조화 출력 완성 |
| 1h | FastAPI 래핑 + StaticFiles 마운트 | API 서버 동작 |
| 2h | HTML 채팅 UI + 추천 버튼 + 시각화 카드 (가격/범위 바/지표 칩/뉴스) | 프론트 완성 |
| (선택) | Chart.js 가격 차트 추가 | 시간 남으면 |

**합계: 8시간 (Chart.js 제외)**

---

## 10. 테스트 케이스 (10개)

### 정상 케이스 (7개)

1. "애플 시가총액 알려줘" → 기업분석 (가격 카드)
2. "테슬라 PER 어때?" → 기업분석 (지표 칩)
3. "엔비디아 오늘 뉴스" → 뉴스서치 (뉴스 카드)
4. "마이크로소프트 요즘 시장에서 어떻게 평가받아?" → 뉴스서치
5. "PER이 뭐야?" → 용어설명 RAG (**Self-RAG 정석 동작 확인: ISREL→ISSUP→ISUSE**)
6. "공매도 위험성 알려줘" → 용어설명 RAG
7. "구글 분석해줘" → 기업분석 + 뉴스서치 복합 (전체 카드)

### 함정 케이스 (3개)

8. "내일 애플 주가 어떻게 될까?" → 예측 거부
9. "한국 카카오 시총" → 매핑 실패 → 확인 불가
10. "가나다라마 용어 설명해줘" → Self-RAG ISREL에서 걸러짐 → 확인 불가

---

## 11. 핵심 가치 제안 (README 박을 내용)

### 왜 이 구조인가

- **메인은 커스텀 StateGraph, 서브는 prebuilt ReAct**: trade-off 이해한 선택
- **Self-RAG 정석 적용**: glossary 에이전트에 ISREL→ISSUP→ISUSE 3단계 전부 구현. 메인 그래프 검증 노드와는 역할 분리
- **LCEL 체인 + LangGraph 결합**: 단순 LLM 호출은 LCEL, 복잡한 제어 흐름은 LangGraph로. 공식 권장 패턴
- **모델 분리 (비용 최적화)**: 답변 생성은 GPT-4o, 판단/라우팅은 GPT-4o-mini
- **검증 노드 + 재시도 1회**: 할루시네이션 차단 안전망. 조건부 엣지 활용
- **신뢰 도메인 한정 + 출처 명시**: Tavily의 `include_domains`로 Bloomberg/Reuters만 사용
- **시각화 우선 응답**: 텍스트 대신 카드/지표 칩/범위 바 — 초보자 가독성 최우선
- **모르면 "확인 불가"**: 추측 금지. 정직성 우선
- **체인 단위 테스트**: Self-RAG 핵심 판단 로직 + 라우팅을 실제 API 호출로 검증 (10개)

### 기술적 차별점

- 멀티 에이전트 협업 (3개 도메인 분리)
- Self-RAG 정석의 ISREL/ISSUP/ISUSE 3단계 전부 구현
- 사실 검증 단계로 할루시네이션 차단
- 영문 데이터 → 한국어 응답 자동 변환
- 시각화 친화적 Pydantic 스키마 → 프론트 카드 렌더링
- LangSmith로 모든 단계 추적 가능
- 비용 최적화: GPT-4o / GPT-4o-mini 이원화

---

## 12. 위험 요소 + 대응

| 위험 | 가능성 | 대응 |
|---|---|---|
| yfinance API 깨짐 | 낮음 | requirements에 버전 고정 |
| Tavily 무료 한도 초과 | 매우 낮음 | 1000건이면 차고 넘침 |
| 검증 노드 무한루프 | 차단됨 | `MAX_RETRIES=1` 하드코딩 |
| Pinecone 셋업 막힘 | 중간 | fallback으로 Chroma 준비 |
| LLM 구조화 출력 어긋남 | 중간 | `with_structured_output()` + 검증 노드에서 빈 필드 체크 |
| 시각화 구현 시간 부족 | 중간 | Chart.js는 선택, 핵심 카드만 우선 |
| 시간 부족 | 중간 | 자를 후보: 가격 차트 → 추천 버튼 디자인 → ... |

---

## 13. 자를 우선순위 (시간 부족 시, 뒤에서부터)

1. **Chart.js 가격 차트** (선택 사항이라 처음부터 빠짐)
2. 추천 버튼 디자인 → 단순 텍스트 버튼
3. 52주 범위 바 → 텍스트로
4. **Self-RAG ISSUP/ISUSE** → ISREL만 남기고 단순 RAG로 회귀
5. 뉴스 카드 디자인 → 단순 리스트

**절대 못 자르는 것**

메인 StateGraph, 기업/뉴스 ReAct 에이전트, 검증 노드, 면책문구, 채팅 UI, FastAPI, **시각화 핵심 (가격 카드 + 지표 칩)**, Output Parser, **체인 단위 테스트**

---

## 14. 참고 자료

- LangGraph 공식 문서 - Application Structure
- LangGraph GitHub
- LangChain LCEL 문서
- Self-RAG 논문
- yfinance 문서
- Tavily API 문서
- Pinecone 문서

---

**작성일**: 2026-05-07
**버전**: 3.0 (Self-RAG 정석 적용 + 모델 분리 + 체인 단위 테스트 + 시각화 응답 + yfinance 도구 4개 분리 반영)

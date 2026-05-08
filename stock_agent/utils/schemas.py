from pydantic import BaseModel, Field
from typing import Literal, Optional



class TickerInfo(BaseModel):
    ticker: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None


class PriceInfo(BaseModel):
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    currency: Literal["KRW", "USD"] = "USD"
    krw_price: Optional[float] = None  # 해외주식일 때 원화 환산가
    usd_krw_rate: Optional[float] = None  # 적용 환율
    market_cap: Optional[str] = None
    market_cap_tier: Optional[Literal["대형주", "중형주", "소형주"]] = None


class RangeInfo(BaseModel):
    low_52w: float
    high_52w: float
    current: float
    position_percent: float
    interpretation: str


class Metric(BaseModel):
    name: str
    value: str
    level: Literal["높음", "보통", "낮음", "정보없음"]
    note: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None


class StockResponse(BaseModel):
    """질문 종류에 따라 일부 필드만 채워질 수 있음 (모두 Optional).
    프론트는 채워진 필드만 렌더링."""

    ticker_info: Optional[TickerInfo] = None
    price: Optional[PriceInfo] = None
    range_52w: Optional[RangeInfo] = None
    key_metrics: Optional[list[Metric]] = None
    company_intro: Optional[str] = None
    news: Optional[list[NewsItem]] = None
    insight: Optional[str] = Field(
        None, description="LLM이 종합한 한국어 해석. 초보자가 이해하기 쉽게."
    )
    glossary: Optional[str] = None
    sources: list[str] = []
    confidence: Literal["높음", "중간", "낮음"] = "중간"
    follow_up: list[str] = Field(default_factory=list, description="사용자가 이어서 물어볼 만한 후속 질문 2~3개")
    disclaimer: Optional[str] = None

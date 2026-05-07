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

    종목: Optional[TickerInfo] = None
    가격: Optional[PriceInfo] = None
    범위_52주: Optional[RangeInfo] = None
    핵심지표: Optional[list[Metric]] = None
    회사소개: Optional[str] = None
    뉴스: Optional[list[NewsItem]] = None
    인사이트: Optional[str] = Field(
        None, description="LLM이 종합한 한국어 해석. 초보자가 이해하기 쉽게."
    )
    용어설명: Optional[str] = None
    출처: list[str] = []
    확신도: Literal["높음", "중간", "낮음"] = "중간"
    후속질문: list[str] = Field(default_factory=list, description="사용자가 이어서 물어볼 만한 후속 질문 2~3개")

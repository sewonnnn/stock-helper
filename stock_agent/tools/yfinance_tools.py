import yfinance as yf
from langchain_core.tools import tool

from stock_agent.tools.ticker_mapping import TICKER_TO_KOREAN


def _get_usd_krw_rate() -> float | None:
    """현재 USD/KRW 환율을 가져옵니다."""
    try:
        fx = yf.Ticker("USDKRW=X")
        rate = fx.info.get("regularMarketPrice") or fx.info.get("previousClose")
        return rate
    except Exception:
        return None


@tool
def get_stock_overview(ticker: str) -> dict:
    """기업 개요 + 현재가 + 시가총액. 가장 자주 쓰이는 도구.
    반환: 회사명, 섹터, 산업, 사업 설명, 현재가, 전일 종가, 등락률,
          시가총액, 52주 최고/최저, 거래량
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        current = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change = round(current - prev_close, 2) if current and prev_close else None
        change_pct = round((change / prev_close) * 100, 2) if change and prev_close else None

        market_cap = info.get("marketCap")
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")

        if market_cap:
            # 한국 주식은 이미 원화, 해외 주식은 USD → KRW 환산
            if is_korean:
                cap_krw = market_cap
            else:
                rate = _get_usd_krw_rate() or 1400
                cap_krw = market_cap * rate

            # 등급 (원화 기준: 대형주 10조 이상, 중형주 2조~10조, 소형주 2조 미만)
            if cap_krw >= 10_000_000_000_000:
                cap_tier = "대형주"
            elif cap_krw >= 2_000_000_000_000:
                cap_tier = "중형주"
            else:
                cap_tier = "소형주"

            # 원화 표시 (증권사 스타일: 조/억 단위만)
            if cap_krw >= 1_000_000_000_000:
                cap_str = f"약 {int(cap_krw // 1_000_000_000_000):,}조원"
            elif cap_krw >= 100_000_000:
                cap_str = f"약 {int(cap_krw // 100_000_000):,}억원"
            else:
                cap_str = f"{cap_krw:,.0f}원"
        else:
            cap_tier = None
            cap_str = None

        # 한국 주식이면 한글명 우선 표시
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")
        korean_name = TICKER_TO_KOREAN.get(ticker)

        if korean_name:
            # 매핑에 있는 경우
            long_name = info.get("longName") or ""
            company_name = f"{korean_name} ({long_name})" if long_name else korean_name
        elif is_korean:
            # 매핑에 없지만 한국 주식인 경우 → shortName이 한글일 수 있음
            short_name = info.get("shortName") or ""
            long_name = info.get("longName") or ""
            company_name = short_name if short_name else long_name
        else:
            company_name = info.get("longName") or info.get("shortName") or ""

        # 미국 주식이면 원화 환산 ��가
        krw_price = None
        krw_rate = None
        if not is_korean and current:
            krw_rate = _get_usd_krw_rate()
            if krw_rate:
                krw_price = round(current * krw_rate)

        return {
            "company_name": company_name,
            "ticker": ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "business_summary": (info.get("longBusinessSummary") or "")[:300],
            "current_price": current,
            "currency": "KRW" if is_korean else "USD",
            "krw_price": krw_price,
            "usd_krw_rate": krw_rate,
            "previous_close": prev_close,
            "change": change,
            "change_percent": change_pct,
            "market_cap": cap_str,
            "market_cap_raw": market_cap,
            "market_cap_tier": cap_tier,
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "volume": info.get("volume"),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_valuation_metrics(ticker: str) -> dict:
    """밸류에이션 지표.
    반환: PER, Forward PER, PBR, EPS, 배당수익률, 배당성향
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "per": info.get("trailingPE"),
            "forward_per": info.get("forwardPE"),
            "pbr": info.get("priceToBook"),
            "eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_financial_health(ticker: str) -> dict:
    """재무 건전성.
    반환: 매출, 영업이익, 순이익, 매출 성장률(YoY), 영업이익률, 순이익률
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "total_revenue": info.get("totalRevenue"),
            "operating_income": info.get("operatingCashflow"),
            "net_income": info.get("netIncomeToCommon"),
            "revenue_growth_yoy": info.get("revenueGrowth"),
            "operating_margin": info.get("operatingMargins"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "return_on_equity": info.get("returnOnEquity"),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_recent_news(ticker: str, limit: int = 5) -> list:
    """yfinance 자체 뉴스 (Tavily 외 보조 소스).
    반환: 제목, 링크, 발행일, 발행처
    """
    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []

        results = []
        for item in news[:limit]:
            content = item.get("content", {})
            results.append({
                "title": content.get("title", item.get("title", "")),
                "url": content.get("canonicalUrl", {}).get("url", "")
                       if isinstance(content.get("canonicalUrl"), dict)
                       else item.get("link", ""),
                "publisher": content.get("provider", {}).get("displayName", "")
                             if isinstance(content.get("provider"), dict)
                             else item.get("publisher", ""),
                "published_at": content.get("pubDate", ""),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]

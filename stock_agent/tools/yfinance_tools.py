import difflib
import yfinance as yf
from langchain_core.tools import tool

from stock_agent.tools.ticker_mapping import TICKER_MAP, TICKER_TO_KOREAN


def _ensure_ticker(raw: str) -> str:
    """입력이 티커가 아닌 경우 자동으로 변환합니다. LLM이 resolve_ticker를 건너뛸 때 안전장치."""
    stripped = raw.strip()
    # 이미 한국 종목코드 형태
    if stripped.endswith('.KS') or stripped.endswith('.KQ'):
        return stripped
    # 6자리 숫자 → 한국 종목코드
    if stripped.isdigit() and len(stripped) == 6:
        return f"{stripped}.KS"
    # 이미 미국 티커 형태 (영문+하이픈 1~5자)
    upper = stripped.upper()
    if 1 <= len(upper) <= 5 and all(c.isalpha() or c == '-' for c in upper):
        return upper
    # 한글 등 → TICKER_MAP에서 조회
    name_lower = stripped.lower()
    if name_lower in TICKER_MAP:
        return TICKER_MAP[name_lower]
    # 유사 매칭
    close_matches = difflib.get_close_matches(name_lower, TICKER_MAP.keys(), n=3, cutoff=0.4)
    if close_matches:
        suggestions = [f"{m}({TICKER_MAP[m]})" for m in close_matches]
        return f"ERROR: '{stripped}'에 해당하는 티커를 찾을 수 없습니다. 유사한 기업: {', '.join(suggestions)}"
    return f"ERROR: '{stripped}'에 해당하는 티커를 찾을 수 없습니다."


def _format_amount(value, is_korean: bool) -> str | None:
    """큰 금액을 한국식 단위(조/억)로 포맷합니다."""
    if value is None:
        return None
    abs_val = abs(value)
    sign = "-" if value < 0 else ""

    if is_korean:
        if abs_val >= 1_000_000_000_000:
            return f"{sign}약 {abs_val / 1_000_000_000_000:,.1f}조원"
        elif abs_val >= 100_000_000:
            return f"{sign}약 {abs_val / 100_000_000:,.0f}억원"
        else:
            return f"{sign}{abs_val:,.0f}원"
    else:
        if abs_val >= 100_000_000:
            return f"{sign}약 {abs_val / 100_000_000:,.1f}억 달러"
        elif abs_val >= 10_000:
            return f"{sign}약 {abs_val / 10_000:,.0f}만 달러"
        else:
            return f"{sign}{abs_val:,.0f} 달러"


def _format_pct(value) -> str | None:
    """소수점 비율을 백분율 문자열로 변환합니다. (0.25 → '25.0%')"""
    if value is None:
        return None
    return f"{value * 100:.1f}%"


def _get_usd_krw_rate() -> float | None:
    """현재 USD/KRW 환율을 가져옵니다."""
    try:
        fx = yf.Ticker("USDKRW=X")
        rate = fx.info.get("regularMarketPrice") or fx.info.get("previousClose")
        return rate
    except Exception:
        return None


def get_company_data(ticker: str) -> dict:
    """기업 데이터를 한 번의 info 호출로 수집합니다 (overview + valuation + financial_health).

    yf.Ticker(ticker).info를 1회만 호출하여 HTTP 요청을 최소화합니다.
    """
    ticker = _ensure_ticker(ticker)
    if ticker.startswith("ERROR"):
        return {"error": ticker}
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        is_korean = ticker.endswith(".KS") or ticker.endswith(".KQ")

        # 환율 (미국 주식만, 1회만 조회)
        usd_krw_rate = None
        if not is_korean:
            usd_krw_rate = _get_usd_krw_rate()

        # ── Overview ──
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change = round(current - prev_close, 2) if current and prev_close else None
        change_pct = round((change / prev_close) * 100, 2) if change and prev_close else None

        market_cap = info.get("marketCap")
        cap_tier = None
        cap_str = None
        if market_cap:
            cap_krw = market_cap if is_korean else market_cap * (usd_krw_rate or 1400)
            if cap_krw >= 10_000_000_000_000:
                cap_tier = "대형주"
            elif cap_krw >= 2_000_000_000_000:
                cap_tier = "중형주"
            else:
                cap_tier = "소형주"
            if cap_krw >= 1_000_000_000_000:
                cap_str = f"약 {int(cap_krw // 1_000_000_000_000):,}조원"
            elif cap_krw >= 100_000_000:
                cap_str = f"약 {int(cap_krw // 100_000_000):,}억원"
            else:
                cap_str = f"{cap_krw:,.0f}원"

        korean_name = TICKER_TO_KOREAN.get(ticker)
        if korean_name:
            long_name = info.get("longName") or ""
            company_name = f"{korean_name} ({long_name})" if long_name else korean_name
        elif is_korean:
            short_name = info.get("shortName") or ""
            long_name = info.get("longName") or ""
            company_name = short_name if short_name else long_name
        else:
            company_name = info.get("longName") or info.get("shortName") or ""

        krw_price = None
        if not is_korean and current and usd_krw_rate:
            krw_price = round(current * usd_krw_rate)

        overview = {
            "company_name": company_name,
            "ticker": ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "business_summary": (info.get("longBusinessSummary") or "")[:300],
            "current_price": current,
            "currency": "KRW" if is_korean else "USD",
            "krw_price": krw_price,
            "usd_krw_rate": usd_krw_rate,
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

        # ── Valuation ──
        valuation = {
            "ticker": ticker,
            "per": info.get("trailingPE"),
            "forward_per": info.get("forwardPE"),
            "pbr": info.get("priceToBook"),
            "eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
        }

        # ── Financial Health ──
        financial_health = {
            "ticker": ticker,
            "total_revenue": _format_amount(info.get("totalRevenue"), is_korean),
            "operating_income": _format_amount(info.get("operatingIncome"), is_korean),
            "net_income": _format_amount(info.get("netIncomeToCommon"), is_korean),
            "revenue_growth_yoy": _format_pct(info.get("revenueGrowth")),
            "operating_margin": _format_pct(info.get("operatingMargins")),
            "profit_margin": _format_pct(info.get("profitMargins")),
            "debt_to_equity": info.get("debtToEquity"),
            "return_on_equity": _format_pct(info.get("returnOnEquity")),
        }

        return {
            "overview": overview,
            "valuation": valuation,
            "financial_health": financial_health,
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_recent_news(ticker: str, limit: int = 5) -> list:
    """yfinance 자체 뉴스 (Tavily 외 보조 소스).
    반환: 제목, 링크, 발행일, 발행처
    """
    ticker = _ensure_ticker(ticker)
    if ticker.startswith("ERROR"):
        return [{"error": ticker}]
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

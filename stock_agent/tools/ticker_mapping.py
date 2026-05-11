import difflib
import json
import re
from pathlib import Path
from langchain_core.tools import tool

# ── tickers.json에서 TICKER_MAP 자동 생성 ──
_TICKERS_PATH = Path(__file__).parent / "tickers.json"

def _load_ticker_map() -> dict[str, str]:
    """tickers.json → {별칭(소문자): 티커} 플랫 딕셔너리."""
    with open(_TICKERS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    result: dict[str, str] = {}
    for section in data.values():
        for ticker, aliases in section.items():
            for alias in aliases:
                result[alias.lower()] = ticker
    return result

TICKER_MAP = _load_ticker_map()


# ── 티커 → 한글명 역방향 매핑 (가장 긴 한글명 사용) ──
def _display_name(name: str) -> str:
    """영문 접두어를 대문자로 변환 (예: 'sk하이닉스' → 'SK하이닉스')."""
    return re.sub(r'[a-zA-Z]+', lambda m: m.group().upper(), name)

def _build_ticker_to_korean() -> dict[str, str]:
    result: dict[str, str] = {}
    for name, ticker in TICKER_MAP.items():
        if name.isascii():
            continue
        if ticker not in result or len(name) > len(result[ticker]):
            result[ticker] = _display_name(name)
    return result

TICKER_TO_KOREAN = _build_ticker_to_korean()


@tool
def resolve_ticker(company_name: str) -> str:
    """회사명을 주식 티커 심볼로 변환합니다.
    미국 주식 (예: '애플' → 'AAPL')과 한국 주식 (예: '삼성전자' → '005930.KS')을 모두 지원합니다.
    이미 티커 형태인 경우 그대로 반환합니다.
    """
    name_lower = company_name.strip().lower()

    if name_lower in TICKER_MAP:
        return TICKER_MAP[name_lower]

    # 이미 미국 티커 형태인 경우 (대문자 영문 1~5자)
    name_upper = company_name.strip().upper()
    if name_upper.isalpha() and 1 <= len(name_upper) <= 5:
        return name_upper

    # 한국 종목코드 직접 입력 (6자리 숫자)
    name_stripped = company_name.strip()
    if name_stripped.isdigit() and len(name_stripped) == 6:
        return f"{name_stripped}.KS"

    # 유사한 기업명 추천
    close_matches = difflib.get_close_matches(name_lower, TICKER_MAP.keys(), n=3, cutoff=0.4)
    if close_matches:
        suggestions = [f"{m}({TICKER_MAP[m]})" for m in close_matches]
        return f"ERROR: '{company_name}'에 해당하는 티커를 찾을 수 없습니다. 유사한 기업: {', '.join(suggestions)}"

    return f"ERROR: '{company_name}'에 해당하는 티커를 찾을 수 없습니다."

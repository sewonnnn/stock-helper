from langchain_core.tools import tool

TICKER_MAP = {
    # ===== 미국 주식 =====
    "애플": "AAPL", "apple": "AAPL",
    "테슬라": "TSLA", "tesla": "TSLA",
    "엔비디아": "NVDA", "nvidia": "NVDA",
    "마이크로소프트": "MSFT", "microsoft": "MSFT",
    "구글": "GOOGL", "google": "GOOGL", "알파벳": "GOOGL", "alphabet": "GOOGL",
    "아마존": "AMZN", "amazon": "AMZN",
    "메타": "META", "meta": "META", "페이스북": "META", "facebook": "META",
    "넷플릭스": "NFLX", "netflix": "NFLX",
    "디즈니": "DIS", "disney": "DIS",
    "나이키": "NKE", "nike": "NKE",
    "코카콜라": "KO", "coca-cola": "KO", "cocacola": "KO",
    "펩시": "PEP", "pepsi": "PEP", "펩시코": "PEP",
    "맥도날드": "MCD", "mcdonalds": "MCD",
    "스타벅스": "SBUX", "starbucks": "SBUX",
    "월마트": "WMT", "walmart": "WMT",
    "코스트코": "COST", "costco": "COST",
    "비자": "V", "visa": "V",
    "마스터카드": "MA", "mastercard": "MA",
    "제이피모건": "JPM", "jpmorgan": "JPM", "jp모건": "JPM",
    "골드만삭스": "GS", "goldman sachs": "GS", "골드만": "GS",
    "뱅크오브아메리카": "BAC", "bank of america": "BAC",
    "버크셔": "BRK-B", "berkshire": "BRK-B", "버크셔해서웨이": "BRK-B",
    "존슨앤존슨": "JNJ", "johnson": "JNJ",
    "화이자": "PFE", "pfizer": "PFE",
    "모더나": "MRNA", "moderna": "MRNA",
    "유나이티드헬스": "UNH", "unitedhealth": "UNH",
    "보잉": "BA", "boeing": "BA",
    "록히드마틴": "LMT", "lockheed": "LMT",
    "인텔": "INTC", "intel": "INTC",
    "amd": "AMD", "에이엠디": "AMD",
    "퀄컴": "QCOM", "qualcomm": "QCOM",
    "브로드컴": "AVGO", "broadcom": "AVGO",
    "세일즈포스": "CRM", "salesforce": "CRM",
    "어도비": "ADBE", "adobe": "ADBE",
    "오라클": "ORCL", "oracle": "ORCL",
    "팔란티어": "PLTR", "palantir": "PLTR",
    "스노우플레이크": "SNOW", "snowflake": "SNOW",
    "우버": "UBER", "uber": "UBER",
    "에어비앤비": "ABNB", "airbnb": "ABNB",
    "로블록스": "RBLX", "roblox": "RBLX",
    "쇼피파이": "SHOP", "shopify": "SHOP",
    "줌": "ZM", "zoom": "ZM",
    "스포티파이": "SPOT", "spotify": "SPOT",
    "엑손모빌": "XOM", "exxon": "XOM",
    "쉐브론": "CVX", "chevron": "CVX",
    "프록터앤갬블": "PG", "procter": "PG", "p&g": "PG",
    "홈디포": "HD", "home depot": "HD",
    "리비안": "RIVN", "rivian": "RIVN",
    "루시드": "LCID", "lucid": "LCID",
    "코인베이스": "COIN", "coinbase": "COIN",

    # ===== 한국 주식 (코스피 .KS / 코스닥 .KQ) =====
    "삼성전자": "005930.KS", "삼성": "005930.KS", "samsung": "005930.KS",
    "sk하이닉스": "000660.KS", "하이닉스": "000660.KS", "skhynix": "000660.KS",
    "lg에너지솔루션": "373220.KS", "lg에너지": "373220.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS", "hyundai": "005380.KS",
    "기아": "000270.KS", "kia": "000270.KS",
    "셀트리온": "068270.KS", "celltrion": "068270.KS",
    "카카오": "035720.KS", "kakao": "035720.KS",
    "네이버": "035420.KS", "naver": "035420.KS",
    "삼성바이오로직스": "207940.KS", "삼성바이오": "207940.KS",
    "포스코홀딩스": "005490.KS", "포스코": "005490.KS", "posco": "005490.KS",
    "삼성sdi": "006400.KS", "삼성에스디아이": "006400.KS",
    "lg화학": "051910.KS", "lg켐": "051910.KS",
    "현대모비스": "012330.KS",
    "kb금융": "105560.KS", "kb": "105560.KS",
    "신한지주": "055550.KS", "신한": "055550.KS",
    "하나금융": "086790.KS", "하나": "086790.KS",
    "삼성물산": "028260.KS",
    "sk텔레콤": "017670.KS", "skt": "017670.KS",
    "kt": "030200.KS",
    "lg전자": "066570.KS", "lg": "066570.KS",
    "한화에어로스페이스": "012450.KS", "한화에어로": "012450.KS",
    "한화오션": "042660.KS",
    "두산에너빌리티": "034020.KS", "두산에너": "034020.KS",
    "에코프로비엠": "247540.KQ", "에코프로bm": "247540.KQ",
    "에코프로": "086520.KQ",
    "엘앤에프": "066970.KQ", "l&f": "066970.KQ",
    "카카오뱅크": "323410.KS",
    "카카오페이": "377300.KS",
    "크래프톤": "259960.KS", "krafton": "259960.KS",
    "hd현대중공업": "329180.KS", "현대중공업": "329180.KS",
}


# 티커 → 한글명 역방향 매핑 (한국 주식 표시용)
TICKER_TO_KOREAN = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션",
    "005380.KS": "현대자동차",
    "000270.KS": "기아",
    "068270.KS": "셀트리온",
    "035720.KS": "카카오",
    "035420.KS": "네이버",
    "207940.KS": "삼성바이오로직스",
    "005490.KS": "포스코홀딩스",
    "006400.KS": "삼성SDI",
    "051910.KS": "LG화학",
    "012330.KS": "현대모비스",
    "105560.KS": "KB금융",
    "055550.KS": "신한지주",
    "086790.KS": "하나금융",
    "028260.KS": "삼성물산",
    "017670.KS": "SK텔레콤",
    "030200.KS": "KT",
    "066570.KS": "LG전자",
    "012450.KS": "한화에어로스페이스",
    "042660.KS": "한화오션",
    "034020.KS": "두산에너빌리티",
    "247540.KQ": "에코프로비엠",
    "086520.KQ": "에코프로",
    "066970.KQ": "엘앤에프",
    "323410.KS": "카카오뱅크",
    "377300.KS": "카카오페이",
    "259960.KS": "크래프톤",
    "329180.KS": "HD현대중공업",
}


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

    return f"ERROR: '{company_name}'에 해당하는 티커를 찾을 수 없습니다."

# 모델 설정 — 모델 분리 적용
DEFAULT_MODEL = "gpt-4o"
LIGHT_MODEL = "gpt-4o-mini"
VALIDATOR_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# 그래프 설정
MAX_RETRIES = 1

# Pinecone
PINECONE_INDEX_NAME = "stock-glossary"

# Tavily 신뢰 도메인
TRUSTED_NEWS_DOMAINS = [
    # 미국/글로벌
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "ft.com",
    "barrons.com",
    # 한국
    "hankyung.com",
    "mk.co.kr",
    "sedaily.com",
    "news.einfomax.co.kr",
    "biz.chosun.com",
    "mt.co.kr",
]

# Advisor용 신뢰 도메인 (뉴스 + 금융 교육/증권사)
TRUSTED_ADVISOR_DOMAINS = TRUSTED_NEWS_DOMAINS + [
    "investopedia.com",
    "nerdwallet.com",
    "kbsec.com",
    "samsungpop.com",
    "miraeassetdaewoo.com",
    "nhqv.com",
    "shinhaninvest.com",
    "tossinvest.com",
    "banksalad.com",
]

# 면책문구
DISCLAIMER = (
    "본 내용은 투자 권유가 아닙니다. "
    "투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다."
)

# 응답 메시지
UNKNOWN_RESPONSE = "확인 불가합니다. 정확한 데이터를 찾을 수 없습니다."

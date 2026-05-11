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

# Tavily 제외 도메인 (소셜미디어·UGC)
EXCLUDED_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "reddit.com",
    "namu.wiki",
    "blog.naver.com",
    "cafe.naver.com",
    "tistory.com",
]

# 면책문구
DISCLAIMER = (
    "본 내용은 투자 권유가 아닙니다. "
    "투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다."
)

# 응답 메시지
UNKNOWN_RESPONSE = "확인 불가합니다. 정확한 데이터를 찾을 수 없습니다."
REJECT_RESPONSE = "저는 주식·금융 관련 질문에만 답변할 수 있어요. 주식, 투자, 경제에 관한 궁금한 점을 물어보세요!"

# 입력 제한
MAX_QUESTION_LENGTH = 500

# 에러 메시지 (사용자 노출용 한국어)
ERROR_MESSAGES = {
    "routing_failed": "질문을 분류하는 중 오류가 발생했습니다. 다시 시도해 주세요.",
    "company_failed": "기업 정보를 조회하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "news_failed": "뉴스를 검색하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "general_failed": "정보를 검색하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "advisor_failed": "맞춤 안내를 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "glossary_failed": "용어 정보를 조회하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "pinecone_failed": "용어 데이터베이스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    "server_error": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "input_too_long": f"질문이 너무 깁니다. {MAX_QUESTION_LENGTH}자 이내로 입력해 주세요.",
}

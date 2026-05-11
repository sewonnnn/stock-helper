from langchain_tavily import TavilySearch

from stock_agent.utils.constants import TRUSTED_NEWS_DOMAINS, TRUSTED_ADVISOR_DOMAINS, EXCLUDED_DOMAINS

# 뉴스 검색 — 최근 1주일 이내
tavily_search_news = TavilySearch(
    max_results=4,
    include_domains=TRUSTED_NEWS_DOMAINS,
    exclude_domains=EXCLUDED_DOMAINS,
    time_range="week",
)

# 일반/트렌드 검색 — 최근 1개월 이내
tavily_search_general = TavilySearch(
    max_results=5,
    include_domains=TRUSTED_NEWS_DOMAINS,
    exclude_domains=EXCLUDED_DOMAINS,
    time_range="month",
)

# 투자 가이드/전략 검색 — 최근 1년 이내 (신뢰 도메인 한정)
tavily_search_advisor = TavilySearch(
    max_results=5,
    include_domains=TRUSTED_ADVISOR_DOMAINS,
    exclude_domains=EXCLUDED_DOMAINS,
    time_range="year",
)

# 하위 호환 (기존 import용)
tavily_search = tavily_search_general

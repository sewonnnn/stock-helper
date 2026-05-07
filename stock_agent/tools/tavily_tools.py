from langchain_tavily import TavilySearch

from stock_agent.utils.constants import TRUSTED_NEWS_DOMAINS

# Tavily 뉴스 검색(신뢰 도메인 한정)
tavily_search = TavilySearch(
    max_results=5,
    include_domains=TRUSTED_NEWS_DOMAINS,
)

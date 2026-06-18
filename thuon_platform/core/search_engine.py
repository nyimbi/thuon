# core/search_engine.py

import logging
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from core.settings_manager import get_settings

logger = logging.getLogger('thuon.search_engine')


class SearchEngine(ABC):
	@abstractmethod
	def __init__(self, engine_name: str):
		self.engine_name = engine_name

	@abstractmethod
	def search(self, query: str, num_results: int = 5, time_range: str | None = None) -> list[dict]:
		"""Search and return list of {title, body, href} dicts.

		Args:
			query:      Search query string.
			num_results: Maximum results to return.
			time_range: Recency filter — 'day', 'week', 'month', 'year'. Not all
			            engines support this; unsupported engines silently ignore it.
		"""
		pass


class DuckDuckGoSearch(SearchEngine):
	def __init__(self):
		super().__init__('DuckDuckGo')

	def search(self, query: str, num_results: int = 5, time_range: str | None = None) -> list[dict]:
		try:
			from ddgs import DDGS
			results = list(DDGS().text(query, max_results=num_results))
			return [{'title': r.get('title', ''), 'body': r.get('body', ''), 'href': r.get('href', '')} for r in results]
		except Exception as e:
			logger.error(f"DuckDuckGo search error: {e}")
			return []


class TavilySearch(SearchEngine):
	def __init__(self):
		super().__init__('Tavily')
		self.api_key = get_settings().get_setting('api_keys.tavily')

	def search(self, query: str, num_results: int = 5, time_range: str | None = None) -> list[dict]:
		if not self.api_key:
			logger.warning("Tavily API key not configured, falling back to DuckDuckGo")
			return DuckDuckGoSearch().search(query, num_results)
		try:
			from tavily import TavilyClient
			response = TavilyClient(api_key=self.api_key).search(query, max_results=num_results)
			return [{'title': r.get('title', ''), 'body': r.get('content', ''), 'href': r.get('url', '')} for r in response.get('results', [])]
		except Exception as e:
			logger.error(f"Tavily search error: {e}")
			return []


class GoogleSerperSearch(SearchEngine):
	def __init__(self):
		super().__init__('GoogleSerper')
		self.api_key = get_settings().get_setting('api_keys.google_serper')

	def search(self, query: str, num_results: int = 5, time_range: str | None = None) -> list[dict]:
		if not self.api_key:
			logger.warning("Google Serper key not configured, falling back to DuckDuckGo")
			return DuckDuckGoSearch().search(query, num_results)
		try:
			resp = requests.post(
				'https://google.serper.dev/search',
				headers={'X-API-KEY': self.api_key, 'Content-Type': 'application/json'},
				json={'q': query, 'num': num_results},
				timeout=10,
			)
			resp.raise_for_status()
			return [{'title': r.get('title', ''), 'body': r.get('snippet', ''), 'href': r.get('link', '')} for r in resp.json().get('organic', [])[:num_results]]
		except Exception as e:
			logger.error(f"GoogleSerper error: {e}")
			return []


class SearXNGSearch(SearchEngine):
	"""Search via a self-hosted SearXNG instance.

	Configure in settings:
	  search.searxng_url: "http://localhost:8888"   # required
	  search.searxng_categories: "general"           # optional
	  search.searxng_language: "en"                  # optional
	"""

	def __init__(self, instance_url: str | None = None):
		super().__init__('SearXNG')
		self._url = (
			instance_url
			or get_settings().get_setting('search.searxng_url', '')
		).rstrip('/')
		self._categories          = get_settings().get_setting('search.searxng_categories', 'general')
		self._language            = get_settings().get_setting('search.searxng_language', 'en')
		self._default_time_range  = get_settings().get_setting('search.searxng_time_range', '')

	def search(self, query: str, num_results: int = 5, time_range: str | None = None) -> list[dict]:
		if not self._url:
			logger.warning('SearXNG URL not configured (search.searxng_url). Falling back to DuckDuckGo.')
			return DuckDuckGoSearch().search(query, num_results)
		params: dict = {
			'q':          query,
			'format':     'json',
			'categories': self._categories,
			'language':   self._language,
		}
		tr = time_range or self._default_time_range
		if tr:
			params['time_range'] = tr
		try:
			resp = requests.get(
				f'{self._url}/search',
				params=params,
				headers={'Accept': 'application/json'},
				timeout=10,
			)
			resp.raise_for_status()
			results = resp.json().get('results', [])
			return [
				{
					'title': r.get('title', ''),
					'body':  r.get('content', ''),
					'href':  r.get('url', ''),
				}
				for r in results[:num_results]
			]
		except Exception as e:
			logger.error(f'SearXNG search error: {e}')
			return []


class FirecrawlScraper:
	"""Clean markdown extraction via the self-hosted Firecrawl service.

	Firecrawl uses a stealth Playwright backend — handles JS-rendered pages
	and anti-bot measures. Configured via search.firecrawl_url in settings.
	"""

	def __init__(self, base_url: str | None = None):
		self._url = (
			base_url
			or get_settings().get_setting('search.firecrawl_url', '')
		).rstrip('/')

	@property
	def enabled(self) -> bool:
		return bool(self._url)

	def scrape(self, url: str, only_main_content: bool = True, timeout: int = 30) -> str:
		"""Scrape a URL and return clean markdown. Returns '' on failure."""
		if not self._url:
			return scrape_webpage(url)
		try:
			resp = requests.post(
				f'{self._url}/v1/scrape',
				json={
					'url':             url,
					'formats':         ['markdown'],
					'onlyMainContent': only_main_content,
					'timeout':         timeout * 1000,
				},
				timeout=timeout + 5,
			)
			resp.raise_for_status()
			data = resp.json()
			if data.get('success'):
				return data['data'].get('markdown', '')
			logger.warning(f'Firecrawl returned success=false for {url}')
			return ''
		except Exception as e:
			logger.error(f'Firecrawl scrape error for {url}: {e}')
			return ''


def scrape_webpage(url: str) -> str:
	"""Basic HTML→text scraper. Prefer FirecrawlScraper for production use."""
	try:
		resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
		resp.raise_for_status()
		soup = BeautifulSoup(resp.text, 'html.parser')
		for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
			tag.decompose()
		return soup.get_text(separator=' ', strip=True)[:5000]
	except Exception as e:
		logger.error(f"Scrape error for {url}: {e}")
		return ''

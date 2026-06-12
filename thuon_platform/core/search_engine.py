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
	def search(self, query: str, num_results: int = 5) -> list[dict]:
		pass


class DuckDuckGoSearch(SearchEngine):
	def __init__(self):
		super().__init__('DuckDuckGo')

	def search(self, query: str, num_results: int = 5) -> list[dict]:
		try:
			from duckduckgo_search import DDGS
			results = list(DDGS().text(query, max_results=num_results))
			return [{'title': r.get('title', ''), 'body': r.get('body', ''), 'href': r.get('href', '')} for r in results]
		except Exception as e:
			logger.error(f"DuckDuckGo search error: {e}")
			return []


class TavilySearch(SearchEngine):
	def __init__(self):
		super().__init__('Tavily')
		self.api_key = get_settings().get_setting('api_keys.tavily')

	def search(self, query: str, num_results: int = 5) -> list[dict]:
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

	def search(self, query: str, num_results: int = 5) -> list[dict]:
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


def scrape_webpage(url: str) -> str:
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

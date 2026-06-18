# tests/ci/test_search_engine.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import json
from unittest.mock import patch, MagicMock
from core.search_engine import DuckDuckGoSearch, TavilySearch, GoogleSerperSearch, scrape_webpage


def _ddg_results():
	return [
		{'title': 'Result 1', 'body': 'Some content about Python', 'href': 'https://example.com/1'},
		{'title': 'Result 2', 'body': 'More content', 'href': 'https://example.com/2'},
	]


def _patch_ddgs(results):
	return patch('ddgs.DDGS', return_value=MagicMock(text=MagicMock(return_value=results)))


def test_duckduckgo_search_returns_list():
	with _patch_ddgs(_ddg_results()):
		engine = DuckDuckGoSearch()
		results = engine.search('python programming', num_results=2)
	assert isinstance(results, list)
	assert len(results) > 0


def test_duckduckgo_search_empty_query():
	with _patch_ddgs([]):
		engine = DuckDuckGoSearch()
		results = engine.search('', num_results=3)
	assert isinstance(results, list)


def test_tavily_falls_back_to_ddg_without_key():
	with _patch_ddgs(_ddg_results()):
		engine = TavilySearch()
		results = engine.search('test query', num_results=2)
	assert isinstance(results, list)


def test_google_serper_falls_back_to_ddg_without_key():
	with _patch_ddgs(_ddg_results()):
		engine = GoogleSerperSearch()
		results = engine.search('test query', num_results=2)
	assert isinstance(results, list)


def test_scrape_webpage_returns_string():
	mock_response = MagicMock()
	mock_response.text = '<html><body><p>Hello world content</p></body></html>'
	mock_response.raise_for_status = MagicMock()
	with patch('core.search_engine.requests.get', return_value=mock_response):
		text = scrape_webpage('https://example.com')
	assert 'Hello world content' in text


def test_scrape_webpage_truncates_at_5000():
	long_content = 'x' * 10000
	mock_response = MagicMock()
	mock_response.text = f'<html><body><p>{long_content}</p></body></html>'
	mock_response.raise_for_status = MagicMock()
	with patch('core.search_engine.requests.get', return_value=mock_response):
		text = scrape_webpage('https://example.com')
	assert len(text) <= 5000

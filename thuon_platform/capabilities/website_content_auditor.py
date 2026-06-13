# capabilities/website_content_auditor.py
"""
Atomic capability: fetch and analyze current website page content.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class WebsiteContentAuditor:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def audit(
		self,
		url: str,
		page_path: str = '/',
	) -> dict:
		"""
		Fetch a website page and analyze its current content quality.

		Returns:
			{current_content, word_count, tone, top_keywords,
			 readability_issues, seo_issues, last_updated_est, raw_html_excerpt}
		"""
		current_content = self._fetch(url)

		prompt = (
			f'You are a content strategist auditing a website page.\n\n'
			f'URL: {url}\n'
			f'Page path: {page_path}\n\n'
			f'PAGE CONTENT:\n{current_content[:5000]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- current_content (str): cleaned, readable text of the page\n'
			'- word_count (int)\n'
			'- tone (str): formal|conversational|technical|marketing\n'
			'- top_keywords (list of str): top 5 keywords used\n'
			'- readability_issues (list of str): jargon, passive voice, long sentences, etc.\n'
			'- seo_issues (list of str): missing keywords, thin content, etc.\n'
			'- last_updated_est (str): best guess at when content was last updated\n'
			'- content_gaps (list of str): topics that are absent but should be there\n'
			'- overall_quality_score (int 0-100)'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'current_content':    current_content[:2000],
			'word_count':         len(current_content.split()),
			'tone':               'unknown',
			'top_keywords':       [],
			'readability_issues': [],
			'seo_issues':         [],
			'last_updated_est':   'unknown',
			'content_gaps':       [],
			'overall_quality_score': 0,
		}

	def _fetch(self, url: str) -> str:
		try:
			import trafilatura
			downloaded = trafilatura.fetch_url(url)
			if downloaded:
				text = trafilatura.extract(downloaded)
				if text:
					return text
		except ImportError:
			pass
		try:
			import requests
			from bs4 import BeautifulSoup
			r = requests.get(url, timeout=15, headers={'User-Agent': 'Thuon/1.0'})
			r.raise_for_status()
			soup = BeautifulSoup(r.text, 'html.parser')
			for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
				tag.decompose()
			return soup.get_text('\n', strip=True)[:15000]
		except Exception:
			return f'[Could not fetch {url}]'

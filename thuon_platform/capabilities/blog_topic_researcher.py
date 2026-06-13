# capabilities/blog_topic_researcher.py
"""
Atomic capability: research and generate blog topic ideas for a domain.
"""

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json, extract_json_array


class BlogTopicResearcher:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine     = ai_engine
		self.search_engine = search_engine

	def research(
		self,
		domain: str,
		audience: str = '',
		num_topics: int = 5,
		company_context: str = '',
	) -> dict:
		"""
		Generate SEO-informed blog topic ideas for a domain and audience.

		Returns:
			{topics: [{title, angle, target_keyword, competition_level,
			           search_intent, why_now, outline_hint}]}
		"""
		results = self.search_engine.search(
			f'{domain} trending topics questions 2024 2025',
			num_results=5,
		)
		context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:200]}"
			for r in results
		)

		prompt = (
			f'You are a content strategist and SEO expert.\n\n'
			f'Domain: {domain}\n'
			f'Target audience: {audience or "business professionals"}\n'
			f'Company context: {company_context[:500] or "Not provided"}\n\n'
			f'Trending context:\n{context}\n\n'
			f'Generate {num_topics} high-quality blog topic ideas. '
			f'Return ONLY a valid JSON object with:\n'
			'- topics (list): each with:\n'
			'  - title (str): compelling blog post title\n'
			'  - angle (str): unique angle or hook that differentiates this post\n'
			'  - target_keyword (str): primary SEO keyword\n'
			'  - secondary_keywords (list of str): 2-3 related keywords\n'
			'  - competition_level (str): low | medium | high\n'
			'  - search_intent (str): informational | navigational | commercial | transactional\n'
			'  - why_now (str): why this topic is timely\n'
			'  - outline_hint (str): brief 2-sentence outline'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {'topics': []}

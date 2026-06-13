# capabilities/social_trend_researcher.py
"""
Atomic capability: research trending context for a social media post idea.
"""

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json, extract_json_array


class SocialTrendResearcher:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine     = ai_engine
		self.search_engine = search_engine

	def research(
		self,
		idea: str,
		platforms: list | str = '',
	) -> dict:
		"""
		Research the trending context for a social post idea.

		Returns:
			{context_summary, trends, hashtag_suggestions, best_time_to_post,
			 audience_insights, content_angles}
		"""
		platforms_list = platforms if isinstance(platforms, list) else ['linkedin', 'twitter']

		results = self.search_engine.search(
			f'{idea} trending news 2024 2025',
			num_results=5,
		)
		context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:200]}"
			for r in results
		)

		prompt = (
			f'You are a social media strategist researching a post idea.\n\n'
			f'Idea: {idea}\n'
			f'Target platforms: {json.dumps(platforms_list)}\n\n'
			f'Recent context:\n{context}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- context_summary (str): 2-3 sentences summarizing the current landscape for this topic\n'
			'- trends (list): each with {platform, trending_angle, hashtags: list, '
			'best_post_time: str, engagement_type: educational|inspirational|controversial|humorous}\n'
			'- hashtag_suggestions (object): {linkedin: [list], twitter: [list]} — 5-10 each\n'
			'- audience_insights (str): who cares about this topic and why\n'
			'- content_angles (list of str): 3-5 distinct angles to approach this idea'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'context_summary':    response[:300],
			'trends':             [],
			'hashtag_suggestions': {},
			'audience_insights':  '',
			'content_angles':     [],
		}

# capabilities/social_media_manager.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class SocialMediaManager:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def analyze_social_trends(self, keywords: list, platforms: list = ['Twitter', 'Facebook', 'Instagram', 'LinkedIn']) -> dict:
		query = f"social media trends {' '.join(keywords)} {' '.join(platforms[:2])}"
		results = self.search_engine.search(query, num_results=5)
		context = '\n'.join(f"- {r.get('title','')}: {r.get('body','')[:250]}" for r in results)

		prompt = (
			f"You are a social media analyst. Analyze social media trends for the following keywords across platforms.\n\n"
			f"Keywords: {keywords}\n"
			f"Platforms: {platforms}\n\n"
			f"Research context:\n{context}\n\n"
			f"Return JSON with keys: trend_summary, platform_breakdown (object per platform with: sentiment, "
			f"top_topics, engagement_level, recommended_content_types), "
			f"trending_hashtags (list), audience_insights, content_recommendations (list), posting_schedule."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'keywords': keywords, 'platforms': platforms, 'status': 'success'}

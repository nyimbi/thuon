# capabilities/social_media_manager.py

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
		from core.output_validator import validated_llm_call
		result = validated_llm_call(self.ai_engine, prompt, fallback_key='result', required_keys=[], max_retries=2)
		if result.get('status') == 'parse_failed':
			return {'result': result.get('result', ''), 'keywords': keywords, 'platforms': platforms, 'status': 'success'}
		return result

# capabilities/brand_sentiment_orchestrator.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class BrandSentimentOrchestrator:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def analyze_brand_sentiment(self, brand_name: str, sources: list = ['social_media', 'news_articles', 'customer_reviews']) -> dict:
		results = self.search_engine.search(f"{brand_name} reviews sentiment customer opinion", num_results=6)
		context = '\n'.join(f"- {r.get('title','')}: {r.get('body','')[:250]}" for r in results)

		prompt = (
			f"You are a brand analyst. Analyze the sentiment and perception of {brand_name} across sources.\n\n"
			f"Sources to analyze: {sources}\n\n"
			f"Research context:\n{context}\n\n"
			f"Return JSON with keys: brand_name, overall_sentiment (positive/negative/neutral/mixed), "
			f"sentiment_score (-1.0 to 1.0), source_breakdown (object per source with: sentiment, key_themes (list), "
			f"representative_mentions (list)), trending_topics (list), brand_strengths (list), "
			f"brand_weaknesses (list), recommendations (list), monitoring_keywords (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'brand': brand_name, 'sources': sources, 'status': 'success'}

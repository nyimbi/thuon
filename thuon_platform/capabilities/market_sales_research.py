# capabilities/market_sales_research.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class MarketSalesResearch:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def analyze_market_trends(self, product_category: str, region: str, metrics: list = ['market_size', 'growth_rate', 'customer_segments']) -> dict:
		query = f"{product_category} market trends {region} market size growth 2024 2025"
		results = self.search_engine.search(query, num_results=5)
		context = '\n'.join(f"- {r.get('title','')}: {r.get('body','')[:300]}" for r in results)

		metrics_str = ', '.join(metrics)
		prompt = (
			f"You are a market research analyst. Analyze market trends for the following.\n\n"
			f"Product Category: {product_category}\nRegion: {region}\nMetrics: {metrics_str}\n\n"
			f"Research context:\n{context}\n\n"
			f"Return JSON with keys: market_overview, market_size (with unit and year), "
			f"growth_rate (CAGR percentage), market_size_forecast_5yr, customer_segments (list with: "
			f"segment_name, size_percentage, key_needs (list), buying_behavior), "
			f"competitive_landscape (list of top players with market_share), key_trends (list), "
			f"opportunities (list), threats (list), entry_barriers (list), sales_channels (list), "
			f"pricing_insights, recommendations (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'product_category': product_category, 'region': region, 'metrics': metrics, 'status': 'success'}

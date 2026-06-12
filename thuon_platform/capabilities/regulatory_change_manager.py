# capabilities/regulatory_change_manager.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class RegulatoryChangeManager:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def monitor_regulatory_changes(self, industry: str, region: str, keywords: list = ['regulation', 'compliance']) -> dict:
		query = f"{industry} regulatory changes {region} {' '.join(keywords)} 2024 2025"
		results = self.search_engine.search(query, num_results=5)
		context = '\n'.join(f"- {r.get('title','')}: {r.get('body','')[:300]}" for r in results)

		prompt = (
			f"You are a regulatory compliance expert. Analyze regulatory changes for the following context.\n\n"
			f"Industry: {industry}\nRegion: {region}\nKeywords: {keywords}\n\n"
			f"Recent regulatory news:\n{context}\n\n"
			f"Return JSON with keys: regulatory_summary, recent_changes (list with: regulation_name, "
			f"effective_date, impact_level, description, required_actions), compliance_deadlines (list), "
			f"risk_areas (list), recommended_actions (list), monitoring_frequency."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'industry': industry, 'region': region, 'keywords': keywords, 'status': 'success'}

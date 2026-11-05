# capabilities/competitive_intelligence_operative.py

from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class CompetitiveIntelligenceOperative:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def analyze_competitor_landscape(self, competitors: list, areas_of_focus: list = ['market_share', 'product_strategy', 'financial_performance', 'marketing_tactics']) -> dict:
		competitor_data = {}
		for competitor in competitors[:5]:
			results = self.search_engine.search(f"{competitor} company analysis {' '.join(areas_of_focus[:2])}", num_results=3)
			snippets = ' '.join(r.get('body', '')[:200] for r in results)
			competitor_data[competitor] = snippets

		context = '\n'.join(f"**{c}**: {d}" for c, d in competitor_data.items())
		prompt = (
			f"You are a competitive intelligence expert. Analyze the competitive landscape for these competitors: {competitors}.\n\n"
			f"Focus areas: {areas_of_focus}\n\n"
			f"Research context:\n{context}\n\n"
			f"Return JSON with keys: competitors (object mapping name to profile), "
			f"landscape_summary, market_dynamics, strategic_threats, opportunities, "
			f"recommendations (list), areas_analyzed."
		)
		from core.output_validator import validated_llm_call
		result = validated_llm_call(self.ai_engine, prompt, fallback_key='result', required_keys=[], max_retries=2)
		if result.get('status') == 'parse_failed':
			return {'result': result.get('result', ''), 'competitors': competitors, 'areas_of_focus': areas_of_focus, 'status': 'success'}
		return result

# capabilities/supply_chain_resilience_planner.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class SupplyChainResiliencePlanner:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	_DISRUPTION_QUERIES = [
		'supply chain disruption 2024 2025 latest news',
		'port congestion shipping delays current',
		'geopolitical trade disruption tariffs sanctions current',
	]

	def assess_supply_chain_risks(
		self,
		supply_chain_description: str,
		risk_factors: list = ['geopolitical_instability', 'natural_disasters', 'supplier_financial_health'],
	) -> dict:
		# Best-practice mitigation context
		risk_query   = f"supply chain risk {' '.join(risk_factors[:2])} mitigation strategies"
		risk_results = self.search_engine.search(risk_query, num_results=4)
		risk_context = '\n'.join(f"- {r.get('body','')[:250]}" for r in risk_results)

		# Live disruption signals
		live_signals: list[str] = []
		for dq in self._DISRUPTION_QUERIES:
			results = self.search_engine.search(dq, num_results=2)
			for r in results:
				headline = r.get('title', '') or r.get('body', '')[:80]
				if headline:
					live_signals.append(headline)

		live_context = ''
		if live_signals:
			live_context = '\n\nLive disruption signals (current events):\n' + '\n'.join(
				f"- {s}" for s in live_signals[:8]
			)

		risk_factors_str = ', '.join(risk_factors)
		prompt = (
			f"You are a supply chain resilience expert. Assess risks for the following supply chain.\n\n"
			f"Supply Chain: {supply_chain_description}\nRisk Factors: {risk_factors_str}\n\n"
			f"Industry context:\n{risk_context}{live_context}\n\n"
			f"Return JSON with keys: supply_chain_summary, risk_assessment (list, each with: risk_factor, "
			f"likelihood (low/medium/high), impact (low/medium/high), risk_score (1-10), description, "
			f"current_signals (list of active disruptions if any), mitigation_strategies (list)), "
			f"overall_resilience_score (1-10), critical_vulnerabilities (list), "
			f"recommended_actions (list with priority), diversification_opportunities (list), "
			f"monitoring_indicators (list), live_disruptions_detected (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				result['live_signals_checked'] = len(live_signals)
				return result
		except Exception:
			pass
		result = {'result': response, 'risk_factors': risk_factors, 'status': 'success'}
		result['live_signals_checked'] = len(live_signals)
		return result

# capabilities/negotiation_strategy_builder.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class NegotiationStrategyBuilder:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine = None):
		self.ai_engine    = ai_engine
		self.search_engine = search_engine

	def develop_negotiation_strategy(
		self,
		negotiation_context: str,
		desired_outcomes: list,
		counterparty_profile: str,
	) -> dict:
		comparable_context = ''
		if self.search_engine:
			query   = f"negotiation strategy {negotiation_context[:60]} outcomes tactics case studies"
			results = self.search_engine.search(query, num_results=4)
			snippets = [f"- {r.get('title','')}: {r.get('body','')[:200]}" for r in results]
			if snippets:
				comparable_context = '\n\nComparable negotiation outcomes and research:\n' + '\n'.join(snippets)

		outcomes_str = '\n'.join(f"- {o}" for o in desired_outcomes)
		prompt = (
			f"You are a master negotiation strategist. Develop a comprehensive negotiation strategy.\n\n"
			f"Context: {negotiation_context}\n"
			f"Desired Outcomes:\n{outcomes_str}\n"
			f"Counterparty Profile: {counterparty_profile}"
			f"{comparable_context}\n\n"
			f"Return JSON with keys: strategy_summary, opening_position, target_position, "
			f"walk_away_point (BATNA), key_arguments (list), concessions_to_offer (list with: concession, "
			f"value_to_us, value_to_them), anticipated_objections (list with: objection, counter_response), "
			f"negotiation_tactics (list), red_lines (non-negotiables list), "
			f"psychological_insights (about counterparty), comparable_outcomes (list), "
			f"success_metrics (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'desired_outcomes': desired_outcomes, 'status': 'success'}

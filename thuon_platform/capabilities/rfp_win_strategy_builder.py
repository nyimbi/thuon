# capabilities/rfp_win_strategy_builder.py
"""
Atomic capability: build win strategy, themes, and solution outline for an RFP.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array
from core.output_validator import validated_llm_call


class RFPWinStrategyBuilder:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def build_strategy(
		self,
		evaluation_criteria: list | str = '',
		customer_research: str = '',
		competitor_analysis: str = '',
		company_context: str = '',
		rfp_title: str = '',
	) -> dict:
		"""
		Synthesize customer research and competitor intel into win themes.

		Returns:
			{win_themes, solution_outline, executive_summary_blueprint,
			 discriminators, pricing_strategy_hint}
		"""
		crit_text = json.dumps(evaluation_criteria) if isinstance(evaluation_criteria, list) else str(evaluation_criteria)

		prompt = (
			f'You are a proposal strategist crafting the win strategy for "{rfp_title or "this RFP"}".\n\n'
			f'Evaluation criteria:\n{crit_text[:1500]}\n\n'
			f'Customer research:\n{str(customer_research)[:1500]}\n\n'
			f'Competitor landscape:\n{str(competitor_analysis)[:1000]}\n\n'
			f'Our company context:\n{str(company_context)[:1500]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- win_themes (list): 3-5 items, each with:\n'
			'  - theme (str): short name\n'
			'  - headline (str): one punchy sentence stating the benefit\n'
			'  - proof_points (list of str): 2-3 evidence items from past performance\n'
			'  - ghosting_angle (str): how this implicitly counters a competitor weakness\n'
			'  - evaluation_criteria_addressed (list of str): which criteria this supports\n'
			'- solution_outline (object): {approach_summary, key_phases, staffing_strategy, '
			'risk_mitigation_highlights}\n'
			'- executive_summary_blueprint (str): 3-4 sentence outline for the exec summary\n'
			'- discriminators (list of str): top 3 things that make us uniquely qualified\n'
			'- pricing_strategy_hint (str): how to position price given the competitive landscape'
		)

		result = validated_llm_call(
			self.ai_engine, prompt,
			required_keys=['win_themes'],
			optional_keys=['solution_outline', 'executive_summary_blueprint',
						   'discriminators', 'pricing_strategy_hint'],
		)
		if result.get('status') == 'parse_failed':
			result.update({
				'win_themes': [], 'solution_outline': {},
				'executive_summary_blueprint': result.get('result', '')[:400],
				'discriminators': [], 'pricing_strategy_hint': '',
			})
		return result

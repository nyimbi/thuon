# capabilities/rfp_bid_evaluator.py
"""
Atomic capability: evaluate bid/no-bid decision for an RFP.
Scores against bid criteria from company KB.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class RFPBidEvaluator:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def evaluate(
		self,
		scope_summary: str,
		requirements: list | str = '',
		evaluation_criteria: list | str = '',
		budget: str = 'Not disclosed',
		company_context: str = '',
	) -> dict:
		"""
		Score this RFP against bid criteria and return a go/no-go recommendation.

		Returns:
			{bid_score, bid_recommendation, disqualifiers, risks,
			 rationale, estimated_win_probability, scoring_breakdown}
		"""
		reqs_text  = json.dumps(requirements) if isinstance(requirements, list) else str(requirements)
		crit_text  = json.dumps(evaluation_criteria) if isinstance(evaluation_criteria, list) else str(evaluation_criteria)

		prompt = (
			'You are a business development strategist evaluating whether to bid on an RFP.\n\n'
			f'Company context:\n{company_context or "[No company context provided]"}\n\n'
			f'Scope summary:\n{scope_summary}\n\n'
			f'Budget: {budget}\n\n'
			f'Evaluation criteria:\n{crit_text[:2000]}\n\n'
			f'Key requirements:\n{reqs_text[:2000]}\n\n'
			'Score this opportunity and return ONLY a valid JSON object with:\n'
			'- bid_score (int 0-100): overall attractiveness score\n'
			'- bid_recommendation (str): "go" | "no_bid" | "conditional_go"\n'
			'- disqualifiers (list of str): hard reasons to no-bid if any\n'
			'- risks (list of objects): each with {risk, severity: high|medium|low, mitigation}\n'
			'- rationale (str): 2-3 sentences explaining the recommendation\n'
			'- estimated_win_probability (int 0-100): estimated win %\n'
			'- scoring_breakdown (object): {strategic_fit, relationship, win_probability_raw, '
			'resource_fit, margin_potential, competition_level} each 1-5'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'bid_score':               50,
			'bid_recommendation':      'conditional_go',
			'disqualifiers':           [],
			'risks':                   [],
			'rationale':               response[:500],
			'estimated_win_probability': 50,
			'scoring_breakdown':        {},
		}

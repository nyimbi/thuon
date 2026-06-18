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
	def __init__(self, ai_engine: AIModel, feedback_store=None):
		self.ai_engine = ai_engine
		self._feedback = feedback_store

	def _get_historical_context(self, naics: str, issuer: str) -> str:
		"""
		Return a brief historical-performance block drawn from FeedbackStore.
		Returns empty string gracefully when no store or no data is available.
		"""
		if self._feedback is None:
			return ''
		try:
			rate = self._feedback.win_rate(naics=naics, issuer=issuer)
			themes = self._feedback.best_win_themes(naics=naics)
			if rate is None and not themes:
				return ''
			lines = ['Historical performance context:']
			if rate is not None:
				lines.append(
					f'  Win rate for NAICS {naics!r} / issuer {issuer!r}: '
					f'{rate["win_pct"]}% over {rate["sample_size"]} decided bids.'
				)
			if themes:
				lines.append(f'  Top win themes: {", ".join(themes[:5])}.')
			return '\n'.join(lines)
		except Exception:
			return ''

	def evaluate(
		self,
		scope_summary: str,
		requirements: list | str = '',
		evaluation_criteria: list | str = '',
		budget: str = 'Not disclosed',
		company_context: str = '',
		naics: str = '',
		issuer: str = '',
	) -> dict:
		"""
		Score this RFP against bid criteria and return a go/no-go recommendation.

		Returns:
			{bid_score, bid_recommendation, disqualifiers, risks,
			 rationale, estimated_win_probability, scoring_breakdown}
		"""
		reqs_text  = json.dumps(requirements) if isinstance(requirements, list) else str(requirements)
		crit_text  = json.dumps(evaluation_criteria) if isinstance(evaluation_criteria, list) else str(evaluation_criteria)

		historical = self._get_historical_context(naics, issuer)
		historical_block = f'\n{historical}\n' if historical else ''

		prompt = (
			'You are a business development strategist evaluating whether to bid on an RFP.\n\n'
			f'Company context:\n{company_context or "[No company context provided]"}\n'
			f'{historical_block}\n'
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
		result = extract_json(response)
		if result is not None:
			return result

		return {
			'bid_score':               50,
			'bid_recommendation':      'conditional_go',
			'disqualifiers':           [],
			'risks':                   [],
			'rationale':               response[:500],
			'estimated_win_probability': 50,
			'scoring_breakdown':        {},
		}

	def record_outcome(
		self,
		rfp_id: str,
		title: str = '',
		issuer: str = '',
		naics: str = '',
		budget_est: float = 0.0,
		win_themes: list[str] | None = None,
		outcome: str = 'lost',
		notes: str = '',
	) -> str:
		"""
		Record the outcome of an RFP bid in FeedbackStore.

		Lazy-initialises self._feedback from the module-level singleton when
		no store was injected at construction time.  Returns the new record id.
		"""
		if self._feedback is None:
			from core.feedback_store import get_feedback_store
			self._feedback = get_feedback_store()
		return self._feedback.record_outcome(
			rfp_id=rfp_id,
			title=title,
			issuer=issuer,
			naics=naics,
			budget_est=budget_est,
			win_themes=win_themes or [],
			outcome=outcome,
			notes=notes,
		)

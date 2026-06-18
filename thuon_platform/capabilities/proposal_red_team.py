# capabilities/proposal_red_team.py
"""
Adversarial proposal evaluation — play the evaluator, score the proposal,
find weaknesses before submission.

Simulates a government Source Selection Evaluation Board (SSEB) member:
scores each criterion 1-5, surfaces red flags, ghosting vulnerabilities,
missing requirements, and inconsistencies before they cost the win.
"""
from __future__ import annotations

import logging

from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array

logger = logging.getLogger(__name__)

_SCORE_LABELS = {1: 'Unacceptable', 2: 'Marginal', 3: 'Acceptable', 4: 'Good', 5: 'Outstanding'}


class ProposalRedTeam:
	"""
	Adversarial proposal reviewer.

	Plays the role of a government evaluator to surface weaknesses,
	gaps, and scoring liabilities before a proposal is submitted.
	"""

	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def evaluate(
		self,
		proposal_sections: dict,
		evaluation_criteria: list,
		rfp_requirements: list = [],
		company_context: str = '',
	) -> dict:
		"""
		Full adversarial evaluation of a proposal.

		Args:
			proposal_sections:   {section_name: content_str}
			evaluation_criteria: [{criterion, weight_pct, description}]
			rfp_requirements:    Raw requirement strings from the RFP (optional).
			company_context:     Brief description of the offeror for bias-check.

		Returns:
			{
				overall_score, max_score, score_pct,
				criterion_scores: [{criterion, score, max, feedback, improvement_suggestions}],
				critical_weaknesses, red_flags, missing_requirements,
				ghosting_vulnerabilities, executive_summary_quality,
				recommended_actions,
				submit_recommendation: 'submit'|'revise'|'major_revision'
			}
		"""
		if not evaluation_criteria:
			evaluation_criteria = [
				{'criterion': 'Technical Approach', 'weight_pct': 40, 'description': 'Technical feasibility and innovation'},
				{'criterion': 'Management Plan',    'weight_pct': 30, 'description': 'Project management and risk mitigation'},
				{'criterion': 'Past Performance',   'weight_pct': 20, 'description': 'Relevant past experience'},
				{'criterion': 'Price/Cost',         'weight_pct': 10, 'description': 'Price reasonableness and realism'},
			]

		sections_text    = self._format_sections(proposal_sections)
		criteria_text    = self._format_criteria(evaluation_criteria)
		requirements_text = (
			'\n'.join(f'- {r}' for r in rfp_requirements)
			if rfp_requirements
			else 'Not provided — infer from proposal content.'
		)
		context_block = f'\nOfferor context: {company_context}\n' if company_context else ''

		prompt = f"""You are a senior member of a government Source Selection Evaluation Board (SSEB)
conducting a rigorous evaluation of the following proposal. Your job is to score it honestly,
identify every weakness a competing evaluator could exploit, and provide actionable red-team feedback.
{context_block}
=== EVALUATION CRITERIA ===
{criteria_text}

=== RFP REQUIREMENTS TO VERIFY ===
{requirements_text}

=== PROPOSAL SECTIONS ===
{sections_text}

=== EVALUATION INSTRUCTIONS ===
For each criterion, score 1-5 using FAR/DFARS SSEB standards:
  1 = Unacceptable (fatal flaw, no award)
  2 = Marginal (significant weaknesses, high risk)
  3 = Acceptable (meets requirement, low risk)
  4 = Good (exceeds requirement, low risk)
  5 = Outstanding (significant strength, very low risk)

Then perform a full red-team pass:
- CRITICAL WEAKNESSES: issues that could disqualify or significantly downgrade the proposal.
- RED FLAGS: statements that will trigger evaluator skepticism or concern.
- MISSING REQUIREMENTS: RFP requirements not addressed or inadequately addressed.
- GHOSTING VULNERABILITIES: specific places a competitor could easily differentiate and one-up us
  by offering a superior approach, metric, or commitment.
- EXECUTIVE SUMMARY QUALITY: is it compelling, specific, and tied to the evaluation criteria?
- RECOMMENDED ACTIONS: concrete, prioritized fixes before submission.
- SUBMIT RECOMMENDATION: 'submit' (strong as-is), 'revise' (targeted improvements needed),
  or 'major_revision' (fundamental gaps — do not submit without significant rework).

Return ONLY valid JSON in this exact structure:
{{
  "criterion_scores": [
    {{
      "criterion": "<name>",
      "score": <1-5>,
      "max": 5,
      "feedback": "<evaluator narrative — 2-4 sentences>",
      "improvement_suggestions": ["<specific action>", ...]
    }}
  ],
  "critical_weaknesses": ["<weakness>", ...],
  "red_flags": ["<flag>", ...],
  "missing_requirements": ["<requirement not addressed>", ...],
  "ghosting_vulnerabilities": ["<vulnerability>", ...],
  "executive_summary_quality": "<assessment — 1-2 sentences>",
  "recommended_actions": ["<action>", ...],
  "submit_recommendation": "submit" | "revise" | "major_revision"
}}"""

		raw    = self.ai_engine.generate_text(prompt)
		parsed = extract_json(raw)

		if not parsed:
			logger.warning('ProposalRedTeam.evaluate: JSON extraction failed — returning raw fallback')
			return self._fallback_evaluate(evaluation_criteria)

		criterion_scores = parsed.get('criterion_scores', [])
		overall_score, max_score = self._compute_weighted_score(criterion_scores, evaluation_criteria)
		score_pct = round((overall_score / max_score * 100) if max_score else 0.0, 1)

		return {
			'overall_score':            round(overall_score, 2),
			'max_score':                round(max_score, 2),
			'score_pct':                score_pct,
			'criterion_scores':         criterion_scores,
			'critical_weaknesses':      parsed.get('critical_weaknesses', []),
			'red_flags':                parsed.get('red_flags', []),
			'missing_requirements':     parsed.get('missing_requirements', []),
			'ghosting_vulnerabilities': parsed.get('ghosting_vulnerabilities', []),
			'executive_summary_quality': parsed.get('executive_summary_quality', ''),
			'recommended_actions':      parsed.get('recommended_actions', []),
			'submit_recommendation':    parsed.get('submit_recommendation', 'revise'),
		}

	def quick_check(
		self,
		section_content: str,
		section_name: str,
		requirements: list = [],
	) -> dict:
		"""
		Fast single-section adversarial check.

		Args:
			section_content: Full text of the section.
			section_name:    Section identifier (e.g. 'technical_approach').
			requirements:    Specific requirements this section must address.

		Returns:
			{section_name, score: int (1-5), issues, strengths, quick_fixes}
		"""
		req_block = (
			'Requirements this section must address:\n' + '\n'.join(f'- {r}' for r in requirements)
			if requirements
			else ''
		)

		prompt = f"""You are a government proposal evaluator doing a rapid section review.
Section: {section_name}
{req_block}

=== SECTION CONTENT ===
{section_content[:6000]}

Score this section 1-5 (1=Unacceptable, 3=Acceptable, 5=Outstanding).
Identify concrete issues, genuine strengths, and quick fixes the author can apply in under an hour.

Return ONLY valid JSON:
{{
  "score": <1-5>,
  "issues": ["<issue>", ...],
  "strengths": ["<strength>", ...],
  "quick_fixes": ["<fix>", ...]
}}"""

		raw    = self.ai_engine.generate_text(prompt)
		parsed = extract_json(raw)

		if not parsed:
			logger.warning('ProposalRedTeam.quick_check: JSON extraction failed for section %s', section_name)
			return {
				'section_name': section_name,
				'score':        1,
				'issues':       ['Unable to parse evaluator response — review manually.'],
				'strengths':    [],
				'quick_fixes':  ['Re-run quick_check or review section manually.'],
			}

		score = max(1, min(5, int(parsed.get('score', 1))))

		return {
			'section_name': section_name,
			'score':        score,
			'issues':       parsed.get('issues', []),
			'strengths':    parsed.get('strengths', []),
			'quick_fixes':  parsed.get('quick_fixes', []),
		}

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _format_sections(self, proposal_sections: dict) -> str:
		parts = []
		for name, content in proposal_sections.items():
			heading = name.replace('_', ' ').title()
			text    = str(content)[:4000]  # guard against token blowout per section
			parts.append(f'--- {heading} ---\n{text}')
		return '\n\n'.join(parts) if parts else '(No sections provided)'

	def _format_criteria(self, evaluation_criteria: list) -> str:
		lines = []
		for c in evaluation_criteria:
			criterion   = c.get('criterion', 'Unknown')
			weight      = c.get('weight_pct', 0)
			description = c.get('description', '')
			lines.append(f'- {criterion} ({weight}%): {description}')
		return '\n'.join(lines)

	def _compute_weighted_score(self, criterion_scores: list, evaluation_criteria: list) -> tuple[float, float]:
		"""
		Compute weighted overall score against a 0-5 scale.

		Returns (weighted_score, 5.0). Falls back to simple average when
		weights are absent or do not sum to ~100.
		"""
		weight_map: dict[str, float] = {}
		total_weight = 0.0
		for c in evaluation_criteria:
			name = c.get('criterion', '')
			w    = float(c.get('weight_pct', 0))
			if name:
				weight_map[name.lower()] = w
				total_weight += w

		use_weights = bool(weight_map) and abs(total_weight - 100.0) < 5.0

		if not criterion_scores:
			return 0.0, 5.0

		if use_weights:
			weighted_sum = 0.0
			weight_used  = 0.0
			for cs in criterion_scores:
				name  = cs.get('criterion', '')
				score = float(cs.get('score', 0))
				w     = weight_map.get(name.lower(), 0.0)
				if w == 0.0:
					# fuzzy fallback: partial name match
					for k, v in weight_map.items():
						if name.lower() in k or k in name.lower():
							w = v
							break
				weighted_sum += score * w
				weight_used  += w

			if not weight_used:
				return 0.0, 5.0
			# weighted_sum is on a 0-500 scale (score * weight%); normalise to 0-5
			return weighted_sum / 100.0, 5.0

		# Simple average fallback
		scores = [float(cs.get('score', 0)) for cs in criterion_scores]
		return sum(scores) / len(scores), 5.0

	def _fallback_evaluate(self, evaluation_criteria: list) -> dict:
		"""Minimal structured fallback when LLM returns unparseable output."""
		criterion_scores = [
			{
				'criterion':              c.get('criterion', 'Unknown'),
				'score':                  1,
				'max':                    5,
				'feedback':               'Evaluation could not be parsed automatically — review raw output.',
				'improvement_suggestions': [],
			}
			for c in evaluation_criteria
		]
		return {
			'overall_score':             0.0,
			'max_score':                 5.0,
			'score_pct':                 0.0,
			'criterion_scores':          criterion_scores,
			'critical_weaknesses':       ['Automated evaluation failed — raw LLM output available in logs.'],
			'red_flags':                 [],
			'missing_requirements':      [],
			'ghosting_vulnerabilities':  [],
			'executive_summary_quality': 'Not assessed — evaluation parse error.',
			'recommended_actions':       ['Re-run evaluation or review proposal manually.'],
			'submit_recommendation':     'major_revision',
		}

# capabilities/capability_judge.py
"""
A/B test judge for capability outputs.

Asks the AI to score two outputs blind on five quality criteria,
records both trial results in ABTestStore, and auto-promotes when
enough evidence accumulates.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.ai_engine import AIModel
from core.ab_test_store import get_ab_test_store
from core.llm_utils import extract_json

logger = logging.getLogger(__name__)

_DEFAULT_CRITERIA = [
	'relevance',
	'completeness',
	'clarity',
	'actionability',
	'accuracy',
]

_JUDGE_PROMPT_TEMPLATE = """\
You are an impartial quality judge for AI-generated outputs.
You will score two responses (A and B) to the same input.
Do NOT speculate about which system or prompt generated each response.
Evaluate each output solely on its own merits.

INPUT:
{input_text}

--- OUTPUT A ---
{output_a}

--- OUTPUT B ---
{output_b}

CRITERIA (score each 1-10, where 1=poor and 10=excellent):
{criteria_list}

Return ONLY a JSON object in exactly this shape — no prose, no markdown fences:
{{
  "scores_a": {{"criterion1": <int>, "criterion2": <int>}},
  "scores_b": {{"criterion1": <int>, "criterion2": <int>}},
  "winner": "a" | "b" | "tie",
  "rationale": "<one concise paragraph explaining the verdict>",
  "strengths_a": ["<strength>"],
  "strengths_b": ["<strength>"]
}}

Rules:
- "winner" must be "a", "b", or "tie"
- Use "tie" only when mean scores differ by less than 0.5
- Each strengths list must have 1-5 items
- All criterion keys in scores_a and scores_b must match the CRITERIA listed above
"""


def _mean(scores: dict[str, float]) -> float:
	if not scores:
		return 0.0
	return sum(scores.values()) / len(scores)


def _parse_judge_response(
	raw: str,
	criteria: list[str],
) -> dict[str, Any]:
	"""Parse AI judge output; return a best-effort result dict even on partial parse."""
	data = extract_json(raw)
	if data is None:
		logger.warning('CapabilityJudge: failed to extract JSON from judge response')
		zero: dict[str, float] = {c: 0.0 for c in criteria}
		return {
			'winner': 'tie',
			'scores_a': zero,
			'scores_b': zero,
			'rationale': 'Judge response could not be parsed.',
			'strengths_a': [],
			'strengths_b': [],
		}

	scores_a: dict[str, float] = {
		c: float(data.get('scores_a', {}).get(c, 0)) for c in criteria
	}
	scores_b: dict[str, float] = {
		c: float(data.get('scores_b', {}).get(c, 0)) for c in criteria
	}

	raw_winner = str(data.get('winner', 'tie')).lower().strip()
	if raw_winner not in ('a', 'b', 'tie'):
		mean_a = _mean(scores_a)
		mean_b = _mean(scores_b)
		if abs(mean_a - mean_b) < 0.5:
			raw_winner = 'tie'
		else:
			raw_winner = 'a' if mean_a > mean_b else 'b'

	return {
		'winner': raw_winner,
		'scores_a': scores_a,
		'scores_b': scores_b,
		'rationale': str(data.get('rationale', '')),
		'strengths_a': list(data.get('strengths_a', [])),
		'strengths_b': list(data.get('strengths_b', [])),
	}


class CapabilityJudge:
	"""
	Blind A/B judge for capability outputs.

	Intended usage (synchronous — wrap in asyncio.to_thread for async callers)::

		judge = CapabilityJudge(ai_engine)
		result = judge.judge(experiment_id, input_text, output_a, output_b)
	"""

	def __init__(self, ai_engine: AIModel) -> None:
		self._ai = ai_engine
		self._store = get_ab_test_store()

	# ── public API ─────────────────────────────────────────────────────────────

	def judge(
		self,
		experiment_id: str,
		input_text: str,
		output_a: str,
		output_b: str,
		criteria: str = '',
	) -> dict[str, Any]:
		"""
		Evaluate output_a vs output_b blind on quality criteria.

		Parameters
		----------
		experiment_id:
		    Active experiment id in ABTestStore.
		input_text:
		    The original prompt/input that produced both outputs.
		output_a, output_b:
		    The two candidate outputs to compare.
		criteria:
		    Comma-separated custom criteria string.  When non-empty, overrides
		    the five default criteria (relevance, completeness, clarity,
		    actionability, accuracy).

		Returns
		-------
		dict with keys:
		    winner      – 'a' | 'b' | 'tie'
		    score_a     – mean score across all criteria for output A (float)
		    score_b     – mean score across all criteria for output B (float)
		    scores_a    – per-criterion scores for A (dict[str, float])
		    scores_b    – per-criterion scores for B (dict[str, float])
		    rationale   – judge's explanation string
		    strengths_a – list of strengths for A
		    strengths_b – list of strengths for B
		    promoted    – True if check_and_promote() declared a winner this call
		"""
		# Resolve criteria list
		if criteria.strip():
			criteria_list = [c.strip() for c in criteria.split(',') if c.strip()]
		else:
			criteria_list = list(_DEFAULT_CRITERIA)

		criteria_formatted = '\n'.join(f'- {c}' for c in criteria_list)
		prompt = _JUDGE_PROMPT_TEMPLATE.format(
			input_text=input_text,
			output_a=output_a,
			output_b=output_b,
			criteria_list=criteria_formatted,
		)

		try:
			raw_response = self._ai.generate_text(prompt)
		except Exception as exc:
			logger.error('CapabilityJudge: AI call failed: %s', exc)
			zero: dict[str, float] = {c: 0.0 for c in criteria_list}
			return {
				'winner': 'tie',
				'score_a': 0.0,
				'score_b': 0.0,
				'scores_a': zero,
				'scores_b': zero,
				'rationale': f'AI call failed: {exc}',
				'strengths_a': [],
				'strengths_b': [],
				'promoted': False,
			}

		parsed = _parse_judge_response(raw_response, criteria_list)
		score_a = _mean(parsed['scores_a'])
		score_b = _mean(parsed['scores_b'])

		judge_notes_a = json.dumps({
			'scores': parsed['scores_a'],
			'strengths': parsed['strengths_a'],
			'rationale': parsed['rationale'],
		})
		judge_notes_b = json.dumps({
			'scores': parsed['scores_b'],
			'strengths': parsed['strengths_b'],
			'rationale': parsed['rationale'],
		})

		try:
			self._store.record_trial(
				experiment_id=experiment_id,
				variant='a',
				input_text=input_text,
				score=score_a,
				judge_notes=judge_notes_a,
			)
			self._store.record_trial(
				experiment_id=experiment_id,
				variant='b',
				input_text=input_text,
				score=score_b,
				judge_notes=judge_notes_b,
			)
		except Exception as exc:
			logger.error('CapabilityJudge: failed to record trials: %s', exc)

		promoted = False
		try:
			winner_variant = self._store.check_and_promote(experiment_id)
			promoted = winner_variant is not None
		except Exception as exc:
			logger.error('CapabilityJudge: check_and_promote failed: %s', exc)

		return {
			'winner': parsed['winner'],
			'score_a': score_a,
			'score_b': score_b,
			'scores_a': parsed['scores_a'],
			'scores_b': parsed['scores_b'],
			'rationale': parsed['rationale'],
			'strengths_a': parsed['strengths_a'],
			'strengths_b': parsed['strengths_b'],
			'promoted': promoted,
		}

	def run_trial(
		self,
		capability_name: str,
		input_text: str,
		output_a: str,
		output_b: str,
	) -> dict[str, Any]:
		"""
		Convenience wrapper: looks up the active experiment for capability_name
		and delegates to judge().

		Returns {error: 'no active experiment', capability: ...} when none found.
		"""
		experiment = self._store.get_active_experiment(capability_name)
		if experiment is None:
			return {
				'error': 'no active experiment',
				'capability': capability_name,
			}
		return self.judge(
			experiment_id=experiment['id'],
			input_text=input_text,
			output_a=output_a,
			output_b=output_b,
		)

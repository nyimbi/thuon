"""
Confidence calibration — score capability outputs and attach calibrated
confidence metrics so callers can decide how much to trust a result.
"""
from __future__ import annotations
import re


# Hedging phrases that lower confidence
_HEDGE_PATTERNS = re.compile(
	r'\b(may|might|could|possibly|perhaps|unclear|unknown|uncertain|'
	r'likely|probably|approximately|roughly|around|suggests?|'
	r'appears? to|seems? to|I think|I believe|it seems)\b',
	re.IGNORECASE,
)

# Definitive phrases that raise confidence
_DEFINITIVE_PATTERNS = re.compile(
	r'\b(confirmed|verified|proven|established|documented|according to|'
	r'per the|data shows?|study found|research indicates?|as of)\b',
	re.IGNORECASE,
)


def _text_score(text: str) -> float:
	"""Heuristic score 0.0-1.0 based on hedge / definitive phrase density."""
	if not text:
		return 0.5
	words = len(text.split())
	hedges     = len(_HEDGE_PATTERNS.findall(text))
	defitinves = len(_DEFINITIVE_PATTERNS.findall(text))
	# base 0.5, +0.04 per definitive, -0.04 per hedge, clamp [0.1, 0.95]
	score = 0.5 + (defitinves - hedges) * 0.04 / max(words / 100, 1)
	return round(max(0.1, min(0.95, score)), 3)


def _structural_score(result: dict) -> float:
	"""
	Higher score if result has many non-empty fields (structured output
	suggests the model followed instructions faithfully).
	"""
	if not result:
		return 0.2
	non_empty = sum(
		1 for v in result.values()
		if v is not None and v != '' and v != [] and v != {}
	)
	total = max(len(result), 1)
	return round(min(0.95, 0.3 + 0.65 * (non_empty / total)), 3)


def _source_score(result: dict) -> float:
	"""Boost confidence if result contains cited sources/references."""
	text = json_flatten(result).lower()
	has_sources = any(
		k in text for k in ('http', 'doi:', 'arxiv', 'source', 'reference', 'citation')
	)
	return 0.85 if has_sources else 0.5


def json_flatten(obj, _depth: int = 0) -> str:
	"""Flatten nested dict/list to a single string for pattern matching."""
	if _depth > 4:
		return ''
	if isinstance(obj, str):
		return obj
	if isinstance(obj, dict):
		return ' '.join(json_flatten(v, _depth + 1) for v in obj.values())
	if isinstance(obj, list):
		return ' '.join(json_flatten(i, _depth + 1) for i in obj)
	return str(obj)


class ConfidenceCalibrator:
	"""
	Attach a `_confidence` block to any capability result dict.

	Scores (all 0.0 – 1.0):
	  - text_score:       hedge/definitive phrase ratio in free text fields
	  - structural_score: proportion of non-empty result fields
	  - source_score:     presence of cited URLs / DOIs
	  - overall:          weighted average

	Thresholds:
	  ≥ 0.75 → HIGH
	  ≥ 0.50 → MEDIUM
	  < 0.50 → LOW
	"""

	_WEIGHTS = {'text': 0.4, 'structural': 0.35, 'source': 0.25}

	def score(self, result: dict, extra_context: str = '') -> dict:
		"""Return confidence block dict (does not mutate result)."""
		flat = json_flatten(result) + ' ' + extra_context
		ts = _text_score(flat)
		ss = _structural_score(result)
		src = _source_score(result)
		overall = round(
			ts   * self._WEIGHTS['text'] +
			ss   * self._WEIGHTS['structural'] +
			src  * self._WEIGHTS['source'],
			3,
		)
		level = 'HIGH' if overall >= 0.75 else ('MEDIUM' if overall >= 0.50 else 'LOW')
		return {
			'text_score':       ts,
			'structural_score': ss,
			'source_score':     src,
			'overall':          overall,
			'level':            level,
		}

	def annotate(self, result: dict, extra_context: str = '') -> dict:
		"""Return a copy of result with `_confidence` key added."""
		return {**result, '_confidence': self.score(result, extra_context)}

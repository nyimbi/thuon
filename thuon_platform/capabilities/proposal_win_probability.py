# capabilities/proposal_win_probability.py
"""
Predict win probability for an RFP using historical bid data from FeedbackStore
and AI-assisted reasoning.

Return contract:
	{
		predicted_win_pct:    int,                # 0–100
		confidence:           str,                # 'high' | 'medium' | 'low'
		recommendation:       str,                # 'go' | 'no-go' | 'conditional-go'
		rationale:            str,
		historical_context:   dict,
		risk_factors:         list[str],
		suggested_win_themes: list[str],
	}
"""
from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.feedback_store import get_feedback_store
from core.llm_utils import extract_json

_log = logging.getLogger(__name__)

# ── Budget band helpers ───────────────────────────────────────────────────────

def _budget_range(budget_est: float) -> tuple[float, float]:
	"""±40 % band around estimate; floor at 0."""
	if budget_est <= 0:
		return (0.0, 0.0)
	low  = max(0.0, budget_est * 0.60)
	high = budget_est * 1.40
	return (low, high)


# ── Historical data loader ────────────────────────────────────────────────────

def _load_historical(
	naics: str,
	issuer: str,
	budget_est: float,
) -> tuple[dict[str, Any], bool]:
	"""
	Pull win-rate + similar-outcome rows from FeedbackStore.

	Returns (historical_context_dict, has_data).
	Never raises — all exceptions are caught and logged.
	"""
	ctx: dict[str, Any] = {
		'win_rate':        None,
		'sample_size':     0,
		'similar_outcomes': [],
		'best_win_themes': [],
	}
	has_data = False

	try:
		store = get_feedback_store()
	except Exception as exc:
		_log.debug('FeedbackStore unavailable: %s', exc)
		return ctx, False

	# -- win rate by NAICS + issuer ----------------------------------------
	if naics:
		try:
			wr = store.win_rate(naics=naics, issuer=issuer)
			if wr is not None:
				# win_rate() may return a float or a dict {win_pct, sample_size}
				if isinstance(wr, dict):
					ctx['win_rate']    = float(wr.get('win_pct', wr.get('rate', 0)))
					ctx['sample_size'] = int(wr.get('sample_size', wr.get('n', 0)))
				else:
					ctx['win_rate'] = float(wr)
				has_data = True
		except Exception as exc:
			_log.debug('win_rate() failed: %s', exc)

	# -- similar outcomes in budget band -----------------------------------
	brange = _budget_range(budget_est)
	if naics or brange != (0.0, 0.0):
		try:
			rows = store.similar_outcomes(naics=naics, budget_range=brange)
			if rows:
				ctx['similar_outcomes'] = _normalise_outcomes(rows)
				has_data = True
		except TypeError:
			# store may not accept budget_range kwarg — try positional
			try:
				rows = store.similar_outcomes(naics)
				if rows:
					ctx['similar_outcomes'] = _normalise_outcomes(rows)
					has_data = True
			except Exception as exc:
				_log.debug('similar_outcomes() failed: %s', exc)
		except Exception as exc:
			_log.debug('similar_outcomes() failed: %s', exc)

	# -- best performing win themes in this NAICS -------------------------
	if naics:
		try:
			themes = store.best_win_themes(naics=naics)
			if themes:
				ctx['best_win_themes'] = list(themes)
				has_data = True
		except Exception as exc:
			_log.debug('best_win_themes() failed: %s', exc)

	return ctx, has_data


def _normalise_outcomes(rows: Any) -> list[dict]:
	"""Coerce whatever similar_outcomes() returns into a uniform list of dicts."""
	if not rows:
		return []
	normalised = []
	for r in rows:
		if isinstance(r, dict):
			normalised.append(r)
		elif hasattr(r, '__dict__'):
			normalised.append(vars(r))
		else:
			normalised.append({'raw': str(r)})
	return normalised[:10]  # cap at 10 for prompt brevity


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
	scope_summary: str,
	issuer: str,
	naics: str,
	bid_score: float,
	win_themes: list,
	budget_est: float,
	hist: dict[str, Any],
	has_hist: bool,
) -> str:
	lines: list[str] = [
		'You are a senior capture manager assessing RFP win probability.',
		'',
		'## Opportunity',
		f'Issuer       : {issuer or "unknown"}',
		f'NAICS code   : {naics or "not provided"}',
		f'Budget est.  : {"${:,.0f}".format(budget_est) if budget_est > 0 else "unknown"}',
		f'Bid score    : {bid_score:.1f}/100' if bid_score else 'Bid score    : not scored yet',
		f'Scope        : {scope_summary}',
	]

	if win_themes:
		lines += ['', '## Proposed Win Themes']
		for t in win_themes:
			lines.append(f'  - {t}')

	if has_hist:
		lines += ['', '## Historical Context (from internal bid database)']

		wr = hist.get('win_rate')
		ss = hist.get('sample_size', 0)
		if wr is not None:
			pct_str = f'{wr * 100:.1f}%' if wr <= 1.0 else f'{wr:.1f}%'
			n_str   = f' ({ss} bids)' if ss else ''
			lines.append(f'  Historical win rate for NAICS {naics} with {issuer or "this issuer"}: {pct_str}{n_str}')

		similar = hist.get('similar_outcomes', [])
		if similar:
			lines.append(f'  Similar past bids ({len(similar)}):')
			for s in similar[:5]:
				title   = s.get('rfp_title') or s.get('title') or 'untitled'
				outcome = s.get('outcome', '?')
				score   = s.get('bid_score') or s.get('score') or ''
				score_s = f', score={score}' if score else ''
				lines.append(f'    • {title}: {outcome}{score_s}')

		best_themes = hist.get('best_win_themes', [])
		if best_themes:
			lines.append(f'  Best-performing win themes in NAICS {naics}:')
			for t in best_themes[:5]:
				lines.append(f'    • {t}')
	else:
		lines += [
			'',
			'## Historical Context',
			'  No internal bid history available. Use market knowledge and scope analysis only.',
		]

	lines += [
		'',
		'## Instructions',
		'Analyse the opportunity. Return ONLY a single valid JSON object — no prose, no markdown fences.',
		'',
		'Required keys:',
		'  predicted_win_pct    (int, 0-100)',
		'  confidence           (str: "high" | "medium" | "low")',
		'  recommendation       (str: "go" | "no-go" | "conditional-go")',
		'  rationale            (str, 2-4 sentences explaining the score)',
		'  risk_factors         (list of str, top risks, max 6)',
		'  suggested_win_themes (list of str, actionable differentiators, max 6)',
		'',
		'Calibration guidance:',
		'  - If historical win rate is available, weight it at ~40% of your estimate.',
		'  - A bid_score ≥ 75 with good past themes should yield predicted_win_pct ≥ 55.',
		'  - confidence = "low" when no history exists or bid_score = 0.',
		'  - recommendation = "go" when predicted_win_pct ≥ 40 and no fatal risk factors.',
		'  - recommendation = "no-go" when predicted_win_pct < 20 or there are unmitigable risks.',
		'  - recommendation = "conditional-go" otherwise.',
	]

	return '\n'.join(lines)


# ── Fallback result ───────────────────────────────────────────────────────────

def _fallback_result(
	raw_response: str,
	bid_score: float,
	win_themes: list,
	hist: dict[str, Any],
	has_hist: bool,
) -> dict[str, Any]:
	"""
	Best-effort structured result when JSON extraction fails.
	Uses bid_score and historical win rate to derive a numeric estimate.
	"""
	# Derive a rough win pct from available signals
	win_pct = 0

	wr = hist.get('win_rate') if has_hist else None
	if wr is not None:
		base = (wr * 100) if wr <= 1.0 else wr
		win_pct = int(base)
	elif bid_score > 0:
		# map score linearly: 50→30, 100→70
		win_pct = max(5, min(95, int(bid_score * 0.70 - 5)))
	else:
		win_pct = 30

	confidence  = 'low' if not has_hist else ('medium' if wr else 'low')
	rec         = 'go' if win_pct >= 40 else ('conditional-go' if win_pct >= 20 else 'no-go')

	return {
		'predicted_win_pct':    win_pct,
		'confidence':           confidence,
		'recommendation':       rec,
		'rationale':            (raw_response[:400].strip() or
								'AI response could not be parsed into structured JSON.'),
		'historical_context':   hist,
		'risk_factors':         ['Unable to parse AI risk analysis — review manually.'],
		'suggested_win_themes': win_themes[:6],
	}


# ── Main class ────────────────────────────────────────────────────────────────

class ProposalWinProbability:
	"""
	Predict win probability for an RFP using historical bid data and AI reasoning.

	Usage::

		from core.ai_engine import get_ai_engine
		from capabilities.proposal_win_probability import ProposalWinProbability

		engine    = get_ai_engine()
		predictor = ProposalWinProbability(engine)
		result    = predictor.predict(
			scope_summary='IT modernisation of legacy HR systems',
			issuer='Department of Veterans Affairs',
			naics='541511',
			bid_score=72.5,
			win_themes=['agile delivery', 'zero-downtime migration'],
			budget_est=4_500_000,
		)
	"""

	def __init__(self, ai_engine: AIModel) -> None:
		assert isinstance(ai_engine, AIModel), 'ai_engine must be an AIModel instance'
		self.ai_engine = ai_engine

	# ── public API ────────────────────────────────────────────────────────

	def predict(
		self,
		scope_summary: str,
		issuer: str,
		naics: str = '',
		bid_score: float = 0,
		win_themes: list | None = None,
		budget_est: float = 0,
	) -> dict[str, Any]:
		"""
		Predict win probability for an RFP.

		Args:
			scope_summary: Plain-text description of the work being procured.
			issuer:        Issuing agency / organisation name.
			naics:         NAICS code string (e.g. '541511'). Used for history lookup.
			bid_score:     Internal bid quality score 0–100 (0 = not yet scored).
			win_themes:    Proposed win themes / discriminators for this bid.
			budget_est:    Estimated contract value in USD (0 = unknown).

		Returns:
			{
				predicted_win_pct:    int,   # 0–100
				confidence:           str,   # 'high' | 'medium' | 'low'
				recommendation:       str,   # 'go' | 'no-go' | 'conditional-go'
				rationale:            str,
				historical_context:   dict,
				risk_factors:         list[str],
				suggested_win_themes: list[str],
			}
		"""
		assert scope_summary, 'scope_summary must not be empty'
		assert issuer or naics, 'at least one of issuer or naics must be provided'

		win_themes = list(win_themes) if win_themes else []

		# 1. Load historical data ------------------------------------------------
		hist, has_hist = _load_historical(naics=naics, issuer=issuer, budget_est=budget_est)
		_log.debug(
			'predict(): naics=%s issuer=%s has_hist=%s win_rate=%s similar=%d',
			naics, issuer, has_hist,
			hist.get('win_rate'), len(hist.get('similar_outcomes', [])),
		)

		# 2. Build prompt --------------------------------------------------------
		prompt = _build_prompt(
			scope_summary=scope_summary,
			issuer=issuer,
			naics=naics,
			bid_score=bid_score,
			win_themes=win_themes,
			budget_est=budget_est,
			hist=hist,
			has_hist=has_hist,
		)

		# 3. Call AI -------------------------------------------------------------
		raw = ''
		try:
			raw = self.ai_engine.generate_text(prompt)
		except Exception as exc:
			_log.error('AI generation failed: %s', exc)
			return _fallback_result(str(exc), bid_score, win_themes, hist, has_hist)

		# 4. Parse JSON ----------------------------------------------------------
		parsed = extract_json(raw)
		if parsed is None:
			_log.warning('Could not extract JSON from AI response; using fallback')
			return _fallback_result(raw, bid_score, win_themes, hist, has_hist)

		# 5. Normalise & validate output ----------------------------------------
		result = self._normalise(parsed, hist, has_hist, win_themes)
		_log.debug('predict() -> win_pct=%d confidence=%s rec=%s',
				   result['predicted_win_pct'], result['confidence'], result['recommendation'])
		return result

	# ── private helpers ───────────────────────────────────────────────────

	def _normalise(
		self,
		parsed: dict,
		hist: dict[str, Any],
		has_hist: bool,
		win_themes: list,
	) -> dict[str, Any]:
		"""
		Coerce AI output into the canonical return contract.
		Unknown / missing keys are filled with safe defaults.
		"""
		# predicted_win_pct: int clamp 0–100
		raw_pct = parsed.get('predicted_win_pct') or parsed.get('win_probability') or 0
		try:
			win_pct = max(0, min(100, int(round(float(raw_pct)))))
		except (TypeError, ValueError):
			win_pct = 0

		# confidence
		raw_conf = str(parsed.get('confidence', '')).lower().strip()
		if raw_conf not in ('high', 'medium', 'low'):
			raw_conf = 'low' if not has_hist else 'medium'

		# recommendation
		raw_rec = str(parsed.get('recommendation', '')).lower().strip()
		valid_recs = {'go', 'no-go', 'conditional-go'}
		if raw_rec not in valid_recs:
			# derive from pct
			raw_rec = 'go' if win_pct >= 40 else ('conditional-go' if win_pct >= 20 else 'no-go')

		# risk_factors
		risk_factors = parsed.get('risk_factors') or parsed.get('risks') or []
		if isinstance(risk_factors, str):
			risk_factors = [risk_factors]
		risk_factors = [str(r) for r in risk_factors][:8]

		# suggested_win_themes
		suggested = (
			parsed.get('suggested_win_themes')
			or parsed.get('recommended_win_themes')
			or parsed.get('win_themes')
			or win_themes
		)
		if isinstance(suggested, str):
			suggested = [suggested]
		suggested = [str(t) for t in suggested][:8]

		# rationale
		rationale = str(parsed.get('rationale', '')).strip() or 'No rationale provided.'

		# historical_context: merge AI commentary with DB data
		ai_hist = parsed.get('historical_context') or {}
		if isinstance(ai_hist, dict):
			merged_hist = {**hist, **ai_hist}
		else:
			merged_hist = hist

		# If no history, confidence must not exceed 'low'
		if not has_hist and raw_conf == 'high':
			raw_conf = 'low'

		return {
			'predicted_win_pct':    win_pct,
			'confidence':           raw_conf,
			'recommendation':       raw_rec,
			'rationale':            rationale,
			'historical_context':   merged_hist,
			'risk_factors':         risk_factors,
			'suggested_win_themes': suggested,
		}

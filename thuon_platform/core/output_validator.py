# core/output_validator.py
# Universal weakness #3 — Pydantic-grade output validation with auto-retry.
#
# Replaces the fragile `try json.loads; fallback to {result: text}` pattern
# with a retry loop that feeds parse errors back to the LLM as correction prompts.
# All 36 capabilities can use validated_llm_call() as a drop-in replacement
# for ai_engine.generate_text() + manual JSON extraction.

import json
import re
from typing import Any

from core.ai_engine import AIModel


def _extract_json(text: str) -> dict | None:
	# Strategy 1: entire response is JSON
	try:
		return json.loads(text.strip())
	except Exception:
		pass
	# Strategy 2: first {...} block (most common LLM pattern)
	try:
		match = re.search(r'\{.*\}', text, re.DOTALL)
		if match:
			return json.loads(match.group())
	except Exception:
		pass
	# Strategy 3: JSON inside a markdown code fence
	try:
		match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
		if match:
			return json.loads(match.group(1))
	except Exception:
		pass
	return None


def validated_llm_call(
	ai_engine: AIModel,
	prompt: str,
	required_keys: list[str] = [],
	optional_keys: list[str] = [],
	max_retries: int = 3,
	fallback_key: str = 'result',
) -> dict:
	"""
	Call the LLM and guarantee a parsed dict with required_keys present.
	On parse failure or missing keys, re-prompts with specific error feedback.
	Falls back to {fallback_key: raw_text, status: 'parse_failed'} after max_retries.

	Args:
		ai_engine:     Any AIModel implementation.
		prompt:        The original task prompt. Must already ask for JSON output.
		required_keys: Keys that MUST be present; triggers retry if absent.
		optional_keys: Keys requested but not enforced.
		max_retries:   Maximum re-prompt attempts.
		fallback_key:  Key name used in the last-resort fallback dict.
	"""
	last_response = ''
	active_prompt = prompt

	for attempt in range(max_retries):
		last_response = ai_engine.generate_text(active_prompt)
		result = _extract_json(last_response)

		if result is not None:
			missing = [k for k in required_keys if k not in result]
			if not missing:
				result.setdefault('_validated', True)
				return result
			# Has JSON but missing keys — build targeted retry prompt
			active_prompt = (
				f'Your previous response was missing required JSON keys: {missing}.\n'
				f'The keys {optional_keys} are also expected.\n\n'
				f'Please try again. Return ONLY valid JSON. Do not include markdown fences or explanatory text.\n\n'
				f'Original task:\n{prompt}'
			)
		else:
			# No parseable JSON found at all
			preview = last_response[:200].replace('\n', ' ')
			active_prompt = (
				f'Your previous response did not contain valid JSON. Response preview: "{preview}"\n\n'
				f'Please try again. Return ONLY a raw JSON object (no markdown, no explanations).\n\n'
				f'Original task:\n{prompt}'
			)

	# Exhausted retries — return best effort
	result = _extract_json(last_response)
	if result:
		result['_validated'] = False
		result['_validation_note'] = f'Missing keys after {max_retries} retries'
		return result
	return {
		fallback_key: last_response,
		'status': 'parse_failed',
		'_validated': False,
		'_retries_exhausted': max_retries,
	}


def extract_json_array(text: str) -> list:
	"""Extract a JSON array from LLM output."""
	try:
		return json.loads(text.strip())
	except Exception:
		pass
	try:
		match = re.search(r'\[.*\]', text, re.DOTALL)
		if match:
			return json.loads(match.group())
	except Exception:
		pass
	return []

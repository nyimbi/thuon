# core/llm_utils.py
"""
Shared LLM response parsing utilities.

Uses balanced-brace/bracket extraction instead of greedy regex so prose-wrapped
LLM responses (```json ... ``` fences, trailing commentary) are handled correctly.
"""
from __future__ import annotations

import json


def _extract_span(text: str, open_ch: str, close_ch: str) -> str | None:
	"""Return the first balanced span between open_ch and close_ch, or None."""
	depth = 0
	start = None
	for i, ch in enumerate(text):
		if ch == open_ch:
			if start is None:
				start = i
			depth += 1
		elif ch == close_ch:
			depth -= 1
			if depth == 0 and start is not None:
				return text[start:i + 1]
	return None


def extract_json(text: str) -> dict | None:
	"""Extract first complete JSON object from text. Returns None on failure."""
	span = _extract_span(text, '{', '}')
	if span:
		try:
			return json.loads(span)
		except (json.JSONDecodeError, ValueError):
			pass
	return None


def extract_json_array(text: str) -> list | None:
	"""Extract first complete JSON array from text. Returns None on failure."""
	span = _extract_span(text, '[', ']')
	if span:
		try:
			return json.loads(span)
		except (json.JSONDecodeError, ValueError):
			pass
	return None

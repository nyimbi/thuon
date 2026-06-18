# core/skill_router.py
"""
Two-stage skill router: BM25 keyword match → LLM disambiguation when top-2
scores are within 1 point of each other.

Usage::

  router = SkillRouter(ai_engine=ollama_model)
  manifest = router.route("research the Kenyan fintech market")
  # → SkillManifest(name='market_sales_research', ...)

  top3 = router.route("generate a tender response", top_k=3)
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from core.llm_utils import extract_json
from core.skill_registry import SkillManifest, SkillRegistry

if TYPE_CHECKING:
	from core.ai_engine import OllamaModel

logger = logging.getLogger('thuon.skill_router')


class SkillRouter:
	"""
	Route natural language instructions to SkillManifests.

	Stage 1: BM25-lite score over name + description + keywords.
	Stage 2: LLM rerank only when top-2 candidates are within 1 BM25 point.
	"""

	def __init__(self, ai_engine: OllamaModel | None = None) -> None:
		self._registry = SkillRegistry.get_instance()
		self._ai = ai_engine
		self._cap_list: str | None = None  # cached after first build

	def route(
		self,
		instruction: str,
		top_k: int = 1,
		fallback: str = 'research_assistant',
	) -> list[SkillManifest] | SkillManifest | None:
		"""
		Route instruction to the best matching skill(s).

		Args:
			instruction: Natural language instruction from the user.
			top_k:       How many results to return.
			             If 1 (default), returns a single SkillManifest or None.
			             If >1, returns a list of SkillManifests.
			fallback:    Capability name to use when nothing matches.

		Returns:
			Single SkillManifest when top_k=1, list when top_k>1.
		"""
		candidates = self._registry.search(instruction, top_k=top_k + 4)

		if not candidates:
			fb = self._registry.get(fallback)
			return fb if top_k == 1 else ([fb] if fb else [])

		if top_k == 1:
			best = self._pick_best(instruction, candidates)
			return best

		return candidates[:top_k]

	def route_with_params(
		self,
		instruction: str,
		fallback: str = 'research_assistant',
		allowed_names: set[str] | None = None,
	) -> tuple[str, dict[str, Any]]:
		"""
		Route and extract parameters from the instruction using the LLM.

		Args:
			instruction:   Natural language user request.
			fallback:      Capability name when nothing matches.
			allowed_names: If given, restrict routing to this subset of names.
			               Useful for the CLI facade which can only instantiate
			               capabilities in _REGISTRY.

		Returns (capability_name, params_dict).
		"""
		manifest = self.route(instruction, top_k=1, fallback=fallback)
		if manifest is None:
			return fallback, {}
		# Enforce allowed_names restriction — if the best match is outside the
		# allowed set, re-search within the restricted set.
		if allowed_names and manifest.name not in allowed_names:
			restricted = [
				m for m in self._registry.search(instruction, top_k=10)
				if m.name in allowed_names
			]
			manifest = restricted[0] if restricted else (self._registry.get(fallback) or manifest)

		if self._ai is None:
			return manifest.name, _extract_quoted(instruction)

		if self._cap_list is None:
			self._cap_list = '\n'.join(
				f'- {m.name}: {m.description}'
				for m in self._registry.all()
				if m.module and m.class_name
			)
		prompt = (
			'You are a routing assistant. Given a user instruction, identify '
			'which capability to call and extract the parameters.\n\n'
			f'Available capabilities:\n{self._cap_list}\n\n'
			f'Instruction: "{instruction}"\n\n'
			'Return ONLY valid JSON:\n'
			'{"capability": "<name>", "params": {<key: value>}}\n'
			'JSON:'
		)
		try:
			raw = self._ai.generate_text(prompt)
			parsed = extract_json(raw)
			if parsed and isinstance(parsed, dict):
				cap_name = parsed.get('capability', '')
				params = parsed.get('params', {})
				if cap_name in self._registry:
					return cap_name, params
		except Exception as exc:
			logger.warning('LLM routing failed: %s', exc)

		return manifest.name, _extract_quoted(instruction)

	# ── Internal ──────────────────────────────────────────────────────────────

	def _pick_best(
		self,
		instruction: str,
		candidates: list[SkillManifest],
	) -> SkillManifest:
		if len(candidates) == 1:
			return candidates[0]

		# Disambiguate with LLM when top-2 are very close
		if (
			self._ai is not None
			and _score_gap(instruction, candidates[:2]) <= 1
		):
			chosen = self._llm_disambiguate(instruction, candidates[:5])
			if chosen is not None:
				return chosen

		return candidates[0]

	def _llm_disambiguate(
		self,
		instruction: str,
		candidates: list[SkillManifest],
	) -> SkillManifest | None:
		options = '\n'.join(
			f'- {m.name}: {m.description}' for m in candidates
		)
		prompt = (
			'Pick the single best capability for this instruction.\n\n'
			f'Instruction: "{instruction}"\n\n'
			f'Options:\n{options}\n\n'
			'Return ONLY the capability name, nothing else.'
		)
		try:
			raw = self._ai.generate_text(prompt).strip().lower()
			name = re.sub(r'[^a-z0-9_]', '', raw)
			return next((m for m in candidates if m.name == name), None)
		except Exception as exc:
			logger.warning('LLM disambiguation failed: %s', exc)
			return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_gap(instruction: str, top2: list[SkillManifest]) -> float:
	"""Return the BM25-lite score difference between the top-2 candidates."""
	tokens = set(re.findall(r'\w+', instruction.lower()))
	scores = []
	for m in top2:
		haystack = (
			m.name.replace('_', ' ') + ' '
			+ m.description + ' '
			+ ' '.join(m.keywords)
		).lower()
		scores.append(sum(1.0 for t in tokens if t in haystack))
	return abs(scores[0] - scores[1]) if len(scores) == 2 else 0.0


def _extract_quoted(instruction: str) -> dict[str, Any]:
	"""Fallback: extract first quoted string as primary param."""
	quoted = re.findall(r'"([^"]+)"', instruction)
	return {'query': quoted[0]} if quoted else {'query': instruction}

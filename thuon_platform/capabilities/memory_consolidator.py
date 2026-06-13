"""
Background memory consolidation — Hermes-inspired.

Runs after conversations or on schedule:
- Extracts new facts from recent episodes → adds to MEMORY.md or USER.md
- Detects user preferences, corrections, and preferences → updates USER.md
- Summarises old episodes into semantic facts
- Deduplicates conflicting facts

This is the "background review fork" pattern from Hermes.
"""
from __future__ import annotations

import json
import re
from typing import Any


class MemoryConsolidator:
	def __init__(self, ai_engine: Any) -> None:
		self._ai = ai_engine

	def consolidate(
		self,
		conversation: str = '',
		force_full_scan: bool = False,
	) -> dict[str, Any]:
		"""
		Consolidate memory from recent activity.

		conversation: recent conversation text to extract facts from.
		force_full_scan: re-scan all recent episodes even without new conversation.
		Returns: {user_facts_added, memory_facts_added, episodes_processed, summary}
		"""
		try:
			from core.memory_store import get_memory_store
			ms = get_memory_store()
		except ImportError:
			return {'error': 'memory_store not available'}

		user_facts_added = 0
		memory_facts_added = 0

		# 1. Extract from provided conversation
		if conversation.strip():
			result = self._extract_from_text(conversation, ms)
			user_facts_added   += result.get('user_facts', 0)
			memory_facts_added += result.get('memory_facts', 0)

		# 2. Scan recent episodes if force or no conversation given
		if force_full_scan or not conversation.strip():
			episodes = ms.recent_episodes(limit=20)
			episode_text = '\n'.join(
				f"[{e['type']}] {e['content'][:300]}" for e in episodes
			)
			if episode_text:
				result = self._extract_from_text(episode_text, ms)
				user_facts_added   += result.get('user_facts', 0)
				memory_facts_added += result.get('memory_facts', 0)

		return {
			'user_facts_added': user_facts_added,
			'memory_facts_added': memory_facts_added,
			'summary': (
				f"Consolidated memory: {user_facts_added} user facts, "
				f"{memory_facts_added} company/context facts extracted."
			),
		}

	def _extract_from_text(self, text: str, ms: Any) -> dict[str, int]:
		current_user   = ms.read_user()
		current_memory = ms.read_memory()

		prompt = f"""You are a memory consolidation agent. Extract new, durable facts from this text.

EXISTING USER PROFILE:
{current_user[:1500]}

EXISTING MEMORY:
{current_memory[:1500]}

TEXT TO ANALYZE:
{text[:4000]}

Extract only NEW facts not already in the existing profile/memory.
Focus on:
USER FACTS: personal preferences, working style, communication preferences, role details, goals, corrections the user made to prior behavior
COMPANY/CONTEXT FACTS: company wins, new hires, contract awards, strategic decisions, market intelligence, operational facts

Return JSON:
{{
  "user_facts": [
    "specific fact about the user (e.g. 'Prefers bullet lists over paragraphs')"
  ],
  "memory_facts": [
    "specific fact about the company or context (e.g. 'Won DHS contract worth $2.4M in June 2026')"
  ]
}}

Only include facts that are:
- Specific and durable (will still be true in 6 months)
- Not already captured in existing profile/memory
- Genuinely useful for future interactions

Return empty lists if nothing new and durable was found. Return only the JSON object."""

		response = self._ai.generate(prompt)
		data = self._parse_json(response)

		user_count = 0
		for fact in data.get('user_facts', []):
			if fact.strip():
				ms.add_user_fact(fact.strip())
				user_count += 1

		mem_count = 0
		for fact in data.get('memory_facts', []):
			if fact.strip():
				ms.add_memory_fact(fact.strip())
				mem_count += 1

		return {'user_facts': user_count, 'memory_facts': mem_count}

	@staticmethod
	def _parse_json(text: str) -> dict[str, Any]:
		text = text.strip()
		m = re.search(r'\{.*\}', text, re.DOTALL)
		if m:
			try:
				return json.loads(m.group())
			except json.JSONDecodeError:
				pass
		return {'user_facts': [], 'memory_facts': []}

# capabilities/skill_hub.py
"""Skills management surface for Thuon.

Surfaces the SKILL.md plugin system as first-class capabilities so users can
list and run markdown skills from any Thuon entry point (web, CLI, NL router).
"""
from __future__ import annotations

from typing import Any

from core.ai_engine import AIModel
from core.skill_registry import SkillRegistry


class SkillHub:
	"""List, inspect, and run installed markdown skills."""

	def __init__(self, ai_engine: AIModel | None = None):
		self.ai_engine = ai_engine

	def list_skills(self, category: str = '', query: str = '') -> list[dict]:
		"""List markdown skills, optionally filtered by category/query."""
		reg = SkillRegistry.get_instance()
		manifests = reg.all()
		if query:
			manifests = reg.search(query, top_k=50)
		out = []
		for m in manifests:
			if category and m.category != category:
				continue
			out.append({
				'name': m.name,
				'category': m.category,
				'description': m.description,
				'type': 'markdown_skill',
				'has_body': bool(m.body),
			})
		return out

	def run_skill(self, skill: str, instruction: str = '', query: str = '') -> dict[str, Any]:
		"""Run a markdown skill by name, with $ARGUMENTS substituted."""
		from core.skill_runner import SkillRunner
		text = instruction or query or ''
		if not text:
			m = SkillRegistry.get_instance().get(skill)
			if m is None:
				return {'status': 'error', 'error': 'unknown skill', 'skill': skill}
			return {
				'name': skill,
				'body': m.body,
				'category': m.category,
				'description': m.description,
				'status': 'ready',
			}
		ai = self.ai_engine
		if ai is None:
			from core.ai_engine import get_ai_engine
			ai = get_ai_engine('standard')
		return SkillRunner(skill, ai).run(instruction=text)

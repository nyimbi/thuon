# core/skill_runner.py
"""Runtime execution for SKILL.md-only skills (no backing Python capability).

A skill that ships only a markdown body becomes runnable by injecting its
body into the prompt, then calling the active AI engine. This is the
"Hermes skill" model: skill = instruction doc, not a typed function.
"""
from __future__ import annotations

from typing import Any

from core.skill_registry import SkillRegistry


class SkillRunner:
	"""Executes a markdown-skill via the active AI engine."""

	def __init__(self, skill_name: str, ai_engine: Any):
		self.skill_name = skill_name
		self.ai_engine = ai_engine
		manifest = SkillRegistry.get_instance().get(skill_name)
		if manifest is None:
			raise ValueError(f'Unknown skill: {skill_name!r}')
		self.manifest = manifest

	def run(self, **kwargs) -> dict[str, Any]:
		instruction = (kwargs.get('instruction')
		              or kwargs.get('query')
		              or kwargs.get('prompt')
		              or '')
		body = self.manifest.body or ''
		prompt = body.replace('$ARGUMENTS', instruction) if body else instruction
		if instruction and instruction not in prompt:
			prompt = f'{prompt}\n\nUser request: {instruction}'
		try:
			text = self.ai_engine.generate_text(prompt)
		except Exception as exc:
			return {'status': 'error', 'error': str(exc), 'skill': self.skill_name}
		return {
			'result': text,
			'skill': self.skill_name,
			'focused_skill': 'skill_prompt',
			'skill_prompt': body[:2000],
		}

	@property
	def configured_prompt(self) -> str:
		return self.manifest.body or ''

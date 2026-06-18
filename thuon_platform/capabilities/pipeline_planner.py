# capabilities/pipeline_planner.py
"""
Adaptive pipeline compiler — given a task description, dynamically select and
sequence capabilities into an executable YAML pipeline plan.

The planner inspects the live SkillRegistry on every call so it sees all
registered capabilities (including SKILL.md-defined ones) without restart.

Return contract::

    {
        pipeline_name:  str,
        description:    str,
        steps:          list[{name, capability, params}],
        estimated_steps: int,
        warnings:       list[str],
        yaml:           str,   # ready to pass to pipeline_runner
    }
"""
from __future__ import annotations

import logging
import re
from typing import Any

import yaml  # PyYAML

from core.ai_engine import AIModel
from core.llm_utils import extract_json
from core.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

_MAX_STEPS = 20


def _capability_catalog() -> str:
	"""One-line per capability: 'name -- description', sorted by name."""
	registry = SkillRegistry.get_instance()
	lines: list[str] = []
	for manifest in sorted(registry.all(), key=lambda m: m.name):
		desc = (manifest.description or '').replace('\n', ' ')[:120]
		lines.append(f'{manifest.name} -- {desc}')
	return '\n'.join(lines) if lines else '(no capabilities registered)'


def _valid_capability_names() -> set[str]:
	return {m.name for m in SkillRegistry.get_instance().all()}


def _dedup_step_names(steps: list[dict]) -> list[dict]:
	"""Ensure step `name` values are unique by appending _2, _3, …"""
	seen: dict[str, int] = {}
	result: list[dict] = []
	for step in steps:
		name = str(step.get('name') or 'step')
		if name in seen:
			seen[name] += 1
			step = dict(step)
			step['name'] = f'{name}_{seen[name]}'
		else:
			seen[name] = 1
		result.append(step)
	return result


class PipelinePlanner:
	"""
	Dynamically compile a YAML pipeline from a natural-language task description.

	Usage::

		planner = PipelinePlanner(ai_engine)
		plan    = planner.plan(
			task='Research Agency X and write an executive summary',
			context={'issuer': 'NASA', 'naics': '541511'},
			max_steps=8,
		)
		# plan['yaml'] can be passed directly to pipeline_runner
	"""

	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	# ── Public API ────────────────────────────────────────────────────────────

	def plan(
		self,
		task: str,
		context: dict | None = None,
		max_steps: int = 10,
		pipeline_name: str = '',
	) -> dict[str, Any]:
		"""
		Generate an executable pipeline plan for the given task.

		Args:
			task:          Natural-language description of what to accomplish.
			context:       Optional key-value pairs passed to the planner as
			               'initial inputs' (become {input.key} variables).
			max_steps:     Cap on the number of pipeline steps (default 10).
			pipeline_name: Optional slug; generated from task if omitted.

		Returns:
			{pipeline_name, description, steps, estimated_steps, warnings, yaml}
		"""
		assert task, 'task must not be empty'
		max_steps = min(max_steps, _MAX_STEPS)

		catalog  = _capability_catalog()
		ctx_text = (
			'\nInitial inputs available as {input.key}:\n'
			+ '\n'.join(f'  {k}: {v}' for k, v in (context or {}).items())
			if context
			else ''
		)

		prompt = f"""You are an expert workflow architect for the Thuon AI platform.

Your job: given a task, compose a linear pipeline of Thuon capabilities that will
accomplish it end-to-end. Each step calls exactly one capability.

Rules:
- Use ONLY capabilities from the catalog below.
- Output ONLY valid JSON — no prose, no markdown fences.
- Step names must be unique lowercase identifiers (snake_case).
- Use {{input.key}} for initial inputs, {{steps.step_name.output_key}} to thread
  results between steps (use simple plausible key names — the runner resolves them).
- Maximum {max_steps} steps.
- Keep steps minimal — don't add steps that aren't needed.

## Available capabilities
{catalog}
{ctx_text}

## Task
{task}

## Required JSON structure
{{
  "pipeline_name": "<short_slug>",
  "description": "<one sentence>",
  "steps": [
    {{
      "name": "<step_slug>",
      "capability": "<capability_name>",
      "params": {{
        "<param_name>": "<value or {{steps.prev.key}} template>"
      }}
    }}
  ],
  "total_estimated_minutes": <int>
}}

JSON:"""

		raw = ''
		try:
			raw = self.ai_engine.generate_text(prompt)
		except Exception as exc:
			logger.error('PipelinePlanner AI call failed: %s', exc)
			return self._fallback(task, pipeline_name, str(exc))

		parsed = extract_json(raw)
		if not parsed or not isinstance(parsed, dict):
			logger.warning('PipelinePlanner: JSON extraction failed')
			return self._fallback(task, pipeline_name, 'AI returned unparseable output')

		return self._normalise(parsed, task, pipeline_name, max_steps)

	def compile_to_yaml(self, plan: dict) -> str:
		"""Serialize a plan dict to YAML suitable for pipeline_runner."""
		out = {
			'name':        plan.get('pipeline_name', 'dynamic_pipeline'),
			'description': plan.get('description', ''),
			'steps':       plan.get('steps', []),
		}
		return yaml.dump(out, allow_unicode=True, default_flow_style=False, sort_keys=False)

	# ── Internals ─────────────────────────────────────────────────────────────

	def _normalise(
		self,
		parsed: dict,
		task: str,
		name_override: str,
		max_steps: int,
	) -> dict[str, Any]:
		valid    = _valid_capability_names()
		warnings: list[str] = []

		raw_steps = parsed.get('steps', [])
		if not isinstance(raw_steps, list):
			raw_steps = []

		# Filter and validate steps
		good_steps: list[dict] = []
		for s in raw_steps[:max_steps]:
			if not isinstance(s, dict):
				warnings.append(f'Dropped non-dict step: {s!r}')
				continue
			cap = str(s.get('capability', ''))
			if cap not in valid:
				warnings.append(f'Unknown capability {cap!r} removed from plan')
				continue
			params = s.get('params', {})
			if not isinstance(params, dict):
				warnings.append(f'Step {s.get("name")!r}: params reset to empty dict')
				params = {}
			good_steps.append({
				'name':       str(s.get('name') or cap),
				'capability': cap,
				'params':     params,
			})

		good_steps = _dedup_step_names(good_steps)

		pipeline_name = (
			name_override
			or str(parsed.get('pipeline_name', ''))
			or _slugify(task)
		)
		description = str(parsed.get('description', task[:120]))

		plan: dict[str, Any] = {
			'pipeline_name':     pipeline_name,
			'description':       description,
			'steps':             good_steps,
			'estimated_steps':   len(good_steps),
			'warnings':          warnings,
		}
		plan['yaml'] = self.compile_to_yaml(plan)
		return plan

	def _fallback(self, task: str, name_override: str, reason: str) -> dict[str, Any]:
		plan: dict[str, Any] = {
			'pipeline_name': name_override or _slugify(task),
			'description':   task[:120],
			'steps':         [],
			'estimated_steps': 0,
			'warnings':      [f'Planning failed: {reason}'],
		}
		plan['yaml'] = self.compile_to_yaml(plan)
		return plan


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
	"""Convert any string to a safe snake_case pipeline name."""
	s = re.sub(r'[^a-z0-9]+', '_', text.lower().strip())
	return s[:40].strip('_') or 'pipeline'

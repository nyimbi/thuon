# core/pipeline_runner.py
"""
Pipeline-as-YAML executor.

Define multi-step capability workflows in YAML; the runner resolves
{input.x} and {steps.step_name.key} template variables at runtime.

Example YAML (thuon_platform/data/pipelines/competitive_report.yaml):

  name: competitive_report
  description: Full competitive intelligence report as PDF
  steps:
    - name: market
      capability: market_sales_research
      params:
        industry: "{input.industry}"
    - name: intel
      capability: competitive_intelligence_operative
      params:
        company_name: "{input.company}"
        industry: "{steps.market.market_size}"
    - name: report
      capability: document_generator
      params:
        topic: "Competitive analysis: {input.company}"
        format: pdf
        context: "{steps.intel.analysis}"
"""

from __future__ import annotations
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from core.pipeline_hooks import PipelineHooks
	from thuon import Thuon

logger = logging.getLogger('thuon.pipeline_runner')


from core.bundle import pipelines_dir as _pd
_PIPELINES_DIR = str(_pd())


def _resolve_template(value: Any, inputs: dict, step_results: dict) -> Any:
	"""Substitute {input.x} and {steps.name.key} in string values."""
	if not isinstance(value, str):
		return value
	def replacer(m: re.Match) -> str:
		expr = m.group(1)
		parts = expr.split('.')
		try:
			if parts[0] == 'input':
				return str(inputs.get(parts[1], m.group(0)))
			elif parts[0] == 'steps' and len(parts) >= 3:
				step = step_results.get(parts[1], {})
				result = step
				for part in parts[2:]:
					if isinstance(result, dict):
						result = result.get(part, m.group(0))
					else:
						return str(result)
				return str(result)
		except (IndexError, KeyError):
			pass
		return m.group(0)
	return re.sub(r'\{([^}]+)\}', replacer, value)


def _resolve_params(params: dict, inputs: dict, step_results: dict) -> dict:
	return {
		k: _resolve_template(v, inputs, step_results)
		for k, v in params.items()
	}


class PipelineRunner:
	def __init__(self, platform: 'Thuon', hooks: 'PipelineHooks | None' = None):
		self._platform = platform
		self._hooks = hooks

	def run(self, pipeline: str | dict, inputs: dict | None = None) -> Any:
		"""
		Run a pipeline.

		Args:
			pipeline: Pipeline name, path to YAML file, or inline dict
			inputs:   Template variable values (accessible as {input.x})
		"""
		inputs = inputs or {}
		spec = self._load(pipeline)
		pipeline_name = spec.get('name', '')
		step_results: dict[str, dict] = {}
		last_result = None
		hooks = self._hooks
		_hooks_active = hooks and not hooks.is_empty()
		if _hooks_active:
			from core.pipeline_hooks import StepEvent

		for step in spec.get('steps', []):
			step_name  = step.get('name') or step.get('capability', f'step_{len(step_results)}')
			cap_name   = step['capability']
			raw_params = step.get('params', {})
			params     = _resolve_params(raw_params, inputs, step_results)

			if _hooks_active:
				hooks.fire_before(StepEvent(
					pipeline_name=pipeline_name,
					step_name=step_name,
					cap_name=cap_name,
					params=params,
				))

			t0 = time.monotonic()
			try:
				proxy  = getattr(self._platform, cap_name)
				result = proxy(**params)
				elapsed = time.monotonic() - t0
			except Exception as exc:
				elapsed = time.monotonic() - t0
				logger.error('Pipeline %s step %s failed: %s', pipeline_name, step_name, exc)
				if _hooks_active:
					hooks.fire_error(StepEvent(
						pipeline_name=pipeline_name,
						step_name=step_name,
						cap_name=cap_name,
						params=params,
						elapsed=elapsed,
						error=exc,
					))
				raise

			# Normalize result for step_results template resolution
			if hasattr(result, 'to_dict'):
				step_results[step_name] = result.to_dict()
			else:
				step_results[step_name] = result if isinstance(result, dict) else {'result': result}
			last_result = result

			if _hooks_active:
				hooks.fire_after(StepEvent(
					pipeline_name=pipeline_name,
					step_name=step_name,
					cap_name=cap_name,
					params=params,
					result=step_results[step_name],
					elapsed=elapsed,
				))

		if _hooks_active:
			hooks.fire_complete(StepEvent(
				pipeline_name=pipeline_name,
				step_name='__complete__',
				cap_name='',
				params={},
			))

		from core.result import ThuonResult
		return ThuonResult(
			{'pipeline': pipeline_name, 'steps': step_results},
			capability_name=f'pipeline:{pipeline_name}',
		) if last_result is None else last_result

	def _load(self, pipeline: str | dict) -> dict:
		if isinstance(pipeline, dict):
			return pipeline
		import yaml
		# Try as file path first
		if os.path.exists(pipeline):
			with open(pipeline) as f:
				return yaml.safe_load(f)
		# Try in the pipelines directory
		candidates = [
			pipeline,
			os.path.join(_PIPELINES_DIR, pipeline),
			os.path.join(_PIPELINES_DIR, f'{pipeline}.yaml'),
			os.path.join(_PIPELINES_DIR, f'{pipeline}.yml'),
		]
		for path in candidates:
			if os.path.exists(path):
				with open(path) as f:
					return yaml.safe_load(f)
		raise FileNotFoundError(
			f'Pipeline {pipeline!r} not found. '
			f'Place YAML files in {_PIPELINES_DIR}/'
		)

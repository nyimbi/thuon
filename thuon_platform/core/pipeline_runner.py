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

class _NoopCheckpointStore:
	"""Used when the real store fails to initialise — all ops are no-ops."""
	def start_run(self, *a, **kw) -> str:              return ''
	def save_step(self, *a, **kw) -> None:             pass
	def mark_completed(self, *a, **kw) -> None:        pass
	def mark_failed(self, *a, **kw) -> None:           pass
	def get_step_results(self, run_id: str) -> dict:   return {}
	def resume_run(self, run_id: str) -> dict | None:  return None


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
	def __init__(
		self,
		platform: 'Thuon',
		hooks: 'PipelineHooks | None' = None,
		checkpoint_store=None,
	):
		self._platform = platform
		self._hooks = hooks
		self._checkpoint_store = checkpoint_store

	def _get_checkpoint_store(self):
		if not self._checkpoint_store:
			try:
				from core.pipeline_checkpoint_store import get_checkpoint_store
				self._checkpoint_store = get_checkpoint_store()
			except Exception:
				pass
		return self._checkpoint_store

	def run(
		self,
		pipeline: str | dict,
		inputs: dict | None = None,
		run_id: str | None = None,
	) -> Any:
		"""
		Run a pipeline with step-level checkpointing.

		Args:
			pipeline:  Pipeline name, path to YAML file, or inline dict
			inputs:    Template variable values (accessible as {input.x})
			run_id:    Supply an existing run_id to resume a previously
			           interrupted run from the last successful step.
			           Completed steps are replayed from the checkpoint store
			           without re-executing.  Omit to start a fresh run.
		"""
		inputs = inputs or {}
		spec = self._load(pipeline)
		pipeline_name = spec.get('name', '')

		cs = self._get_checkpoint_store()

		if run_id:
			resume_data = cs.resume_run(run_id) if cs else None
		else:
			run_id = cs.start_run(pipeline_name, inputs) if cs else None
			resume_data = None

		# Restore already-completed steps
		if resume_data:
			step_results: dict[str, dict] = dict(resume_data.get('completed_steps', {}))
			resume_from: str | None = resume_data.get('resume_from_step')
			logger.info(
				'Resuming pipeline %s run %s (%d steps already done)',
				pipeline_name, run_id, len(step_results),
			)
		else:
			step_results = {}
			resume_from = None

		last_result = None
		hooks = self._hooks
		_hooks_active = hooks and not hooks.is_empty()
		if _hooks_active:
			from core.pipeline_hooks import StepEvent

		try:
			for step in spec.get('steps', []):
				step_name  = step.get('name') or step.get('capability', f'step_{len(step_results)}')
				cap_name   = step['capability']
				raw_params = step.get('params', {})
				params     = _resolve_params(raw_params, inputs, step_results)

				# Resume logic: skip steps that have already been completed
				if resume_from and step_name != resume_from:
					if step_name in step_results:
						continue  # already completed
				elif resume_from and step_name == resume_from:
					resume_from = None  # start executing from here

				# Also skip steps replayed via completed_steps (no resume_from set)
				if not resume_from and step_name in (resume_data or {}).get('completed_steps', {}):
					logger.debug('Pipeline %s step %s: replaying from checkpoint', pipeline_name, step_name)
					last_result = step_results[step_name]
					continue

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
					if cs and run_id:
						cs.mark_failed(run_id, step_name, str(exc))
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

				# Normalize result for template resolution and checkpointing
				if hasattr(result, 'to_dict'):
					step_dict = result.to_dict()
				else:
					step_dict = result if isinstance(result, dict) else {'result': result}
				step_results[step_name] = step_dict
				last_result = result

				if cs and run_id:
					cs.save_step(run_id, step_name, cap_name, step_dict, elapsed)

				if _hooks_active:
					hooks.fire_after(StepEvent(
						pipeline_name=pipeline_name,
						step_name=step_name,
						cap_name=cap_name,
						params=params,
						result=step_dict,
						elapsed=elapsed,
					))

		except Exception:
			raise
		else:
			if cs and run_id:
				cs.mark_completed(run_id)

		if _hooks_active:
			hooks.fire_complete(StepEvent(
				pipeline_name=pipeline_name,
				step_name='__complete__',
				cap_name='',
				params={},
			))

		from core.result import ThuonResult
		return ThuonResult(
			{'pipeline': pipeline_name, 'steps': step_results, 'run_id': run_id},
			capability_name=f'pipeline:{pipeline_name}',
		) if last_result is None else last_result

	def resume(self, run_id: str, inputs: dict | None = None) -> Any:
		"""Resume a previously interrupted pipeline run by its run_id.

		Args:
			run_id: The run identifier returned when the run was originally started.
			inputs: Optional overrides merged on top of the stored inputs.

		Returns:
			The final pipeline result, same as ``run()``.
		"""
		cs = self._get_checkpoint_store()
		if not cs:
			raise RuntimeError('No checkpoint store available')
		resume_data = cs.resume_run(run_id)
		if not resume_data:
			raise ValueError(f'Run {run_id!r} not found or not resumable')
		pipeline_name = resume_data['run']['pipeline_name']
		stored_inputs = resume_data['run'].get('inputs', {})
		merged_inputs = {**stored_inputs, **(inputs or {})}
		return self.run(pipeline_name, merged_inputs, run_id=run_id)

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

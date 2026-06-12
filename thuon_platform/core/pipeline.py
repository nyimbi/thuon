"""
Capability chaining — run multiple capabilities in sequence, feeding each
result into the next step as enriched context.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PipelineStep:
	name: str
	fn: Callable[..., dict]
	# keys from prior results to inject into this step's kwargs
	inject_keys: list[str] = field(default_factory=list)
	# override kwargs (static)
	kwargs: dict[str, Any] = field(default_factory=dict)


class Pipeline:
	"""
	Chain capability calls, passing selected keys from each result into the next.

	Usage:
		p = Pipeline()
		p.add_step('research', assistant.perform_research, kwargs={'query': q})
		p.add_step('report', writer.write_report, inject_keys=['summary', 'sources'])
		result = p.run()
	"""

	def __init__(self) -> None:
		self._steps: list[PipelineStep] = []
		self._results: dict[str, dict] = {}

	def add_step(
		self,
		name: str,
		fn: Callable[..., dict],
		inject_keys: list[str] | None = None,
		**kwargs: Any,
	) -> 'Pipeline':
		self._steps.append(PipelineStep(
			name=name,
			fn=fn,
			inject_keys=inject_keys or [],
			kwargs=kwargs,
		))
		return self

	def run(self) -> dict:
		"""
		Execute all steps in order.
		Returns a dict with:
		  - 'steps': {step_name: result_dict, ...}
		  - 'final': the last step's result dict
		  - 'status': 'ok' | 'error'
		  - 'error_step': name of step that failed (if any)
		"""
		accumulated: dict[str, Any] = {}

		for step in self._steps:
			call_kwargs = dict(step.kwargs)
			# inject selected keys from accumulated context
			for key in step.inject_keys:
				if key in accumulated:
					call_kwargs[key] = accumulated[key]
			try:
				result = step.fn(**call_kwargs)
				self._results[step.name] = result
				# flatten the result into accumulated context for downstream steps
				if isinstance(result, dict):
					accumulated.update(result)
			except Exception as exc:
				error_result: dict = {
					'status': 'error',
					'error': str(exc),
					'step': step.name,
				}
				self._results[step.name] = error_result
				return {
					'steps':      self._results,
					'final':      error_result,
					'status':     'error',
					'error_step': step.name,
				}

		final = self._results[self._steps[-1].name] if self._steps else {}
		return {
			'steps':  self._results,
			'final':  final,
			'status': 'ok',
		}

	def get_step_result(self, name: str) -> dict:
		return self._results.get(name, {})

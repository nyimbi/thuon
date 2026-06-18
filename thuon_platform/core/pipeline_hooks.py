# core/pipeline_hooks.py
"""
Lifecycle hooks for PipelineRunner.

Capabilities call nothing — hooks are registered externally and fire
automatically around each pipeline step.  Zero breaking changes: the
PipelineRunner works identically without any hooks registered.

Usage::

  from core.pipeline_hooks import PipelineHooks, StepEvent, build_hooks_from_context

  # Wire context-aware hooks (notifications + memory logging)
  hooks = build_hooks_from_context(skill_context, pipeline_name='rfp_response')

  runner = PipelineRunner(platform, hooks=hooks)
  runner.run('rfp_response', inputs)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
	from core.skill_context import SkillContext


# ── Event ─────────────────────────────────────────────────────────────────────

@dataclass
class StepEvent:
	"""Passed to every hook function."""

	pipeline_name: str
	step_name: str
	cap_name: str
	params: dict[str, Any]
	result: dict[str, Any] | None = None   # None for before_step
	elapsed: float | None = None
	error: Exception | None = None


# ── Hooks container ───────────────────────────────────────────────────────────

HookFn = Callable[[StepEvent], None]


@dataclass
class PipelineHooks:
	"""
	Ordered lists of callables fired at each lifecycle point.

	All hooks receive a `StepEvent`.  Exceptions inside a hook are caught
	and logged — they never abort the pipeline.
	"""

	before_step: list[HookFn] = field(default_factory=list)
	after_step:  list[HookFn] = field(default_factory=list)
	on_error:    list[HookFn] = field(default_factory=list)
	on_complete: list[HookFn] = field(default_factory=list)

	def fire_before(self, event: StepEvent) -> None:
		_fire_all(self.before_step, event)

	def fire_after(self, event: StepEvent) -> None:
		_fire_all(self.after_step, event)

	def fire_error(self, event: StepEvent) -> None:
		_fire_all(self.on_error, event)

	def fire_complete(self, event: StepEvent) -> None:
		_fire_all(self.on_complete, event)

	def is_empty(self) -> bool:
		return not any([
			self.before_step, self.after_step,
			self.on_error, self.on_complete,
		])


def _fire_all(hooks: list[HookFn], event: StepEvent) -> None:
	import logging
	log = logging.getLogger('thuon.pipeline_hooks')
	for fn in hooks:
		try:
			fn(event)
		except Exception as exc:
			log.warning('Pipeline hook %s raised: %s', fn.__name__, exc)


# ── Context-aware hook builder ────────────────────────────────────────────────

def build_hooks_from_context(
	context: SkillContext,
	pipeline_name: str = '',
) -> PipelineHooks:
	"""
	Build a PipelineHooks instance wired to the given SkillContext.

	Registers:
	  - before_step  → notification 'pipeline_step_started'
	  - after_step   → notification 'pipeline_step_done' + memory episode
	  - on_error     → notification 'pipeline_step_error'
	  - on_complete  → notification 'pipeline_complete'
	"""
	hooks = PipelineHooks()

	if context.notification_bus is not None:
		def _notify_before(ev: StepEvent) -> None:
			context.notification_bus.publish(  # type: ignore[union-attr]
				event='pipeline_step_started',
				title=f'{ev.pipeline_name}: {ev.step_name} starting',
				body=f'Capability: {ev.cap_name}',
			)

		def _notify_after(ev: StepEvent) -> None:
			context.notification_bus.publish(  # type: ignore[union-attr]
				event='pipeline_step_done',
				title=f'{ev.pipeline_name}: {ev.step_name} done',
				body=f'{ev.cap_name} completed in {ev.elapsed:.1f}s',
			)

		def _notify_error(ev: StepEvent) -> None:
			context.notification_bus.publish(  # type: ignore[union-attr]
				event='pipeline_step_error',
				title=f'{ev.pipeline_name}: {ev.step_name} failed',
				body=str(ev.error),
			)

		def _notify_complete(ev: StepEvent) -> None:
			context.notification_bus.publish(  # type: ignore[union-attr]
				event='pipeline_complete',
				title=f'{ev.pipeline_name} completed',
			)

		hooks.before_step.append(_notify_before)
		hooks.after_step.append(_notify_after)
		hooks.on_error.append(_notify_error)
		hooks.on_complete.append(_notify_complete)

	if context.memory_store is not None:
		def _log_step(ev: StepEvent) -> None:
			try:
				context.memory_store.add_episode(  # type: ignore[union-attr]
					content=(
						f'Pipeline {ev.pipeline_name!r} step {ev.step_name!r} '
						f'({ev.cap_name}) completed in {ev.elapsed:.1f}s'
					),
					source='pipeline_runner',
				)
			except Exception:
				pass

		hooks.after_step.append(_log_step)

	return hooks

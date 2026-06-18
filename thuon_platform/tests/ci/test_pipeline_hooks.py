# tests/ci/test_pipeline_hooks.py
"""
Unit tests for PipelineHooks, StepEvent, and build_hooks_from_context.
No network, no LLM, no database.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from core.pipeline_hooks import (
	PipelineHooks,
	StepEvent,
	build_hooks_from_context,
)
from core.skill_context import SkillContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event(**kw) -> StepEvent:
	defaults = dict(
		pipeline_name='test_pipe',
		step_name='step1',
		cap_name='research_assistant',
		params={'query': 'AI'},
	)
	return StepEvent(**{**defaults, **kw})


# ── PipelineHooks.is_empty ────────────────────────────────────────────────────

def test_hooks_empty_by_default():
	assert PipelineHooks().is_empty()


def test_hooks_not_empty_with_before():
	h = PipelineHooks(before_step=[lambda e: None])
	assert not h.is_empty()


def test_hooks_not_empty_with_on_complete():
	h = PipelineHooks(on_complete=[lambda e: None])
	assert not h.is_empty()


# ── PipelineHooks.fire_* ──────────────────────────────────────────────────────

def test_fire_before_calls_all():
	called = []
	h = PipelineHooks(
		before_step=[
			lambda e: called.append('a'),
			lambda e: called.append('b'),
		]
	)
	h.fire_before(_event())
	assert called == ['a', 'b']


def test_fire_after_calls_all():
	called = []
	h = PipelineHooks(after_step=[lambda e: called.append(e.step_name)])
	h.fire_after(_event(step_name='ingest'))
	assert called == ['ingest']


def test_fire_error_passes_exception():
	received = []
	h = PipelineHooks(on_error=[lambda e: received.append(e.error)])
	exc = ValueError('db down')
	h.fire_error(_event(error=exc))
	assert received[0] is exc


def test_fire_complete_receives_event():
	received = []
	h = PipelineHooks(on_complete=[lambda e: received.append(e.pipeline_name)])
	h.fire_complete(_event(pipeline_name='rfp_response', step_name='__complete__'))
	assert received == ['rfp_response']


def test_hook_exception_does_not_abort_pipeline(caplog):
	"""A hook that raises must not stop other hooks or the pipeline."""
	import logging
	results = []

	def bad_hook(e: StepEvent) -> None:
		raise RuntimeError('hook exploded')

	def good_hook(e: StepEvent) -> None:
		results.append('ok')

	h = PipelineHooks(before_step=[bad_hook, good_hook])
	with caplog.at_level(logging.WARNING, logger='thuon.pipeline_hooks'):
		h.fire_before(_event())

	assert results == ['ok']
	assert any('hook exploded' in r.message for r in caplog.records)


def test_multiple_hooks_all_fired():
	calls = []
	h = PipelineHooks(
		before_step=[lambda e: calls.append('before1'), lambda e: calls.append('before2')],
		after_step=[lambda e: calls.append('after')],
	)
	ev = _event()
	h.fire_before(ev)
	h.fire_after(ev)
	assert calls == ['before1', 'before2', 'after']


# ── build_hooks_from_context ──────────────────────────────────────────────────

def test_no_bus_no_store_returns_empty_hooks():
	ctx = SkillContext()
	hooks = build_hooks_from_context(ctx)
	assert hooks.is_empty()


def test_bus_registers_all_four_hook_types():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	hooks = build_hooks_from_context(ctx, pipeline_name='rfp_response')
	assert not hooks.is_empty()
	assert len(hooks.before_step) == 1
	assert len(hooks.after_step) == 1
	assert len(hooks.on_error) == 1
	assert len(hooks.on_complete) == 1


def test_bus_before_step_publishes_started():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	hooks = build_hooks_from_context(ctx, pipeline_name='rfp_response')
	hooks.fire_before(_event(pipeline_name='rfp_response', step_name='ingest'))
	bus.publish.assert_called_once()
	kwargs = bus.publish.call_args.kwargs
	assert kwargs['event'] == 'pipeline_step_started'
	assert 'ingest' in kwargs['title']


def test_bus_after_step_publishes_done():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	hooks = build_hooks_from_context(ctx)
	hooks.fire_after(_event(step_name='analyze', elapsed=1.23))
	bus.publish.assert_called_once()
	kwargs = bus.publish.call_args.kwargs
	assert kwargs['event'] == 'pipeline_step_done'
	assert '1.2' in kwargs['body']


def test_bus_on_error_publishes_error():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	hooks = build_hooks_from_context(ctx)
	hooks.fire_error(_event(error=RuntimeError('oops'), elapsed=0.1))
	kwargs = bus.publish.call_args.kwargs
	assert kwargs['event'] == 'pipeline_step_error'
	assert 'oops' in kwargs['body']


def test_bus_on_complete_publishes_complete():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	hooks = build_hooks_from_context(ctx, pipeline_name='blog_post')
	hooks.fire_complete(_event(pipeline_name='blog_post', step_name='__complete__'))
	kwargs = bus.publish.call_args.kwargs
	assert kwargs['event'] == 'pipeline_complete'
	assert 'blog_post' in kwargs['title']


def test_memory_store_registers_after_hook():
	mem = MagicMock()
	ctx = SkillContext(memory_store=mem)
	hooks = build_hooks_from_context(ctx)
	assert len(hooks.after_step) == 1
	hooks.fire_after(_event(elapsed=2.5, step_name='write'))
	mem.add_episode.assert_called_once()
	content = mem.add_episode.call_args.kwargs['content']
	assert 'write' in content


def test_memory_store_exception_is_swallowed():
	mem = MagicMock()
	mem.add_episode.side_effect = RuntimeError('db down')
	ctx = SkillContext(memory_store=mem)
	hooks = build_hooks_from_context(ctx)
	hooks.fire_after(_event(elapsed=1.0))  # must not raise


def test_both_bus_and_store_registered():
	bus = MagicMock()
	mem = MagicMock()
	ctx = SkillContext(notification_bus=bus, memory_store=mem)
	hooks = build_hooks_from_context(ctx)
	# after_step: 1 bus hook + 1 memory hook
	assert len(hooks.after_step) == 2
	hooks.fire_after(_event(elapsed=0.5))
	bus.publish.assert_called_once()
	mem.add_episode.assert_called_once()

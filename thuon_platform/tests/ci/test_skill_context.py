# tests/ci/test_skill_context.py
"""
Unit tests for SkillContext and build_context.
No network, no LLM, no database.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from core.skill_context import SkillContext, build_context


# ── SkillContext defaults ─────────────────────────────────────────────────────

def test_skill_context_defaults():
	ctx = SkillContext()
	assert ctx.memory_store is None
	assert ctx.session_store is None
	assert ctx.calendar_store is None
	assert ctx.notification_bus is None
	assert ctx.user_prefs == {}
	assert ctx.session_id == ''


def test_skill_context_with_values():
	mem = MagicMock()
	ctx = SkillContext(memory_store=mem, session_id='abc123')
	assert ctx.memory_store is mem
	assert ctx.session_id == 'abc123'


# ── notify ────────────────────────────────────────────────────────────────────

def test_notify_calls_bus():
	bus = MagicMock()
	ctx = SkillContext(notification_bus=bus)
	ctx.notify('rfp_found', 'New RFP', body='details', url='/rfps/1')
	bus.publish.assert_called_once_with(
		event='rfp_found', title='New RFP', body='details', url='/rfps/1'
	)


def test_notify_no_bus_is_noop():
	ctx = SkillContext()
	ctx.notify('rfp_found', 'New RFP')  # must not raise


# ── remember ─────────────────────────────────────────────────────────────────

def test_remember_calls_memory_store():
	mem = MagicMock()
	ctx = SkillContext(memory_store=mem)
	ctx.remember('Signed contract with Acme', source='contract_renegotiator')
	mem.add_episode.assert_called_once_with(
		content='Signed contract with Acme', source='contract_renegotiator'
	)


def test_remember_no_store_is_noop():
	ctx = SkillContext()
	ctx.remember('anything')  # must not raise


def test_remember_store_exception_is_swallowed():
	mem = MagicMock()
	mem.add_episode.side_effect = RuntimeError('db down')
	ctx = SkillContext(memory_store=mem)
	ctx.remember('test')  # must not raise


# ── calendar_today ────────────────────────────────────────────────────────────

def test_calendar_today_returns_events():
	cal = MagicMock()
	cal.for_date.return_value = [{'title': 'Board meeting', 'date': '2026-06-13'}]
	ctx = SkillContext(calendar_store=cal)
	events = ctx.calendar_today('2026-06-13')
	assert len(events) == 1
	assert events[0]['title'] == 'Board meeting'


def test_calendar_today_no_store_returns_empty():
	ctx = SkillContext()
	assert ctx.calendar_today('2026-06-13') == []


def test_calendar_today_no_date_returns_empty():
	cal = MagicMock()
	ctx = SkillContext(calendar_store=cal)
	assert ctx.calendar_today('') == []
	cal.for_date.assert_not_called()


def test_calendar_today_store_exception_returns_empty():
	cal = MagicMock()
	cal.for_date.side_effect = RuntimeError('db error')
	ctx = SkillContext(calendar_store=cal)
	assert ctx.calendar_today('2026-06-13') == []


# ── build_context ─────────────────────────────────────────────────────────────

def test_build_context_from_services():
	mem = MagicMock()
	cal = MagicMock()
	bus = MagicMock()
	services = {
		'memory_store':     mem,
		'calendar_store':   cal,
		'notification_bus': bus,
		'ai_engine':        MagicMock(),  # unrelated — should be ignored
	}
	ctx = build_context(services, session_id='sess-42')
	assert ctx.memory_store is mem
	assert ctx.calendar_store is cal
	assert ctx.notification_bus is bus
	assert ctx.session_id == 'sess-42'


def test_build_context_empty_services():
	ctx = build_context({})
	assert ctx.memory_store is None
	assert ctx.session_id == ''


def test_build_context_missing_keys_graceful():
	ctx = build_context({'ai_engine': MagicMock()})
	assert ctx.memory_store is None
	assert ctx.notification_bus is None

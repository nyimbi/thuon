# tests/ci/test_notification_bus.py
"""
Unit tests for NotificationBus and Notification.
No network, no disk, no LLM.
"""
from __future__ import annotations

import pytest

from core.notification_bus import Notification, NotificationBus


# ── Notification ──────────────────────────────────────────────────────────────

def test_notification_to_dict():
	n = Notification(event='rfp_found', title='New RFP', body='Details here', url='/rfp/1')
	d = n.to_dict()
	assert d['event'] == 'rfp_found'
	assert d['title'] == 'New RFP'
	assert d['body'] == 'Details here'
	assert d['url'] == '/rfp/1'
	assert 'ts' in d
	assert 'read' in d


def test_notification_to_sse_format():
	n = Notification(event='rfp_found', title='Test')
	sse = n.to_sse()
	assert 'data:' in sse
	assert 'rfp_found' in sse


def test_notification_defaults():
	n = Notification(event='ping', title='Hello')
	assert n.body == ''
	assert n.url == ''


# ── NotificationBus.publish ───────────────────────────────────────────────────

def test_publish_adds_to_history():
	bus = NotificationBus()
	bus.publish(event='test', title='Hello')
	assert len(bus.history()) == 1


def test_publish_multiple():
	bus = NotificationBus()
	bus.publish(event='a', title='A')
	bus.publish(event='b', title='B')
	assert len(bus.history()) == 2


def test_history_most_recent_first():
	bus = NotificationBus()
	bus.publish(event='first', title='First')
	bus.publish(event='second', title='Second')
	h = bus.history()
	assert h[0]['event'] == 'second'


def test_history_limit():
	bus = NotificationBus()
	for i in range(10):
		bus.publish(event='e', title=f'N{i}')
	assert len(bus.history(limit=3)) == 3


# ── Unread count ──────────────────────────────────────────────────────────────

def test_unread_count_increments():
	bus = NotificationBus()
	assert bus.unread_count() == 0
	bus.publish(event='x', title='T')
	assert bus.unread_count() == 1
	bus.publish(event='y', title='U')
	assert bus.unread_count() == 2


def test_mark_all_read_zeroes_count():
	bus = NotificationBus()
	bus.publish(event='x', title='T')
	bus.publish(event='y', title='U')
	bus.mark_all_read()
	assert bus.unread_count() == 0


def test_mark_all_read_does_not_clear_history():
	bus = NotificationBus()
	bus.publish(event='x', title='T')
	bus.mark_all_read()
	assert len(bus.history()) == 1


# ── Retention cap ─────────────────────────────────────────────────────────────

def test_history_does_not_grow_unbounded():
	bus = NotificationBus()
	for i in range(200):
		bus.publish(event='flood', title=f'N{i}')
	# retention cap is 50 per spec
	assert len(bus.history(limit=1000)) <= 100

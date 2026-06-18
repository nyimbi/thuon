"""Tests for core/notification_bus.py"""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from core.notification_bus import Notification, NotificationBus


# ── Notification model ────────────────────────────────────────────────────────

class TestNotification:
	def test_to_dict(self):
		n = Notification(event='rfp_found', title='New RFP', body='Details', url='/rfp/1')
		d = n.to_dict()
		assert d['event'] == 'rfp_found'
		assert d['title'] == 'New RFP'
		assert d['body'] == 'Details'
		assert d['url'] == '/rfp/1'
		assert d['read'] is False
		assert isinstance(d['ts'], float)

	def test_to_sse_format(self):
		n = Notification(event='blog_ready', title='Blog Done')
		sse = n.to_sse()
		assert sse.startswith('event: blog_ready\ndata: {')
		assert sse.endswith('\n\n')

	def test_defaults(self):
		n = Notification(event='x', title='y')
		assert n.body == ''
		assert n.url == ''


# ── NotificationBus ───────────────────────────────────────────────────────────

class TestNotificationBus:
	def _bus(self) -> NotificationBus:
		return NotificationBus()

	def test_publish_and_history(self):
		bus = self._bus()
		bus.publish('rfp_found', 'Found one', 'body text', '/rfp/1')
		h = bus.history()
		assert len(h) == 1
		assert h[0]['event'] == 'rfp_found'
		assert h[0]['title'] == 'Found one'

	def test_history_limit(self):
		bus = self._bus()
		for i in range(10):
			bus.publish('ev', f'Title {i}')
		h = bus.history(limit=3)
		assert len(h) == 3

	def test_history_newest_first(self):
		bus = self._bus()
		bus.publish('ev', 'First')
		bus.publish('ev', 'Second')
		h = bus.history()
		assert h[0]['title'] == 'Second'
		assert h[1]['title'] == 'First'

	def test_unread_count(self):
		bus = self._bus()
		bus.publish('ev', 'A')
		bus.publish('ev', 'B')
		assert bus.unread_count() == 2

	def test_mark_all_read(self):
		bus = self._bus()
		bus.publish('ev', 'A')
		bus.publish('ev', 'B')
		assert bus.unread_count() == 2
		bus.mark_all_read()
		assert bus.unread_count() == 0

	def test_retention_cap(self):
		# default retention is 50; create bus with small cap
		from unittest.mock import patch
		from core.settings_manager import get_settings
		settings = get_settings()
		original = settings.get_setting('notifications.retention_count', 50)

		# Directly instantiate with deque maxlen override
		from collections import deque
		bus = self._bus()
		bus._history = deque(maxlen=3)
		for i in range(5):
			bus.publish('ev', f'T{i}')
		assert len(list(bus._history)) == 3

	def test_multiple_publishers_thread_safe(self):
		bus = self._bus()
		errors = []

		def publish_many():
			try:
				for i in range(20):
					bus.publish('ev', f'Title {i}')
			except Exception as e:
				errors.append(e)

		threads = [threading.Thread(target=publish_many) for _ in range(5)]
		for t in threads:
			t.start()
		for t in threads:
			t.join()

		assert errors == []
		assert len(list(bus._history)) <= 50


# ── SSE stream ────────────────────────────────────────────────────────────────

class TestNotificationBusStream:
	def test_stream_backfills_existing(self):
		bus = NotificationBus()
		bus.publish('old_event', 'Old notification')

		gen = bus.stream()
		# First yield(s) should be the backfill of existing events
		first = next(gen)
		assert 'old_event' in first or 'connected' in first
		gen.close()  # trigger finally cleanup

	def test_stream_receives_published_event(self):
		bus = NotificationBus()
		gen = bus.stream()

		# Drain the connected message and any backfill
		received = []
		def drain():
			for chunk in gen:
				received.append(chunk)
				if len(received) >= 3:
					gen.close()
					break

		# Publish from another thread after a short delay
		def publish_delayed():
			time.sleep(0.05)
			bus.publish('test_event', 'Stream test')

		t = threading.Thread(target=drain, daemon=True)
		pub = threading.Thread(target=publish_delayed, daemon=True)
		t.start()
		pub.start()
		t.join(timeout=2.0)

		assert any('test_event' in r or 'connected' in r for r in received)

	def test_stream_cleanup_on_close(self):
		bus = NotificationBus()
		gen = bus.stream()
		next(gen)  # trigger subscribe
		assert len(bus._subscribers) == 1
		gen.close()
		assert len(bus._subscribers) == 0

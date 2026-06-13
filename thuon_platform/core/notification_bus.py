# core/notification_bus.py
"""
Thread-safe notification bus for Thuon events.
SSE consumers call `stream()` to receive a Server-Sent Events generator.
"""

from __future__ import annotations
import json
import queue
import threading
import time
from collections import deque
from typing import Generator

from core.settings_manager import get_settings


class Notification:
	__slots__ = ('event', 'title', 'body', 'url', 'ts', 'read')

	def __init__(self, event: str, title: str, body: str = '', url: str = ''):
		self.event = event
		self.title = title
		self.body  = body
		self.url   = url
		self.ts    = time.time()
		self.read  = False

	def to_dict(self) -> dict:
		return {
			'event': self.event,
			'title': self.title,
			'body':  self.body,
			'url':   self.url,
			'ts':    self.ts,
			'read':  self.read,
		}

	def to_sse(self) -> str:
		return f"event: {self.event}\ndata: {json.dumps(self.to_dict())}\n\n"


class NotificationBus:
	def __init__(self):
		settings = get_settings()
		retention = settings.get_setting('notifications.retention_count', 50)
		self._history: deque[Notification] = deque(maxlen=retention)
		self._subscribers: list[queue.Queue] = []
		self._lock = threading.Lock()

	def publish(self, event: str, title: str, body: str = '', url: str = '') -> None:
		n = Notification(event, title, body, url)
		now = time.monotonic()
		with self._lock:
			self._history.appendleft(n)
			dead = []
			for q in self._subscribers:
				try:
					q.put_nowait(n)
				except queue.Full:
					dead.append(q)
				else:
					# Evict stale subscribers whose GeneratorExit was swallowed (e.g. Gunicorn sync)
					if now - getattr(q, '_subscribed_at', now) > 600:
						dead.append(q)
			for q in dead:
				self._subscribers.remove(q)

	def history(self, limit: int = 20) -> list[dict]:
		return [n.to_dict() for n in list(self._history)[:limit]]

	def unread_count(self) -> int:
		return sum(1 for n in self._history if not n.read)

	def mark_all_read(self) -> None:
		for n in self._history:
			n.read = True

	def stream(self) -> Generator[str, None, None]:
		"""SSE generator — subscribe, yield events, clean up on disconnect."""
		q: queue.Queue = queue.Queue(maxsize=100)
		q._subscribed_at = time.monotonic()  # type: ignore[attr-defined]
		with self._lock:
			self._subscribers.append(q)
		try:
			# Backfill last 5 unread events on connect
			for n in reversed(list(self._history)[:5]):
				yield n.to_sse()
			yield "data: {\"type\": \"connected\"}\n\n"
			while True:
				try:
					n = q.get(timeout=25)
					yield n.to_sse()
				except queue.Empty:
					yield ": keepalive\n\n"
		finally:
			with self._lock:
				try:
					self._subscribers.remove(q)
				except ValueError:
					pass


# Module-level singleton
_bus: NotificationBus | None = None
_bus_lock = threading.Lock()


def get_notification_bus() -> NotificationBus:
	global _bus
	if _bus is None:
		with _bus_lock:
			if _bus is None:
				_bus = NotificationBus()
	return _bus

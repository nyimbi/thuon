# core/skill_context.py
"""
SkillContext — runtime context threaded through capability invocations.

Capabilities opt in by declaring a `context` parameter:

  def generate(self, topic: str, context: SkillContext | None = None) -> dict:
      if context and context.memory_store:
          prior = context.memory_store.get_context_block(topic)
          ...

The web app builds a SkillContext from available services and injects it when
the capability's method signature accepts it.  Capabilities that don't declare
`context` receive nothing — zero breaking changes to existing capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from core.calendar_store import CalendarStore
	from core.memory_store import MemoryStore
	from core.notification_bus import NotificationBus
	from core.session_store import SessionStore


@dataclass
class SkillContext:
	"""
	Mutable platform-state bundle passed to capabilities that want it.

	All fields are optional — capabilities only use what they need.
	"""

	memory_store: MemoryStore | None = None
	session_store: SessionStore | None = None
	calendar_store: CalendarStore | None = None
	notification_bus: NotificationBus | None = None
	user_prefs: dict[str, Any] = field(default_factory=dict)
	session_id: str = ''

	def notify(self, event: str, title: str, body: str = '', url: str = '') -> None:
		"""Fire a notification if a bus is available; silently no-op otherwise."""
		if self.notification_bus is None:
			return
		self.notification_bus.publish(event=event, title=title, body=body, url=url)

	def remember(self, content: str, source: str = 'capability') -> None:
		"""Append to episodic memory if a memory store is available."""
		if self.memory_store is None:
			return
		try:
			self.memory_store.add_episode(content=content, source=source)
		except Exception:
			pass

	def calendar_today(self, date_str: str = '') -> list[dict[str, Any]]:
		"""Return today's calendar events, or [] when not configured."""
		if self.calendar_store is None:
			return []
		try:
			return self.calendar_store.for_date(date_str) if date_str else []
		except Exception:
			return []


def build_context(services: dict[str, Any], session_id: str = '') -> SkillContext:
	"""
	Construct a SkillContext from the web app's live service dict.

	Args:
		services:   Dict produced by web_app._get_services() — keys include
		            'memory_store', 'calendar_store', 'notification_bus', etc.
		session_id: Optional request/session identifier for episodic logging.
	"""
	return SkillContext(
		memory_store     = services.get('memory_store'),
		session_store    = services.get('session_store'),
		calendar_store   = services.get('calendar_store'),
		notification_bus = services.get('notification_bus'),
		session_id       = session_id,
	)

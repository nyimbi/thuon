# core/obsidian_bridge.py
"""
Obsidian vault integration — read/write .md files to/from a local vault.
All methods are no-ops when vault_path is not configured.
"""

from __future__ import annotations
import re
import threading
import time
from pathlib import Path

from core.settings_manager import get_settings


class ObsidianBridge:
	def __init__(self):
		settings = get_settings()
		vault_raw = settings.get_setting('obsidian.vault_path', '')
		self._vault: Path | None = Path(vault_raw).expanduser() if vault_raw else None
		self._inbox  = settings.get_setting('obsidian.inbox_folder',  'Thuon Inbox')
		self._rfps   = settings.get_setting('obsidian.rfp_folder',    'RFPs')
		self._blog   = settings.get_setting('obsidian.blog_folder',   'Blog Posts')

	@property
	def enabled(self) -> bool:
		return self._vault is not None and self._vault.is_dir()

	# ── Read ─────────────────────────────────────────────────────────────────

	def read_ideas(self) -> list[str]:
		"""Read all .md files from the inbox folder as raw text strings."""
		if not self.enabled:
			return []
		inbox = self._vault / self._inbox
		if not inbox.is_dir():
			return []
		ideas = []
		for f in sorted(inbox.glob('*.md')):
			try:
				text = f.read_text(encoding='utf-8').strip()
				if text:
					ideas.append(text)
			except Exception:
				pass
		return ideas

	def read_folder(self, folder_name: str) -> list[dict]:
		"""Return list of {name, content} dicts for all .md files in a subfolder."""
		if not self.enabled:
			return []
		folder = self._vault / folder_name
		if not folder.is_dir():
			return []
		results = []
		for f in sorted(folder.glob('*.md')):
			try:
				results.append({'name': f.stem, 'content': f.read_text(encoding='utf-8')})
			except Exception:
				pass
		return results

	# ── Write ─────────────────────────────────────────────────────────────────

	def write_rfp(self, title: str, content: str) -> str | None:
		"""Write an RFP response .md to the Obsidian RFPs folder. Returns path or None."""
		return self._write_to_folder(self._rfps, title, content)

	def write_blog(self, title: str, content: str) -> str | None:
		"""Write a blog post .md to the Obsidian blog folder. Returns path or None."""
		return self._write_to_folder(self._blog, title, content)

	def write_note(self, folder: str, title: str, content: str) -> str | None:
		return self._write_to_folder(folder, title, content)

	# ── Internal ─────────────────────────────────────────────────────────────

	def _write_to_folder(self, folder_name: str, title: str, content: str) -> str | None:
		if not self.enabled:
			return None
		safe_folder = re.sub(r'[^\w\- ]', '', folder_name).strip()[:80] or 'Notes'
		folder = (self._vault / safe_folder).resolve()
		if not str(folder).startswith(str(self._vault.resolve())):
			return None
		folder.mkdir(parents=True, exist_ok=True)
		safe = re.sub(r'[^\w\- ]', '', title)[:80].strip()
		ts   = time.strftime('%Y%m%d-%H%M%S')
		path = folder / f'{safe}-{ts}.md'
		path.write_text(content, encoding='utf-8')
		return str(path)


# Module-level singleton
_bridge: ObsidianBridge | None = None
_bridge_lock = threading.Lock()


def get_obsidian_bridge() -> ObsidianBridge:
	global _bridge
	if _bridge is None:
		with _bridge_lock:
			if _bridge is None:
				_bridge = ObsidianBridge()
	return _bridge

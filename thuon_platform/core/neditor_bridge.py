# core/neditor_bridge.py
"""
neditor / `ned` CLI bridge.
Opens .md files in neditor via the IPC queue file (~/.neditor/cli-open-queue.jsonl).
All methods are graceful no-ops when neditor is not installed or unconfigured.
"""

from __future__ import annotations
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from core.settings_manager import get_settings

_DEFAULT_QUEUE = Path.home() / '.neditor' / 'cli-open-queue.jsonl'


class NeditorBridge:
	def __init__(self):
		settings = get_settings()
		queue_raw  = settings.get_setting('neditor.ipc_queue_path', str(_DEFAULT_QUEUE))
		self._queue_path = Path(queue_raw).expanduser()
		self._lock = threading.Lock()

	@property
	def available(self) -> bool:
		return self._ned_on_path() or self._queue_path.parent.is_dir()

	# ── Public API ────────────────────────────────────────────────────────────

	def open(self, file_path: str, metadata: dict | None = None) -> bool:
		"""
		Ask neditor to open a file. First tries IPC queue, then `ned open` subprocess.
		Returns True if the request was dispatched (not that neditor is running).
		"""
		entry = {'action': 'open', 'path': str(file_path), 'ts': time.time()}
		if metadata:
			entry['metadata'] = metadata
		return self._enqueue(entry) or self._ned_cli('open', file_path)

	def convert(self, md_path: str, output_format: str = 'docx') -> str | None:
		"""
		Run `ned convert <file> --format <fmt>`. Returns output path or None.
		"""
		if not self._ned_on_path():
			return None
		out = Path(md_path).with_suffix(f'.{output_format}')
		try:
			result = subprocess.run(
				['ned', 'convert', md_path, '--format', output_format, '--out', str(out)],
				capture_output=True, text=True, timeout=120,
			)
			if result.returncode == 0 and out.exists():
				return str(out)
		except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
			pass
		return None

	# ── Internal ─────────────────────────────────────────────────────────────

	def _enqueue(self, entry: dict) -> bool:
		try:
			self._queue_path.parent.mkdir(parents=True, exist_ok=True)
			with self._lock:
				with open(self._queue_path, 'a') as f:
					f.write(json.dumps(entry) + '\n')
			return True
		except OSError:
			return False

	def _ned_cli(self, *args: str) -> bool:
		if not self._ned_on_path():
			return False
		try:
			subprocess.Popen(['ned', *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return True
		except (FileNotFoundError, OSError):
			return False

	@staticmethod
	def _ned_on_path() -> bool:
		return subprocess.run(
			['which', 'ned'], capture_output=True
		).returncode == 0


# Module-level singleton
_neditor: NeditorBridge | None = None
_neditor_lock = threading.Lock()


def get_neditor_bridge() -> NeditorBridge:
	global _neditor
	if _neditor is None:
		with _neditor_lock:
			if _neditor is None:
				_neditor = NeditorBridge()
	return _neditor

"""
Three-tier persistent memory — inspired by Hermes agent architecture.

Tiers:
  1. USER.md       — user identity, preferences, working style  (semantic, file-backed)
  2. MEMORY.md     — facts about the company and world          (semantic, file-backed)
  3. sessions.db   — episodic event log with FTS5               (SQLite)

Injection: get_context_block(query) returns a formatted block for system-prompt injection.
Background consolidation: consolidate() runs hourly — summarises old episodes into MEMORY.md.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

# ── constants ─────────────────────────────────────────────────────────────────

from core.bundle import writable_data_dir as _wdd
_MEM_DIR   = _wdd() / 'memory'
_USER_FILE = _MEM_DIR / 'USER.md'
_MEM_FILE  = _MEM_DIR / 'MEMORY.md'
_DB_PATH   = _MEM_DIR / 'sessions.db'

_DELIM = '§'   # section separator inside USER.md / MEMORY.md

_USER_TEMPLATE = """# User Profile

Use this file to record what Thuon knows about the person using it.
Each fact on its own line, separated by §.

§ Name: [fill in]
§ Role: [fill in]
§ Company: [fill in]
§ Communication style: [fill in]
§ Working hours: [fill in]
§ Top priorities: [fill in]
"""

_MEM_TEMPLATE = """# Thuon Memory

Persistent facts about the company, market, and ongoing context.
Each entry on its own line, separated by §.

§ Platform: Thuon business automation platform
§ Initialized: {date}
"""


# ── SQLite schema ─────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,        -- 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'summary'
    content     TEXT NOT NULL,
    metadata    TEXT DEFAULT '{}',    -- JSON blob
    created_at  REAL NOT NULL         -- Unix timestamp
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    content,
    content=episodes,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO episodes_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    source      TEXT DEFAULT 'web',   -- 'web' | 'cli' | 'scheduler'
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
"""


# ── MemoryStore ────────────────────────────────────────────────────────────────

class MemoryStore:
	"""Thread-safe, file + SQLite backed memory store."""

	def __init__(self, mem_dir: Path | None = None) -> None:
		self._dir = mem_dir or _MEM_DIR
		self._dir.mkdir(parents=True, exist_ok=True)
		self._user_file = self._dir / 'USER.md'
		self._mem_file  = self._dir / 'MEMORY.md'
		self._db_path   = self._dir / 'sessions.db'
		self._lock = threading.RLock()

		self._ensure_files()
		self._db = self._open_db()

	# ── file-backed tiers ─────────────────────────────────────────────────────

	def read_user(self) -> str:
		return self._user_file.read_text(encoding='utf-8')

	def read_memory(self) -> str:
		return self._mem_file.read_text(encoding='utf-8')

	def add_user_fact(self, fact: str) -> None:
		with self._lock:
			current = self._user_file.read_text(encoding='utf-8')
			self._user_file.write_text(current.rstrip() + f'\n{_DELIM} {fact.strip()}\n', encoding='utf-8')

	def replace_user_fact(self, old: str, new: str) -> bool:
		with self._lock:
			text = self._user_file.read_text(encoding='utf-8')
			if old not in text:
				return False
			self._user_file.write_text(text.replace(old, new, 1), encoding='utf-8')
			return True

	def add_memory_fact(self, fact: str) -> None:
		with self._lock:
			current = self._mem_file.read_text(encoding='utf-8')
			self._mem_file.write_text(current.rstrip() + f'\n{_DELIM} {fact.strip()}\n', encoding='utf-8')

	def replace_memory_fact(self, old: str, new: str) -> bool:
		with self._lock:
			text = self._mem_file.read_text(encoding='utf-8')
			if old not in text:
				return False
			self._mem_file.write_text(text.replace(old, new, 1), encoding='utf-8')
			return True

	def write_user(self, content: str) -> None:
		with self._lock:
			self._user_file.write_text(content, encoding='utf-8')

	def write_memory(self, content: str) -> None:
		with self._lock:
			self._mem_file.write_text(content, encoding='utf-8')

	# ── episodic store ────────────────────────────────────────────────────────

	def log_episode(self, session_id: str, event_type: str, content: str, metadata: dict | None = None) -> int:
		import json
		with self._lock:
			cur = self._db.execute(
				'INSERT INTO episodes (session_id, event_type, content, metadata, created_at) VALUES (?,?,?,?,?)',
				(session_id, event_type, content, json.dumps(metadata or {}), time.time()),
			)
			self._db.commit()
			return cur.lastrowid

	def search_episodes(self, query: str, limit: int = 10) -> list[dict]:
		with self._lock:
			rows = self._db.execute(
				"""
				SELECT e.id, e.session_id, e.event_type, e.content, e.created_at
				FROM episodes_fts f
				JOIN episodes e ON e.id = f.rowid
				WHERE episodes_fts MATCH ?
				ORDER BY rank
				LIMIT ?
				""",
				(query, limit),
			).fetchall()
		return [{'id': r[0], 'session_id': r[1], 'type': r[2], 'content': r[3], 'created_at': r[4]} for r in rows]

	def recent_episodes(self, limit: int = 20, session_id: str | None = None) -> list[dict]:
		with self._lock:
			if session_id:
				rows = self._db.execute(
					'SELECT id, session_id, event_type, content, created_at FROM episodes WHERE session_id=? ORDER BY created_at DESC LIMIT ?',
					(session_id, limit),
				).fetchall()
			else:
				rows = self._db.execute(
					'SELECT id, session_id, event_type, content, created_at FROM episodes ORDER BY created_at DESC LIMIT ?',
					(limit,),
				).fetchall()
		return [{'id': r[0], 'session_id': r[1], 'type': r[2], 'content': r[3], 'created_at': r[4]} for r in rows]

	def ensure_session(self, session_id: str, title: str = '', source: str = 'web') -> None:
		now = time.time()
		with self._lock:
			self._db.execute(
				'INSERT OR IGNORE INTO sessions (id, title, source, created_at, updated_at) VALUES (?,?,?,?,?)',
				(session_id, title, source, now, now),
			)
			self._db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (now, session_id))
			self._db.commit()

	# ── context injection ─────────────────────────────────────────────────────

	def get_context_block(self, query: str = '', top_episodes: int = 5) -> str:
		"""
		Returns a formatted context block for injection into capability prompts.
		Pulls USER.md, MEMORY.md, and top matching episodes.
		"""
		parts: list[str] = []

		user_text = self.read_user().strip()
		if user_text:
			parts.append('## User Profile\n' + user_text)

		mem_text = self.read_memory().strip()
		if mem_text:
			parts.append('## Platform Memory\n' + mem_text)

		if query:
			episodes = self.search_episodes(query, limit=top_episodes)
			if not episodes:
				episodes = self.recent_episodes(limit=top_episodes)
		else:
			episodes = self.recent_episodes(limit=top_episodes)

		if episodes:
			ep_lines = '\n'.join(
				f'[{e["type"]}] {e["content"][:300]}' for e in reversed(episodes)
			)
			parts.append('## Recent Context\n' + ep_lines)

		return '\n\n'.join(parts)

	# ── stats ─────────────────────────────────────────────────────────────────

	def stats(self) -> dict[str, Any]:
		with self._lock:
			episode_count = self._db.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]
			session_count = self._db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
		user_facts    = self.read_user().count(_DELIM)
		mem_facts     = self.read_memory().count(_DELIM)
		return {
			'episodes': episode_count,
			'sessions': session_count,
			'user_facts': user_facts,
			'memory_facts': mem_facts,
		}

	# ── internals ─────────────────────────────────────────────────────────────

	def _ensure_files(self) -> None:
		if not self._user_file.exists():
			self._user_file.write_text(_USER_TEMPLATE, encoding='utf-8')
		if not self._mem_file.exists():
			from datetime import date
			self._mem_file.write_text(
				_MEM_TEMPLATE.format(date=date.today().isoformat()), encoding='utf-8'
			)

	def _open_db(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
		conn.executescript(_DDL)
		conn.commit()
		return conn


# ── singleton ──────────────────────────────────────────────────────────────────

_store: MemoryStore | None = None
_store_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
	global _store
	if _store is None:
		with _store_lock:
			if _store is None:
				_store = MemoryStore()
	return _store

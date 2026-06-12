# core/session_store.py
# Universal weakness #2 — Session continuity.
#
# Every capability invocation is currently stateless. This module stores results
# in PostgreSQL keyed by session_id so capabilities can load prior context,
# enabling iterative workflows and follow-up calls within a session.

import json
import time
import hashlib
from typing import Any

_DDL = """
CREATE TABLE IF NOT EXISTS capability_sessions (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(64)  NOT NULL,
    capability  VARCHAR(128) NOT NULL,
    input_hash  VARCHAR(64),
    input_json  JSONB,
    result_json JSONB,
    created_at  BIGINT       NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cap_sessions_sid ON capability_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_cap_sessions_cap ON capability_sessions(session_id, capability);
"""


class SessionStore:
	"""
	Persist capability results per session. Requires a live DatabaseHandler.
	Falls back silently (no-ops) when the DB is unavailable.
	"""

	def __init__(self, data_handler=None):
		self.db = data_handler
		self._ready = False

	def _ensure(self) -> bool:
		if self._ready:
			return True
		if self.db is None:
			return False
		try:
			for stmt in _DDL.strip().split(';'):
				stmt = stmt.strip()
				if stmt:
					self.db.execute_query(stmt)
			self._ready = True
			return True
		except Exception:
			return False

	# ── Write ────────────────────────────────────────────────────────────

	def save(self, session_id: str, capability: str, params: dict, result: dict) -> bool:
		if not self._ensure():
			return False
		try:
			input_hash = hashlib.sha256(
				json.dumps(params, sort_keys=True).encode()
			).hexdigest()[:16]
			self.db.execute_query(
				"""
				INSERT INTO capability_sessions
				    (session_id, capability, input_hash, input_json, result_json, created_at)
				VALUES (%s, %s, %s, %s, %s, %s)
				""",
				(session_id, capability, input_hash,
				 json.dumps(params), json.dumps(result), int(time.time())),
			)
			return True
		except Exception:
			return False

	# ── Read ─────────────────────────────────────────────────────────────

	def load(self, session_id: str) -> list[dict]:
		"""Return all entries for a session, oldest first."""
		if not self._ensure():
			return []
		try:
			return self.db.execute_query(
				"""
				SELECT capability, input_json, result_json, created_at
				FROM   capability_sessions
				WHERE  session_id = %s
				ORDER  BY created_at ASC
				""",
				(session_id,),
			)
		except Exception:
			return []

	def latest(self, session_id: str, capability: str) -> dict | None:
		"""Return the most recent result for a specific capability in this session."""
		if not self._ensure():
			return None
		try:
			rows = self.db.execute_query(
				"""
				SELECT result_json FROM capability_sessions
				WHERE  session_id = %s AND capability = %s
				ORDER  BY created_at DESC LIMIT 1
				""",
				(session_id, capability),
			)
			return rows[0]['result_json'] if rows else None
		except Exception:
			return None

	def get_context(self, session_id: str, max_entries: int = 5) -> str:
		"""
		Format recent session results as a context block for LLM prompts.
		Returns empty string when session is empty or DB unavailable.
		"""
		rows = self.load(session_id)
		if not rows:
			return ''
		recent = rows[-max_entries:]
		parts = []
		for r in recent:
			result = r.get('result_json') or {}
			summary = (
				result.get('summary')
				or result.get('answer')
				or result.get('abstract')
				or result.get('landscape_summary')
				or str(result)[:400]
			)
			parts.append(f"[{r['capability']}]: {str(summary)[:500]}")
		return 'Prior session context:\n' + '\n'.join(parts)

	def list_sessions(self, capability: str = '', limit: int = 20) -> list[dict]:
		"""List recent sessions, optionally filtered by capability."""
		if not self._ensure():
			return []
		try:
			if capability:
				return self.db.execute_query(
					"""
					SELECT DISTINCT session_id, MAX(created_at) AS last_active
					FROM   capability_sessions
					WHERE  capability = %s
					GROUP  BY session_id
					ORDER  BY last_active DESC LIMIT %s
					""",
					(capability, limit),
				)
			return self.db.execute_query(
				"""
				SELECT DISTINCT session_id, MAX(created_at) AS last_active
				FROM   capability_sessions
				GROUP  BY session_id
				ORDER  BY last_active DESC LIMIT %s
				""",
				(limit,),
			)
		except Exception:
			return []

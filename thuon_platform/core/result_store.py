"""
Result versioning and diffing — store capability results keyed by (capability, key),
retrieve history, diff consecutive versions.
"""
from __future__ import annotations
import json
import hashlib


class ResultStore:
	"""
	Append-only store for capability results with diff support.

	Backed by DatabaseHandler when available; falls back to in-memory list.
	Schema (auto-created):
	  capability_results(id SERIAL, capability TEXT, result_key TEXT,
	                     version INT, content_hash TEXT,
	                     result_json TEXT, created_at TIMESTAMPTZ DEFAULT now())
	"""

	_TABLE = 'capability_results'

	def __init__(self, data_handler=None) -> None:
		self._db = data_handler
		self._mem: list[dict] = []
		self._ensure_table()

	def _ensure_table(self) -> None:
		if not self._db:
			return
		try:
			self._db.execute_query(
				f"""
				CREATE TABLE IF NOT EXISTS {self._TABLE} (
					id          SERIAL PRIMARY KEY,
					capability  TEXT NOT NULL,
					result_key  TEXT NOT NULL,
					version     INT  NOT NULL DEFAULT 1,
					content_hash TEXT NOT NULL,
					result_json TEXT NOT NULL,
					created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
				)
				""",
				(),
			)
		except Exception:
			self._db = None  # fall back silently

	def save(self, capability: str, result_key: str, result: dict) -> int:
		"""
		Persist result. Returns the new version number.
		"""
		content_hash = hashlib.sha256(
			json.dumps(result, sort_keys=True, default=str).encode()
		).hexdigest()[:16]
		history = self.get_history(capability, result_key)
		version = len(history) + 1
		record = {
			'capability':   capability,
			'result_key':   result_key,
			'version':      version,
			'content_hash': content_hash,
			'result_json':  json.dumps(result, default=str),
		}
		if self._db:
			try:
				self._db.insert_data(self._TABLE, record)
				return version
			except Exception:
				pass
		record['result'] = result
		self._mem.append(record)
		return version

	def get_history(self, capability: str, result_key: str) -> list[dict]:
		"""Return all versions, oldest first."""
		if self._db:
			try:
				rows = self._db.execute_query(
					f'SELECT version, content_hash, result_json, created_at '
					f'FROM {self._TABLE} '
					f'WHERE capability=%s AND result_key=%s ORDER BY version ASC',
					(capability, result_key),
				)
				return [
					{
						'version':      r[0],
						'content_hash': r[1],
						'result':       json.loads(r[2]),
						'created_at':   str(r[3]),
					}
					for r in (rows or [])
				]
			except Exception:
				pass
		return [
			r for r in self._mem
			if r['capability'] == capability and r['result_key'] == result_key
		]

	def latest(self, capability: str, result_key: str) -> dict | None:
		history = self.get_history(capability, result_key)
		return history[-1] if history else None

	def diff(self, capability: str, result_key: str, v1: int, v2: int) -> dict:
		"""
		Produce a shallow key-level diff between two versions.
		Returns {added, removed, changed} keyed by field name.
		"""
		history = self.get_history(capability, result_key)
		by_version = {h['version']: h['result'] for h in history}
		r1 = by_version.get(v1, {})
		r2 = by_version.get(v2, {})

		keys1, keys2 = set(r1), set(r2)
		added   = {k: r2[k] for k in keys2 - keys1}
		removed = {k: r1[k] for k in keys1 - keys2}
		changed = {
			k: {'from': r1[k], 'to': r2[k]}
			for k in keys1 & keys2
			if r1[k] != r2[k]
		}
		return {'added': added, 'removed': removed, 'changed': changed}

	def diff_latest_two(self, capability: str, result_key: str) -> dict:
		history = self.get_history(capability, result_key)
		if len(history) < 2:
			return {'added': {}, 'removed': {}, 'changed': {}, 'note': 'fewer than 2 versions'}
		v1 = history[-2]['version']
		v2 = history[-1]['version']
		return self.diff(capability, result_key, v1, v2)

# core/pipeline_checkpoint_store.py
"""
Persist pipeline execution state after each step so failed/interrupted
pipelines can resume from the last successful step.

Schema:
  runs        — one row per pipeline execution
  step_results — one row per completed step within a run

Thread-safe via a single threading.Lock per store instance.
WAL mode enabled for concurrent readers.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd

_DB_PATH: Path = _wdd() / 'pipeline_checkpoints.db'

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
	id            TEXT PRIMARY KEY,
	pipeline_name TEXT NOT NULL,
	inputs        TEXT NOT NULL,          -- JSON
	status        TEXT NOT NULL DEFAULT 'running'
	                  CHECK(status IN ('running','completed','failed','paused')),
	current_step  TEXT,
	started_at    REAL NOT NULL,
	updated_at    REAL NOT NULL,
	error         TEXT
);

CREATE TABLE IF NOT EXISTS step_results (
	id           TEXT PRIMARY KEY,
	run_id       TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
	step_name    TEXT NOT NULL,
	cap_name     TEXT NOT NULL,
	result       TEXT NOT NULL,           -- JSON
	elapsed      REAL NOT NULL,
	completed_at REAL NOT NULL,
	UNIQUE(run_id, step_name)
);

CREATE INDEX IF NOT EXISTS runs_pipeline ON runs(pipeline_name);
CREATE INDEX IF NOT EXISTS runs_status   ON runs(status);
CREATE INDEX IF NOT EXISTS sr_run_id     ON step_results(run_id);
"""


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
	return {col[0]: row[col[0]] for col in cursor.description}


class PipelineCheckpointStore:
	"""SQLite-backed checkpoint store for pipeline executions."""

	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db   = self._open()

	# ── internal ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn

	def _now(self) -> float:
		return time.time()

	def _new_id(self) -> str:
		return str(uuid.uuid4())

	def _dumps(self, obj: Any) -> str:
		return json.dumps(obj, default=str)

	def _loads(self, s: str | None) -> Any:
		if s is None:
			return None
		try:
			return json.loads(s)
		except (TypeError, json.JSONDecodeError):
			return s

	def _row_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
		if row is None:
			return None
		return dict(row)

	# ── public API ────────────────────────────────────────────────────────────

	def start_run(self, pipeline_name: str, inputs: dict) -> str:
		"""Create a new run record and return its run_id."""
		run_id = self._new_id()
		now    = self._now()
		with self._lock:
			self._db.execute(
				"""INSERT INTO runs
				   (id, pipeline_name, inputs, status, current_step, started_at, updated_at)
				   VALUES (?, ?, ?, 'running', NULL, ?, ?)""",
				(run_id, pipeline_name, self._dumps(inputs), now, now),
			)
			self._db.commit()
		return run_id

	def save_step(
		self,
		run_id: str,
		step_name: str,
		cap_name: str,
		result: dict,
		elapsed: float,
	) -> None:
		"""Persist a completed step result and advance current_step on the run."""
		step_id = self._new_id()
		now     = self._now()
		with self._lock:
			self._db.execute(
				"""INSERT INTO step_results
				   (id, run_id, step_name, cap_name, result, elapsed, completed_at)
				   VALUES (?, ?, ?, ?, ?, ?, ?)
				   ON CONFLICT(run_id, step_name) DO UPDATE SET
				     cap_name=excluded.cap_name,
				     result=excluded.result,
				     elapsed=excluded.elapsed,
				     completed_at=excluded.completed_at""",
				(step_id, run_id, step_name, cap_name, self._dumps(result), elapsed, now),
			)
			self._db.execute(
				"UPDATE runs SET current_step=?, updated_at=? WHERE id=?",
				(step_name, now, run_id),
			)
			self._db.commit()

	def mark_failed(self, run_id: str, step_name: str, error: str) -> None:
		"""Mark a run as failed, recording which step failed and the error."""
		now = self._now()
		with self._lock:
			self._db.execute(
				"""UPDATE runs
				   SET status='failed', current_step=?, error=?, updated_at=?
				   WHERE id=?""",
				(step_name, error, now, run_id),
			)
			self._db.commit()

	def mark_completed(self, run_id: str) -> None:
		"""Mark a run as successfully completed."""
		now = self._now()
		with self._lock:
			self._db.execute(
				"UPDATE runs SET status='completed', updated_at=? WHERE id=?",
				(now, run_id),
			)
			self._db.commit()

	def mark_paused(self, run_id: str, at_step: str) -> None:
		"""Pause a run at the given step (e.g. awaiting human input)."""
		now = self._now()
		with self._lock:
			self._db.execute(
				"""UPDATE runs
				   SET status='paused', current_step=?, updated_at=?
				   WHERE id=?""",
				(at_step, now, run_id),
			)
			self._db.commit()

	def resume_run(self, run_id: str) -> dict | None:
		"""
		Return the information needed to resume a run from the last checkpoint.

		Returns:
		  {
		    'run': dict,                          # the runs row (inputs deserialized)
		    'completed_steps': {step_name: result},
		    'resume_from_step': str | None,       # first step NOT yet completed
		  }
		  or None if run_id does not exist.
		"""
		run = self.get_run(run_id)
		if run is None:
			return None

		completed = self.get_step_results(run_id)

		# Re-mark as running so callers can use the same state transitions
		now = self._now()
		with self._lock:
			self._db.execute(
				"UPDATE runs SET status='running', error=NULL, updated_at=? WHERE id=?",
				(now, run_id),
			)
			self._db.commit()

		# resume_from_step: whatever current_step was (the step that failed /
		# was paused at).  If no current_step recorded, start from scratch.
		resume_from = run.get('current_step')

		return {
			'run': run,
			'completed_steps': completed,
			'resume_from_step': resume_from,
		}

	def get_run(self, run_id: str) -> dict[str, Any] | None:
		"""Fetch a single run row; inputs deserialized from JSON."""
		row = self._db.execute(
			"SELECT * FROM runs WHERE id=?", (run_id,)
		).fetchone()
		if row is None:
			return None
		d = dict(row)
		d['inputs'] = self._loads(d.get('inputs'))
		return d

	def list_runs(
		self,
		pipeline_name: str | None = None,
		status: str | None = None,
		limit: int = 20,
	) -> list[dict[str, Any]]:
		"""
		Return recent runs, optionally filtered by pipeline_name and/or status.
		Ordered newest first.
		"""
		clauses: list[str] = []
		params:  list[Any] = []

		if pipeline_name is not None:
			clauses.append("pipeline_name=?")
			params.append(pipeline_name)
		if status is not None:
			clauses.append("status=?")
			params.append(status)

		where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
		params.append(limit)

		rows = self._db.execute(
			f"SELECT * FROM runs {where} ORDER BY started_at DESC LIMIT ?",
			params,
		).fetchall()

		result = []
		for row in rows:
			d = dict(row)
			d['inputs'] = self._loads(d.get('inputs'))
			result.append(d)
		return result

	def get_step_results(self, run_id: str) -> dict[str, dict]:
		"""
		Return all completed step results for a run as {step_name: result_dict}.
		result values are deserialized from JSON.
		"""
		rows = self._db.execute(
			"SELECT * FROM step_results WHERE run_id=? ORDER BY completed_at ASC",
			(run_id,),
		).fetchall()
		out: dict[str, dict] = {}
		for row in rows:
			d = dict(row)
			d['result'] = self._loads(d.get('result'))
			out[d['step_name']] = d
		return out

	def cleanup_old_runs(self, days: int = 7) -> int:
		"""
		Delete completed/failed runs (and their step_results via CASCADE)
		older than `days` days.  Returns the number of runs deleted.
		"""
		cutoff = self._now() - days * 86400.0
		with self._lock:
			cur = self._db.execute(
				"""DELETE FROM runs
				   WHERE status IN ('completed','failed')
				   AND updated_at < ?""",
				(cutoff,),
			)
			self._db.commit()
		return cur.rowcount


# ── module-level singleton ────────────────────────────────────────────────────

_store: PipelineCheckpointStore | None = None
_store_lock = threading.Lock()


def get_checkpoint_store() -> PipelineCheckpointStore:
	"""Return the process-wide PipelineCheckpointStore singleton."""
	global _store
	if _store is None:
		with _store_lock:
			if _store is None:
				_store = PipelineCheckpointStore()
	return _store

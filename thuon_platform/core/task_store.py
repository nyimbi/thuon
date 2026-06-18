"""
Persistent task / todo list — survives restarts, supports Kanban views.

Schema mirrors Hermes' TodoStore with extensions:
  - due_date, priority, project, tags for business context
  - parent_id for subtasks
  - Persisted to SQLite (not just in-memory)
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd
_DB_PATH = _wdd() / 'tasks.db'

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    notes       TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|in_progress|completed|cancelled
    priority    INTEGER DEFAULT 2,                -- 1=high 2=medium 3=low
    due_date    TEXT,                             -- ISO date YYYY-MM-DD or NULL
    project     TEXT DEFAULT '',
    tags        TEXT DEFAULT '',                  -- comma-separated
    parent_id   TEXT REFERENCES tasks(id),
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    completed_at REAL
);

CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS tasks_due    ON tasks(due_date);
CREATE INDEX IF NOT EXISTS tasks_proj   ON tasks(project);
"""

_VALID_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}


class TaskStore:
	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db   = self._open()

	# ── CRUD ──────────────────────────────────────────────────────────────────

	def create(
		self,
		title: str,
		notes: str = '',
		priority: int = 2,
		due_date: str | None = None,
		project: str = '',
		tags: str = '',
		parent_id: str | None = None,
		status: str = 'pending',
	) -> dict[str, Any]:
		import uuid
		task_id = str(uuid.uuid4())
		now = time.time()
		with self._lock:
			self._db.execute(
				"""INSERT INTO tasks
				   (id, title, notes, status, priority, due_date, project, tags, parent_id, created_at, updated_at)
				   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
				(task_id, title, notes, status, priority, due_date, project, tags, parent_id, now, now),
			)
			self._db.commit()
		return self.get(task_id)

	def get(self, task_id: str) -> dict[str, Any] | None:
		row = self._db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
		return self._row(row) if row else None

	def update(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
		allowed = {'title', 'notes', 'status', 'priority', 'due_date', 'project', 'tags', 'parent_id'}
		updates = {k: v for k, v in fields.items() if k in allowed}
		if not updates:
			return self.get(task_id)
		if 'status' in updates and updates['status'] not in _VALID_STATUSES:
			raise ValueError(f'Invalid status: {updates["status"]}')
		updates['updated_at'] = time.time()
		if updates.get('status') == 'completed':
			updates['completed_at'] = time.time()
		cols = ', '.join(f'{k}=?' for k in updates)
		vals = list(updates.values()) + [task_id]
		with self._lock:
			self._db.execute(f'UPDATE tasks SET {cols} WHERE id=?', vals)
			self._db.commit()
		return self.get(task_id)

	def delete(self, task_id: str) -> bool:
		with self._lock:
			cur = self._db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
			self._db.commit()
		return cur.rowcount > 0

	# ── queries ───────────────────────────────────────────────────────────────

	def all(
		self,
		status: str | None = None,
		project: str | None = None,
		include_completed: bool = False,
	) -> list[dict[str, Any]]:
		clauses: list[str] = []
		params:  list[Any] = []
		if status:
			clauses.append('status=?'); params.append(status)
		elif not include_completed:
			clauses.append("status NOT IN ('completed','cancelled')")
		if project:
			clauses.append('project=?'); params.append(project)
		where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
		rows = self._db.execute(
			f'SELECT * FROM tasks {where} ORDER BY priority ASC, due_date ASC NULLS LAST, created_at ASC',
			params,
		).fetchall()
		return [self._row(r) for r in rows]

	def overdue(self) -> list[dict[str, Any]]:
		from datetime import date
		today = date.today().isoformat()
		rows = self._db.execute(
			"SELECT * FROM tasks WHERE status IN ('pending','in_progress') AND due_date < ? ORDER BY due_date ASC",
			(today,),
		).fetchall()
		return [self._row(r) for r in rows]

	def due_today(self) -> list[dict[str, Any]]:
		from datetime import date
		today = date.today().isoformat()
		rows = self._db.execute(
			"SELECT * FROM tasks WHERE status IN ('pending','in_progress') AND due_date = ?",
			(today,),
		).fetchall()
		return [self._row(r) for r in rows]

	def due_soon(self, days: int = 7) -> list[dict[str, Any]]:
		from datetime import date, timedelta
		today = date.today().isoformat()
		cutoff = (date.today() + timedelta(days=days)).isoformat()
		rows = self._db.execute(
			"SELECT * FROM tasks WHERE status IN ('pending','in_progress') AND due_date BETWEEN ? AND ? ORDER BY due_date ASC",
			(today, cutoff),
		).fetchall()
		return [self._row(r) for r in rows]

	def by_status(self) -> dict[str, list[dict[str, Any]]]:
		result: dict[str, list] = {s: [] for s in _VALID_STATUSES}
		for t in self.all(include_completed=True):
			result.setdefault(t['status'], []).append(t)
		return result

	def projects(self) -> list[str]:
		rows = self._db.execute(
			"SELECT DISTINCT project FROM tasks WHERE project != '' ORDER BY project"
		).fetchall()
		return [r[0] for r in rows]

	def stats(self) -> dict[str, int]:
		rows = self._db.execute(
			"SELECT status, COUNT(*) FROM tasks GROUP BY status"
		).fetchall()
		counts = {r[0]: r[1] for r in rows}
		return {
			'total': sum(counts.values()),
			'pending': counts.get('pending', 0),
			'in_progress': counts.get('in_progress', 0),
			'completed': counts.get('completed', 0),
			'cancelled': counts.get('cancelled', 0),
			'overdue': len(self.overdue()),
		}

	# ── internals ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn

	@staticmethod
	def _row(row: sqlite3.Row) -> dict[str, Any]:
		return dict(row)


_store: TaskStore | None = None
_lock = threading.Lock()


def get_task_store() -> TaskStore:
	global _store
	if _store is None:
		with _lock:
			if _store is None:
				_store = TaskStore()
	return _store

"""
Calendar / important dates store.

Maintains business-critical dates: RFP deadlines, contract PoP end dates,
certification expirations, scheduled meetings, recurring reviews, milestones.

Events are typed so the UI can color-code and the scheduler can fire the right alerts.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd
_DB_PATH = _wdd() / 'calendar.db'

# Event types with display metadata
EVENT_TYPES: dict[str, dict[str, str]] = {
	'rfp_deadline':      {'label': 'RFP Deadline',       'color': '#f87171', 'icon': '⚑'},
	'contract_start':    {'label': 'Contract Start',      'color': '#34d399', 'icon': '▶'},
	'contract_end':      {'label': 'Contract End',        'color': '#fb923c', 'icon': '⏹'},
	'certification_exp': {'label': 'Certification Exp.',  'color': '#fbbf24', 'icon': '🏅'},
	'meeting':           {'label': 'Meeting',             'color': '#60a5fa', 'icon': '📅'},
	'review':            {'label': 'Review / Gate',       'color': '#a78bfa', 'icon': '🔍'},
	'milestone':         {'label': 'Milestone',           'color': '#3ecfcf', 'icon': '🎯'},
	'reminder':          {'label': 'Reminder',            'color': '#94a3b8', 'icon': '🔔'},
	'other':             {'label': 'Other',               'color': '#475569', 'icon': '📌'},
}

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    event_type   TEXT NOT NULL DEFAULT 'other',
    date         TEXT NOT NULL,              -- ISO YYYY-MM-DD
    time         TEXT,                       -- HH:MM or NULL
    end_date     TEXT,                       -- for multi-day events
    recurrence   TEXT,                       -- NULL | 'daily' | 'weekly' | 'monthly' | 'yearly'
    notes        TEXT DEFAULT '',
    ref_id       TEXT,                       -- link to rfp.id / contract.id / etc.
    ref_type     TEXT,                       -- 'rfp' | 'contract' | 'certification' | NULL
    alert_days   TEXT DEFAULT '7,1',         -- comma-sep days-before to alert
    alerted      TEXT DEFAULT '',            -- which alert_days have fired (comma-sep)
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS events_date ON events(date);
CREATE INDEX IF NOT EXISTS events_type ON events(event_type);
"""


class CalendarStore:
	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db   = self._open()

	# ── CRUD ──────────────────────────────────────────────────────────────────

	def create(
		self,
		title: str,
		date: str,
		event_type: str = 'other',
		time: str | None = None,
		end_date: str | None = None,
		recurrence: str | None = None,
		notes: str = '',
		ref_id: str | None = None,
		ref_type: str | None = None,
		alert_days: str = '7,1',
	) -> dict[str, Any]:
		import uuid
		eid  = str(uuid.uuid4())
		now  = _now()
		if event_type not in EVENT_TYPES:
			event_type = 'other'
		with self._lock:
			self._db.execute(
				"""INSERT INTO events
				   (id,title,event_type,date,time,end_date,recurrence,notes,ref_id,ref_type,alert_days,created_at,updated_at)
				   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
				(eid, title, event_type, date, time, end_date, recurrence, notes, ref_id, ref_type, alert_days, now, now),
			)
			self._db.commit()
		return self.get(eid)

	def get(self, event_id: str) -> dict[str, Any] | None:
		row = self._db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
		return self._row(row) if row else None

	def update(self, event_id: str, **fields: Any) -> dict[str, Any] | None:
		allowed = {'title', 'event_type', 'date', 'time', 'end_date', 'recurrence', 'notes',
		           'ref_id', 'ref_type', 'alert_days', 'alerted'}
		updates = {k: v for k, v in fields.items() if k in allowed}
		if not updates:
			return self.get(event_id)
		updates['updated_at'] = _now()
		cols = ', '.join(f'{k}=?' for k in updates)
		with self._lock:
			self._db.execute(f'UPDATE events SET {cols} WHERE id=?', [*updates.values(), event_id])
			self._db.commit()
		return self.get(event_id)

	def delete(self, event_id: str) -> bool:
		with self._lock:
			cur = self._db.execute('DELETE FROM events WHERE id=?', (event_id,))
			self._db.commit()
		return cur.rowcount > 0

	# ── queries ───────────────────────────────────────────────────────────────

	def upcoming(self, days: int = 30, event_type: str | None = None) -> list[dict[str, Any]]:
		from datetime import date, timedelta
		today  = date.today().isoformat()
		cutoff = (date.today() + timedelta(days=days)).isoformat()
		if event_type:
			rows = self._db.execute(
				'SELECT * FROM events WHERE date BETWEEN ? AND ? AND event_type=? ORDER BY date ASC',
				(today, cutoff, event_type),
			).fetchall()
		else:
			rows = self._db.execute(
				'SELECT * FROM events WHERE date BETWEEN ? AND ? ORDER BY date ASC',
				(today, cutoff),
			).fetchall()
		return [self._row(r) for r in rows]

	def for_month(self, year: int, month: int) -> list[dict[str, Any]]:
		prefix = f'{year:04d}-{month:02d}'
		rows = self._db.execute(
			"SELECT * FROM events WHERE date LIKE ? ORDER BY date ASC, time ASC",
			(f'{prefix}%',),
		).fetchall()
		return [self._row(r) for r in rows]

	def for_date(self, date_str: str) -> list[dict[str, Any]]:
		rows = self._db.execute(
			'SELECT * FROM events WHERE date=? ORDER BY time ASC',
			(date_str,),
		).fetchall()
		return [self._row(r) for r in rows]

	def due_alerts(self) -> list[dict[str, Any]]:
		"""Return events whose alert_days threshold has been crossed but not yet fired."""
		from datetime import date, timedelta
		today = date.today()
		upcoming = self._db.execute(
			"SELECT * FROM events WHERE date >= ? ORDER BY date ASC",
			(today.isoformat(),),
		).fetchall()
		alerts: list[dict] = []
		for row in upcoming:
			ev = self._row(row)
			days_until = (date.fromisoformat(ev['date']) - today).days
			thresholds = [int(d) for d in (ev['alert_days'] or '').split(',') if d.strip().isdigit()]
			alerted    = [int(d) for d in (ev['alerted'] or '').split(',') if d.strip().isdigit()]
			for threshold in thresholds:
				if days_until <= threshold and threshold not in alerted:
					alerts.append({**ev, '_days_until': days_until, '_threshold': threshold})
		return alerts

	def mark_alerted(self, event_id: str, threshold: int) -> None:
		ev = self.get(event_id)
		if not ev:
			return
		alerted = [int(d) for d in (ev['alerted'] or '').split(',') if d.strip().isdigit()]
		alerted.append(threshold)
		self.update(event_id, alerted=','.join(str(d) for d in sorted(set(alerted))))

	def all(self, include_past: bool = False) -> list[dict[str, Any]]:
		from datetime import date
		if include_past:
			rows = self._db.execute('SELECT * FROM events ORDER BY date ASC').fetchall()
		else:
			rows = self._db.execute(
				'SELECT * FROM events WHERE date >= ? ORDER BY date ASC',
				(date.today().isoformat(),),
			).fetchall()
		return [self._row(r) for r in rows]

	def sync_rfp_deadlines(self) -> int:
		"""Pull deadlines from RFPTracker and upsert into calendar. Returns number added."""
		try:
			from core.rfp_tracker import get_rfp_tracker
		except ImportError:
			return 0

		tracker = get_rfp_tracker()
		added = 0
		for rfp in tracker.all():
			if not rfp.deadline:
				continue
			existing = self._db.execute(
				"SELECT id FROM events WHERE ref_id=? AND ref_type='rfp' AND event_type='rfp_deadline'",
				(rfp.id,),
			).fetchone()
			if not existing:
				self.create(
					title=f'RFP Deadline: {rfp.title}',
					date=rfp.deadline[:10],
					event_type='rfp_deadline',
					ref_id=rfp.id,
					ref_type='rfp',
					notes=f'Issuer: {rfp.issuer}',
					alert_days='30,14,7,3,1',
				)
				added += 1
		return added

	# ── internals ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn

	@staticmethod
	def _row(row: sqlite3.Row) -> dict[str, Any]:
		d = dict(row)
		d['_type_meta'] = EVENT_TYPES.get(d.get('event_type', 'other'), EVENT_TYPES['other'])
		return d


def _now() -> float:
	return time.time()


_store: CalendarStore | None = None
_cstore_lock = threading.Lock()


def get_calendar_store() -> CalendarStore:
	global _store
	if _store is None:
		with _cstore_lock:
			if _store is None:
				_store = CalendarStore()
	return _store

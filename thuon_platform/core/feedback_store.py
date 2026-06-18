# core/feedback_store.py
"""
FeedbackStore — SQLite-backed win/loss outcome recorder for RFP bids.

Records bid outcomes so proposal_win_probability can derive historical
win rates, surface similar past bids, and identify the win themes that
correlate most strongly with wins.

Thread-safe via threading.RLock.  WAL mode enabled.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir

_DB_PATH: Path = writable_data_dir() / 'feedback_store.db'

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS rfp_outcomes (
    id              TEXT PRIMARY KEY,
    rfp_id          TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    issuer          TEXT NOT NULL DEFAULT '',
    naics           TEXT NOT NULL DEFAULT '',
    budget_est      REAL,
    bid_score       REAL,
    win_themes      TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    section_quality TEXT NOT NULL DEFAULT '{}',   -- JSON {section: score}
    outcome         TEXT NOT NULL
                    CHECK(outcome IN ('won','lost','no_bid')),
    notes           TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fbo_naics   ON rfp_outcomes (naics);
CREATE INDEX IF NOT EXISTS idx_fbo_issuer  ON rfp_outcomes (issuer);
CREATE INDEX IF NOT EXISTS idx_fbo_outcome ON rfp_outcomes (outcome);
"""


def _new_id() -> str:
	import uuid
	return str(uuid.uuid4())


class FeedbackStore:
	"""SQLite-backed bid outcome store."""

	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.RLock()
		self._conn = self._open()

	# ── internal ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn

	def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
		with self._lock:
			cur = self._conn.execute(sql, params)
			self._conn.commit()
			return cur

	def _rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
		with self._lock:
			rows = self._conn.execute(sql, params).fetchall()
		return [dict(r) for r in rows]

	def _row(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
		with self._lock:
			row = self._conn.execute(sql, params).fetchone()
		return dict(row) if row else None

	# ── public API ────────────────────────────────────────────────────────────

	def record_outcome(
		self,
		rfp_id: str,
		title: str = '',
		issuer: str = '',
		naics: str = '',
		budget_est: float = 0.0,
		bid_score: float = 0.0,
		win_themes: list[str] | None = None,
		section_quality: dict | None = None,
		outcome: str = 'lost',
		notes: str = '',
	) -> str:
		"""
		Record the outcome of an RFP bid. Returns the new row id.

		outcome must be 'won', 'lost', or 'no_bid'.
		"""
		if outcome not in ('won', 'lost', 'no_bid'):
			raise ValueError(f'outcome must be won/lost/no_bid, got {outcome!r}')
		row_id = _new_id()
		self._exec(
			"""INSERT INTO rfp_outcomes
			   (id, rfp_id, title, issuer, naics, budget_est, bid_score,
			    win_themes, section_quality, outcome, notes, created_at)
			   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
			(
				row_id, rfp_id, title, issuer, naics,
				float(budget_est), float(bid_score),
				json.dumps(win_themes or []),
				json.dumps(section_quality or {}),
				outcome, notes, time.time(),
			),
		)
		return row_id

	def win_rate(
		self,
		naics: str = '',
		issuer: str = '',
	) -> dict[str, Any] | None:
		"""
		Compute win rate over decided bids (won + lost; no_bid excluded).

		Returns {win_pct: float 0-100, sample_size: int} or None when no data.
		"""
		clauses: list[str] = ["outcome IN ('won','lost')"]
		params: list[Any] = []
		if naics:
			clauses.append('naics = ?')
			params.append(naics)
		if issuer:
			clauses.append("issuer LIKE ?")
			params.append(f'%{issuer}%')
		where = 'WHERE ' + ' AND '.join(clauses)

		row = self._row(
			f"""SELECT
			      COUNT(*) AS total,
			      SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END) AS wins
			    FROM rfp_outcomes {where}""",
			tuple(params),
		)
		if not row or not row.get('total'):
			return None
		total = int(row['total'])
		wins  = int(row['wins'] or 0)
		return {
			'win_pct':     round(wins / total * 100, 1),
			'sample_size': total,
		}

	def similar_outcomes(
		self,
		naics: str = '',
		budget_range: tuple[float, float] | None = None,
		issuer: str = '',
		limit: int = 10,
	) -> list[dict[str, Any]]:
		"""
		Return bids similar by NAICS, issuer, and/or budget range.

		Results are sorted closest-budget-first when a budget_range is given.
		"""
		clauses: list[str] = []
		params: list[Any] = []

		if naics:
			clauses.append('naics = ?')
			params.append(naics)
		if issuer:
			clauses.append("issuer LIKE ?")
			params.append(f'%{issuer}%')

		order = 'ORDER BY created_at DESC'
		if budget_range and budget_range != (0.0, 0.0):
			lo, hi = budget_range
			midpoint = (lo + hi) / 2
			clauses.append('(budget_est IS NULL OR (budget_est >= ? AND budget_est <= ?))')
			params += [lo, hi]
			order = f'ORDER BY ABS(COALESCE(budget_est, {midpoint}) - {midpoint}) ASC'

		where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
		rows = self._rows(
			f'SELECT * FROM rfp_outcomes {where} {order} LIMIT ?',
			tuple(params) + (limit,),
		)
		for r in rows:
			try:
				r['win_themes'] = json.loads(r.get('win_themes') or '[]')
			except (TypeError, json.JSONDecodeError):
				r['win_themes'] = []
		return rows

	def best_win_themes(
		self,
		naics: str = '',
		min_win_rate: float = 0.5,
		limit: int = 10,
	) -> list[str]:
		"""
		Return win themes that appear most frequently in *won* bids for the
		given NAICS code.  no_bid rows are excluded entirely.

		Returns a list of theme strings, most-frequent first.
		"""
		clauses: list[str] = ["outcome IN ('won','lost')"]
		params: list[Any] = []
		if naics:
			clauses.append('naics = ?')
			params.append(naics)
		where = 'WHERE ' + ' AND '.join(clauses)

		rows = self._rows(
			f"SELECT win_themes, outcome FROM rfp_outcomes {where}",
			tuple(params),
		)

		theme_wins:  dict[str, int] = {}
		theme_total: dict[str, int] = {}
		for row in rows:
			try:
				themes = json.loads(row.get('win_themes') or '[]')
			except (TypeError, json.JSONDecodeError):
				continue
			won = row['outcome'] == 'won'
			for theme in themes:
				theme = str(theme).strip()
				if not theme:
					continue
				theme_total[theme] = theme_total.get(theme, 0) + 1
				if won:
					theme_wins[theme] = theme_wins.get(theme, 0) + 1

		# Filter by minimum win rate among themes that appear in decided bids
		qualified = [
			(t, theme_wins.get(t, 0) / theme_total[t])
			for t in theme_total
			if theme_wins.get(t, 0) / theme_total[t] >= min_win_rate
		]
		qualified.sort(key=lambda x: (-x[1], -theme_wins.get(x[0], 0)))
		return [t for t, _ in qualified[:limit]]

	def get_similar_bids(
		self,
		naics: str = '',
		issuer: str = '',
		limit: int = 5,
	) -> list[dict[str, Any]]:
		"""Convenience wrapper used by proposal_win_probability."""
		return self.similar_outcomes(naics=naics, issuer=issuer, limit=limit)


# ── singleton ─────────────────────────────────────────────────────────────────

_store: FeedbackStore | None = None
_store_lock = threading.Lock()


def get_feedback_store() -> FeedbackStore:
	global _store
	if _store is None:
		with _store_lock:
			if _store is None:
				_store = FeedbackStore()
	return _store

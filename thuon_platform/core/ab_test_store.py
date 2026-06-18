# core/ab_test_store.py
"""
Persist A/B test experiments for capability prompt variants.
Track wins and auto-promote winning variants.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd

_DB_PATH = _wdd() / 'ab_tests.db'

_DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS experiments (
	id                 TEXT PRIMARY KEY,
	capability_name    TEXT NOT NULL,
	variant_a_desc     TEXT NOT NULL,
	variant_b_desc     TEXT NOT NULL,
	status             TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','promoted')),
	winner             TEXT NOT NULL DEFAULT '' CHECK(winner IN ('a','b','tie','')),
	promotions_needed  INTEGER NOT NULL DEFAULT 5,
	created_at         REAL NOT NULL,
	completed_at       REAL
);

CREATE INDEX IF NOT EXISTS experiments_capability ON experiments(capability_name);
CREATE INDEX IF NOT EXISTS experiments_status     ON experiments(status);

CREATE TABLE IF NOT EXISTS trials (
	id             TEXT PRIMARY KEY,
	experiment_id  TEXT NOT NULL REFERENCES experiments(id),
	variant        TEXT NOT NULL CHECK(variant IN ('a','b')),
	input_hash     TEXT NOT NULL,
	score          REAL NOT NULL,
	judge_notes    TEXT NOT NULL DEFAULT '',
	created_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS trials_experiment ON trials(experiment_id);
CREATE INDEX IF NOT EXISTS trials_variant    ON trials(experiment_id, variant);
"""


class ABTestStore:
	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db   = self._open()

	# ── experiment management ──────────────────────────────────────────────────

	def create_experiment(
		self,
		capability_name: str,
		variant_a_desc: str,
		variant_b_desc: str,
		promotions_needed: int = 5,
	) -> str:
		"""Create a new active experiment; returns the new experiment id."""
		import uuid
		exp_id = str(uuid.uuid4())
		now = time.time()
		with self._lock:
			self._db.execute(
				"""INSERT INTO experiments
				   (id, capability_name, variant_a_desc, variant_b_desc,
				    status, winner, promotions_needed, created_at)
				   VALUES (?,?,?,?,?,?,?,?)""",
				(exp_id, capability_name, variant_a_desc, variant_b_desc,
				 'active', '', promotions_needed, now),
			)
			self._db.commit()
		return exp_id

	def get_active_experiment(self, capability_name: str) -> dict[str, Any] | None:
		"""Return the most-recently-created active experiment for a capability, or None."""
		row = self._db.execute(
			"""SELECT * FROM experiments
			   WHERE capability_name=? AND status='active'
			   ORDER BY created_at DESC LIMIT 1""",
			(capability_name,),
		).fetchone()
		return dict(row) if row else None

	def list_experiments(
		self,
		capability_name: str | None = None,
		status: str | None = None,
	) -> list[dict[str, Any]]:
		"""List experiments, optionally filtered by capability_name and/or status."""
		clauses: list[str] = []
		params:  list[Any] = []
		if capability_name is not None:
			clauses.append('capability_name=?')
			params.append(capability_name)
		if status is not None:
			clauses.append('status=?')
			params.append(status)
		where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
		rows = self._db.execute(
			f'SELECT * FROM experiments {where} ORDER BY created_at DESC',
			params,
		).fetchall()
		return [dict(r) for r in rows]

	def get_winning_variant(self, capability_name: str) -> str | None:
		"""Return description of the promoted winner for a capability, or None."""
		row = self._db.execute(
			"""SELECT winner, variant_a_desc, variant_b_desc FROM experiments
			   WHERE capability_name=? AND status='promoted'
			   ORDER BY completed_at DESC LIMIT 1""",
			(capability_name,),
		).fetchone()
		if row is None:
			return None
		winner = row['winner']
		if winner == 'a':
			return row['variant_a_desc']
		if winner == 'b':
			return row['variant_b_desc']
		# tie — return None; caller decides
		return None

	# ── trial recording ────────────────────────────────────────────────────────

	def record_trial(
		self,
		experiment_id: str,
		variant: str,
		input_text: str,
		score: float,
		judge_notes: str = '',
	) -> str:
		"""Record one trial result; returns the new trial id."""
		if variant not in ('a', 'b'):
			raise ValueError(f'variant must be "a" or "b", got {variant!r}')

		# Verify experiment exists and is active
		exp = self._db.execute(
			'SELECT id, status FROM experiments WHERE id=?', (experiment_id,)
		).fetchone()
		if exp is None:
			raise KeyError(f'Experiment {experiment_id!r} not found')
		if exp['status'] != 'active':
			raise ValueError(
				f'Experiment {experiment_id!r} is not active (status={exp["status"]!r})'
			)

		import uuid
		trial_id   = str(uuid.uuid4())
		input_hash = hashlib.sha256(input_text.encode()).hexdigest()
		now        = time.time()

		with self._lock:
			self._db.execute(
				"""INSERT INTO trials
				   (id, experiment_id, variant, input_hash, score, judge_notes, created_at)
				   VALUES (?,?,?,?,?,?,?)""",
				(trial_id, experiment_id, variant, input_hash, score, judge_notes, now),
			)
			self._db.commit()

		return trial_id

	# ── analysis ───────────────────────────────────────────────────────────────

	def get_results(self, experiment_id: str) -> dict[str, Any]:
		"""
		Return a comprehensive result dict:
		  experiment   – the experiment row as dict
		  trials_a     – list of trial dicts for variant a
		  trials_b     – list of trial dicts for variant b
		  score_a      – mean score for variant a (0.0 if no trials)
		  score_b      – mean score for variant b (0.0 if no trials)
		  winner       – 'a'|'b'|'tie'|None  (None = not yet decided)
		  needs_more   – True if experiment still needs more trials
		"""
		exp = self._db.execute(
			'SELECT * FROM experiments WHERE id=?', (experiment_id,)
		).fetchone()
		if exp is None:
			raise KeyError(f'Experiment {experiment_id!r} not found')
		exp_dict = dict(exp)

		all_trials = self._db.execute(
			'SELECT * FROM trials WHERE experiment_id=? ORDER BY created_at ASC',
			(experiment_id,),
		).fetchall()
		trials_a = [dict(t) for t in all_trials if t['variant'] == 'a']
		trials_b = [dict(t) for t in all_trials if t['variant'] == 'b']

		score_a = (sum(t['score'] for t in trials_a) / len(trials_a)) if trials_a else 0.0
		score_b = (sum(t['score'] for t in trials_b) / len(trials_b)) if trials_b else 0.0

		# Derive current winner from stored field, or compute from scores
		stored_winner = exp_dict.get('winner') or None
		if stored_winner == '':
			stored_winner = None

		if stored_winner:
			current_winner: str | None = stored_winner
			needs_more = False
		else:
			current_winner = None
			needs_more = True

		return {
			'experiment': exp_dict,
			'trials_a':   trials_a,
			'trials_b':   trials_b,
			'score_a':    score_a,
			'score_b':    score_b,
			'winner':     current_winner,
			'needs_more': needs_more,
		}

	def check_and_promote(self, experiment_id: str) -> str | None:
		"""
		Evaluate trial win counts.  If one variant has >= promotions_needed more wins
		than the other, mark the experiment completed/promoted and return 'a'|'b'.
		On a statistical tie (equal wins), mark 'tie'.
		Returns the winner letter ('a'|'b') or None if more data is needed.
		"""
		exp = self._db.execute(
			'SELECT * FROM experiments WHERE id=?', (experiment_id,)
		).fetchone()
		if exp is None:
			raise KeyError(f'Experiment {experiment_id!r} not found')
		exp_dict = dict(exp)

		if exp_dict['status'] != 'active':
			# Already decided — return stored winner or None for tie
			w = exp_dict.get('winner') or ''
			return w if w in ('a', 'b') else None

		promotions_needed: int = exp_dict['promotions_needed']

		# Count trials per variant
		counts = self._db.execute(
			"""SELECT variant, COUNT(*) as cnt FROM trials
			   WHERE experiment_id=? GROUP BY variant""",
			(experiment_id,),
		).fetchall()
		count_map: dict[str, int] = {r['variant']: r['cnt'] for r in counts}
		cnt_a = count_map.get('a', 0)
		cnt_b = count_map.get('b', 0)

		# A "win" per trial: higher score wins; compute head-to-head wins by score
		# We use mean scores as the decision metric — simpler and deterministic.
		all_trials = self._db.execute(
			'SELECT variant, score FROM trials WHERE experiment_id=?',
			(experiment_id,),
		).fetchall()

		scores_a = [t['score'] for t in all_trials if t['variant'] == 'a']
		scores_b = [t['score'] for t in all_trials if t['variant'] == 'b']

		# Need at least promotions_needed trials on each side
		if len(scores_a) < promotions_needed or len(scores_b) < promotions_needed:
			return None

		mean_a = sum(scores_a) / len(scores_a)
		mean_b = sum(scores_b) / len(scores_b)

		# Count individual trial wins
		wins_a = sum(1 for s in scores_a if s > mean_b)
		wins_b = sum(1 for s in scores_b if s > mean_a)

		margin = wins_a - wins_b
		now = time.time()

		if abs(margin) >= promotions_needed:
			winner = 'a' if margin > 0 else 'b'
			with self._lock:
				self._db.execute(
					"""UPDATE experiments
					   SET status='promoted', winner=?, completed_at=?
					   WHERE id=?""",
					(winner, now, experiment_id),
				)
				self._db.commit()
			return winner

		# Check if totals are exhausted and it's effectively a tie
		total = len(scores_a) + len(scores_b)
		if total >= promotions_needed * 10 and abs(margin) < promotions_needed:
			with self._lock:
				self._db.execute(
					"""UPDATE experiments
					   SET status='completed', winner='tie', completed_at=?
					   WHERE id=?""",
					(now, experiment_id),
				)
				self._db.commit()
			return None  # tie — no clear winner

		return None

	# ── internals ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn


# ── module-level singleton ─────────────────────────────────────────────────────

_store: ABTestStore | None = None
_singleton_lock = threading.Lock()


def get_ab_test_store() -> ABTestStore:
	global _store
	if _store is None:
		with _singleton_lock:
			if _store is None:
				_store = ABTestStore()
	return _store

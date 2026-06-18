# core/competitor_graph.py
"""
CompetitorGraph — living graph of competitors, their wins, certifications, and relationships.

Each rfp_competitor_analyst run upserts into this graph via the module-level singleton.
Thread-safe SQLite backend using WAL mode.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd

_DB_PATH = _wdd() / 'competitor_graph.db'

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS competitors (
	id               TEXT PRIMARY KEY,
	name             TEXT UNIQUE NOT NULL,
	website          TEXT DEFAULT '',
	description      TEXT DEFAULT '',
	certifications   TEXT DEFAULT '[]',
	naics_codes      TEXT DEFAULT '[]',
	notes            TEXT DEFAULT '',
	updated_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_wins (
	id                  TEXT PRIMARY KEY,
	competitor_id       TEXT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
	issuer              TEXT DEFAULT '',
	contract_title      TEXT DEFAULT '',
	naics               TEXT DEFAULT '',
	contract_value_est  REAL DEFAULT 0,
	award_date          TEXT DEFAULT '',
	period              TEXT DEFAULT '',
	source              TEXT DEFAULT '',
	created_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_appearances (
	id              TEXT PRIMARY KEY,
	competitor_id   TEXT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
	rfp_id          TEXT NOT NULL,
	rfp_title       TEXT DEFAULT '',
	issuer          TEXT DEFAULT '',
	role            TEXT NOT NULL DEFAULT 'likely_bidder'
	                     CHECK(role IN ('incumbent','likely_bidder','won','lost')),
	created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
	id            TEXT PRIMARY KEY,
	competitor_a  TEXT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
	competitor_b  TEXT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
	rel_type      TEXT NOT NULL,
	notes         TEXT DEFAULT '',
	created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS cw_competitor   ON contract_wins(competitor_id);
CREATE INDEX IF NOT EXISTS cw_issuer       ON contract_wins(issuer);
CREATE INDEX IF NOT EXISTS cw_naics        ON contract_wins(naics);
CREATE INDEX IF NOT EXISTS ra_competitor   ON rfp_appearances(competitor_id);
CREATE INDEX IF NOT EXISTS ra_rfp          ON rfp_appearances(rfp_id);
CREATE INDEX IF NOT EXISTS rel_a           ON relationships(competitor_a);
CREATE INDEX IF NOT EXISTS rel_b           ON relationships(competitor_b);
"""


def _gen_id() -> str:
	import uuid
	return str(uuid.uuid4())


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
	return {col[0]: row[col[0]] for col in cursor.description}


def _parse_json_field(value: str | None, fallback: Any = None) -> Any:
	if not value:
		return fallback if fallback is not None else []
	try:
		return json.loads(value)
	except (json.JSONDecodeError, TypeError):
		return fallback if fallback is not None else []


class CompetitorGraph:
	"""
	Living graph of competitors, contract wins, RFP appearances, and inter-competitor
	relationships. Backed by SQLite with WAL mode. All public methods are thread-safe.
	"""

	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db = self._open()

	# ── lifecycle ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn

	def close(self) -> None:
		with self._lock:
			self._db.close()

	# ── internal helpers ──────────────────────────────────────────────────────

	def _get_competitor_id(self, name: str) -> str | None:
		"""Return the competitor id for *name*, or None if not found."""
		row = self._db.execute(
			'SELECT id FROM competitors WHERE name=?', (name,)
		).fetchone()
		return row['id'] if row else None

	def _require_competitor_id(self, name: str) -> str:
		"""Return the competitor id, creating a minimal record if absent."""
		cid = self._get_competitor_id(name)
		if cid is None:
			cid = self.upsert_competitor(name)
		return cid

	# ── upsert competitor ─────────────────────────────────────────────────────

	def upsert_competitor(
		self,
		name: str,
		website: str = '',
		description: str = '',
		certifications: list[str] | None = None,
		naics_codes: list[str] | None = None,
		notes: str = '',
	) -> str:
		"""
		Insert or update a competitor record.  Returns the competitor id.
		Existing rows are updated only for non-empty incoming fields so that
		partial upserts don't wipe previously stored data.
		"""
		if not name or not name.strip():
			raise ValueError('competitor name must be non-empty')

		name = name.strip()
		certs_json = json.dumps(certifications or [])
		naics_json = json.dumps(naics_codes or [])
		now = time.time()

		with self._lock:
			existing = self._db.execute(
				'SELECT id, certifications, naics_codes FROM competitors WHERE name=?',
				(name,),
			).fetchone()

			if existing is None:
				cid = _gen_id()
				self._db.execute(
					"""INSERT INTO competitors
					   (id, name, website, description, certifications, naics_codes, notes, updated_at)
					   VALUES (?,?,?,?,?,?,?,?)""",
					(cid, name, website, description, certs_json, naics_json, notes, now),
				)
			else:
				cid = existing['id']
				# Merge list fields — union of existing and new values
				existing_certs = _parse_json_field(existing['certifications'])
				existing_naics = _parse_json_field(existing['naics_codes'])
				merged_certs = list(dict.fromkeys(existing_certs + (certifications or [])))
				merged_naics = list(dict.fromkeys(existing_naics + (naics_codes or [])))

				self._db.execute(
					"""UPDATE competitors SET
					   website          = CASE WHEN ?!='' THEN ? ELSE website END,
					   description      = CASE WHEN ?!='' THEN ? ELSE description END,
					   certifications   = ?,
					   naics_codes      = ?,
					   notes            = CASE WHEN ?!='' THEN ? ELSE notes END,
					   updated_at       = ?
					   WHERE id=?""",
					(
						website, website,
						description, description,
						json.dumps(merged_certs),
						json.dumps(merged_naics),
						notes, notes,
						now,
						cid,
					),
				)
			self._db.commit()
		return cid

	# ── contract wins ─────────────────────────────────────────────────────────

	def add_contract_win(
		self,
		competitor_name: str,
		issuer: str,
		contract_title: str,
		naics: str = '',
		value_est: float = 0.0,
		award_date: str = '',
		period: str = '',
		source: str = '',
	) -> str:
		"""
		Record a contract win for a competitor.  Deduplicates on
		(competitor_id, issuer, contract_title, award_date) to prevent double-inserts
		from repeated analyst runs.  Returns the record id.
		"""
		if not competitor_name or not competitor_name.strip():
			raise ValueError('competitor_name must be non-empty')
		if not issuer or not contract_title:
			raise ValueError('issuer and contract_title are required')

		with self._lock:
			cid = self._require_competitor_id(competitor_name.strip())
			# Idempotency check
			existing = self._db.execute(
				"""SELECT id FROM contract_wins
				   WHERE competitor_id=? AND issuer=? AND contract_title=? AND award_date=?""",
				(cid, issuer, contract_title, award_date),
			).fetchone()
			if existing:
				return existing['id']

			win_id = _gen_id()
			self._db.execute(
				"""INSERT INTO contract_wins
				   (id, competitor_id, issuer, contract_title, naics, contract_value_est,
				    award_date, period, source, created_at)
				   VALUES (?,?,?,?,?,?,?,?,?,?)""",
				(win_id, cid, issuer, contract_title, naics, value_est,
				 award_date, period, source, time.time()),
			)
			self._db.commit()
		return win_id

	# ── rfp appearances ───────────────────────────────────────────────────────

	def record_rfp_appearance(
		self,
		competitor_name: str,
		rfp_id: str,
		rfp_title: str,
		issuer: str,
		role: str = 'likely_bidder',
	) -> str:
		"""
		Record that a competitor appeared in an RFP analysis.
		Deduplicates on (competitor_id, rfp_id); if role changes the row is updated.
		Returns the record id.
		"""
		valid_roles = {'incumbent', 'likely_bidder', 'won', 'lost'}
		if role not in valid_roles:
			raise ValueError(f'role must be one of {valid_roles}, got {role!r}')
		if not competitor_name or not competitor_name.strip():
			raise ValueError('competitor_name must be non-empty')
		if not rfp_id:
			raise ValueError('rfp_id must be non-empty')

		with self._lock:
			cid = self._require_competitor_id(competitor_name.strip())
			existing = self._db.execute(
				'SELECT id FROM rfp_appearances WHERE competitor_id=? AND rfp_id=?',
				(cid, rfp_id),
			).fetchone()

			if existing:
				self._db.execute(
					"""UPDATE rfp_appearances
					   SET role=?, rfp_title=?, issuer=? WHERE id=?""",
					(role, rfp_title, issuer, existing['id']),
				)
				self._db.commit()
				return existing['id']

			app_id = _gen_id()
			self._db.execute(
				"""INSERT INTO rfp_appearances
				   (id, competitor_id, rfp_id, rfp_title, issuer, role, created_at)
				   VALUES (?,?,?,?,?,?,?)""",
				(app_id, cid, rfp_id, rfp_title, issuer, role, time.time()),
			)
			self._db.commit()
		return app_id

	# ── relationships ─────────────────────────────────────────────────────────

	def add_relationship(
		self,
		name_a: str,
		name_b: str,
		rel_type: str,
		notes: str = '',
	) -> str:
		"""
		Record a relationship between two competitors (e.g. 'teaming_partner',
		'subcontractor', 'subsidiary').  Deduplicates on the canonical
		(min_id, max_id, rel_type) triple.  Returns the record id.
		"""
		if not name_a or not name_b:
			raise ValueError('both competitor names must be non-empty')
		if not rel_type:
			raise ValueError('rel_type must be non-empty')
		if name_a.strip().lower() == name_b.strip().lower():
			raise ValueError('a competitor cannot have a relationship with itself')

		with self._lock:
			aid = self._require_competitor_id(name_a.strip())
			bid = self._require_competitor_id(name_b.strip())
			# Canonical ordering prevents (A,B) / (B,A) duplicates
			ca, cb = (aid, bid) if aid < bid else (bid, aid)

			existing = self._db.execute(
				"""SELECT id FROM relationships
				   WHERE competitor_a=? AND competitor_b=? AND rel_type=?""",
				(ca, cb, rel_type),
			).fetchone()
			if existing:
				if notes:
					self._db.execute(
						'UPDATE relationships SET notes=? WHERE id=?',
						(notes, existing['id']),
					)
					self._db.commit()
				return existing['id']

			rel_id = _gen_id()
			self._db.execute(
				"""INSERT INTO relationships
				   (id, competitor_a, competitor_b, rel_type, notes, created_at)
				   VALUES (?,?,?,?,?,?)""",
				(rel_id, ca, cb, rel_type, notes, time.time()),
			)
			self._db.commit()
		return rel_id

	# ── reads ─────────────────────────────────────────────────────────────────

	def get_competitor(self, name: str) -> dict[str, Any] | None:
		"""Return the full competitor record or None if not found."""
		if not name:
			return None
		row = self._db.execute(
			'SELECT * FROM competitors WHERE name=?', (name.strip(),)
		).fetchone()
		if row is None:
			return None
		d = dict(row)
		d['certifications'] = _parse_json_field(d.get('certifications'))
		d['naics_codes'] = _parse_json_field(d.get('naics_codes'))
		return d

	def query_competitors(
		self,
		naics: str | None = None,
		issuer: str | None = None,
		limit: int = 20,
	) -> list[dict[str, Any]]:
		"""
		Return competitors filtered by NAICS code (JSON-contains substring match)
		and/or by issuer (any contract win with that issuer).  Ordered by most-recently
		updated first.
		"""
		if limit < 1:
			raise ValueError('limit must be >= 1')

		params: list[Any] = []
		clauses: list[str] = []

		if naics:
			clauses.append("c.naics_codes LIKE ?")
			params.append(f'%{naics}%')

		if issuer:
			clauses.append(
				"c.id IN (SELECT competitor_id FROM contract_wins WHERE issuer LIKE ?)"
			)
			params.append(f'%{issuer}%')

		where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
		sql = f"""
			SELECT c.* FROM competitors c
			{where}
			ORDER BY c.updated_at DESC
			LIMIT ?
		"""
		params.append(limit)

		rows = self._db.execute(sql, params).fetchall()
		results = []
		for row in rows:
			d = dict(row)
			d['certifications'] = _parse_json_field(d.get('certifications'))
			d['naics_codes'] = _parse_json_field(d.get('naics_codes'))
			results.append(d)
		return results

	def get_rfp_landscape(self, rfp_id: str) -> dict[str, Any]:
		"""
		Return a landscape summary for a given RFP:
		  - incumbents: competitors with role='incumbent'
		  - likely_bidders: competitors with role='likely_bidder'
		  - our_differentiation_data: aggregated win history + certs for all
		    competitors appearing in this RFP, structured for gap analysis
		"""
		if not rfp_id:
			raise ValueError('rfp_id must be non-empty')

		appearances = self._db.execute(
			"""SELECT ra.role, c.id, c.name, c.website, c.certifications,
			          c.naics_codes, c.description
			   FROM rfp_appearances ra
			   JOIN competitors c ON c.id = ra.competitor_id
			   WHERE ra.rfp_id=?""",
			(rfp_id,),
		).fetchall()

		incumbents: list[dict[str, Any]] = []
		likely_bidders: list[dict[str, Any]] = []
		differentiation_data: list[dict[str, Any]] = []

		for row in appearances:
			d = dict(row)
			d['certifications'] = _parse_json_field(d.get('certifications'))
			d['naics_codes'] = _parse_json_field(d.get('naics_codes'))

			wins = self._db.execute(
				"""SELECT issuer, contract_title, naics, contract_value_est, award_date
				   FROM contract_wins WHERE competitor_id=?
				   ORDER BY award_date DESC LIMIT 5""",
				(d['id'],),
			).fetchall()
			d['recent_wins'] = [dict(w) for w in wins]

			role = d.pop('role')
			if role == 'incumbent':
				incumbents.append(d)
			elif role == 'likely_bidder':
				likely_bidders.append(d)

			differentiation_data.append({
				'name': d['name'],
				'certifications': d['certifications'],
				'naics_codes': d['naics_codes'],
				'win_count': len(d['recent_wins']),
				'recent_wins': d['recent_wins'],
			})

		return {
			'rfp_id': rfp_id,
			'incumbents': incumbents,
			'likely_bidders': likely_bidders,
			'our_differentiation_data': differentiation_data,
		}

	def win_history(
		self,
		competitor_name: str,
		limit: int = 10,
	) -> list[dict[str, Any]]:
		"""Return up to *limit* contract wins for a competitor, newest first."""
		if not competitor_name:
			raise ValueError('competitor_name must be non-empty')
		if limit < 1:
			raise ValueError('limit must be >= 1')

		cid = self._get_competitor_id(competitor_name.strip())
		if cid is None:
			return []

		rows = self._db.execute(
			"""SELECT * FROM contract_wins WHERE competitor_id=?
			   ORDER BY award_date DESC, created_at DESC LIMIT ?""",
			(cid, limit),
		).fetchall()
		return [dict(r) for r in rows]


# ── module-level singleton ─────────────────────────────────────────────────────

_singleton: CompetitorGraph | None = None
_singleton_lock = threading.Lock()


def get_singleton() -> CompetitorGraph:
	"""Return the process-wide CompetitorGraph instance, creating it on first call."""
	global _singleton
	if _singleton is None:
		with _singleton_lock:
			if _singleton is None:
				_singleton = CompetitorGraph()
	return _singleton

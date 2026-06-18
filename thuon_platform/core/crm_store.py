# core/crm_store.py
"""
CRM store — contacts, interactions, organizations, partnerships.

Tracks relationships with contracting officers, teaming partners,
subcontractors, and certifications against a local SQLite database.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from uuid6 import uuid7

from core.bundle import writable_data_dir as _wdd


# ── helpers ───────────────────────────────────────────────────────────────────

def _uuid7str() -> str:
	return str(uuid7())


def _now() -> float:
	return time.time()


def _dumps(v: Any) -> str:
	return json.dumps(v, ensure_ascii=False)


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
	return dict(zip([c[0] for c in cursor.description], row))


def _json_field(row: dict[str, Any], key: str) -> Any:
	"""Parse a JSON-encoded field in-place; return the parsed value."""
	raw = row.get(key)
	if raw is None:
		return []
	try:
		return json.loads(raw)
	except (json.JSONDecodeError, TypeError):
		return raw


def _hydrate(row: dict[str, Any], json_keys: list[str]) -> dict[str, Any]:
	for k in json_keys:
		row[k] = _json_field(row, k)
	return row


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS contacts (
	id           TEXT PRIMARY KEY,
	name         TEXT NOT NULL,
	role         TEXT NOT NULL DEFAULT '',
	organization TEXT NOT NULL DEFAULT '',
	email        TEXT NOT NULL DEFAULT '',
	phone        TEXT NOT NULL DEFAULT '',
	linkedin     TEXT NOT NULL DEFAULT '',
	notes        TEXT NOT NULL DEFAULT '',
	preferences  TEXT NOT NULL DEFAULT '{}',
	tags         TEXT NOT NULL DEFAULT '[]',
	created_at   REAL NOT NULL,
	updated_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
	id               TEXT PRIMARY KEY,
	contact_id       TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
	interaction_type TEXT NOT NULL DEFAULT '',
	subject          TEXT NOT NULL DEFAULT '',
	notes            TEXT NOT NULL DEFAULT '',
	rfp_id           TEXT NOT NULL DEFAULT '',
	outcome          TEXT NOT NULL DEFAULT '',
	created_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
	id             TEXT PRIMARY KEY,
	name           TEXT UNIQUE NOT NULL,
	org_type       TEXT NOT NULL CHECK(org_type IN ('agency','partner','competitor','subcontractor','prime')),
	certifications TEXT NOT NULL DEFAULT '[]',
	naics_codes    TEXT NOT NULL DEFAULT '[]',
	sam_uei        TEXT NOT NULL DEFAULT '',
	website        TEXT NOT NULL DEFAULT '',
	notes          TEXT NOT NULL DEFAULT '',
	updated_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS partnerships (
	id           TEXT PRIMARY KEY,
	org_id       TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
	partner_type TEXT NOT NULL DEFAULT '',
	active       INTEGER NOT NULL DEFAULT 1,
	capabilities TEXT NOT NULL DEFAULT '[]',
	notes        TEXT NOT NULL DEFAULT '',
	created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_email        ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_organization ON contacts(organization);
CREATE INDEX IF NOT EXISTS idx_contacts_role         ON contacts(role);
CREATE INDEX IF NOT EXISTS idx_interactions_contact  ON interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_interactions_rfp      ON interactions(rfp_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_org      ON partnerships(org_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_type     ON partnerships(partner_type);
"""


# ── CRMStore ──────────────────────────────────────────────────────────────────

class CRMStore:
	"""
	Thread-safe CRM backed by SQLite.

	One connection per thread via threading.local; WAL mode allows concurrent
	reads while writes are serialised through _write_lock.
	"""

	def __init__(self, db_path: Path | None = None) -> None:
		self._db_path: Path = db_path or (_wdd() / 'crm.db')
		self._db_path.parent.mkdir(parents=True, exist_ok=True)
		self._local = threading.local()
		self._write_lock = threading.Lock()
		# initialise schema on the calling thread
		conn = self._conn()
		conn.executescript(_DDL)
		conn.commit()

	# ── connection management ─────────────────────────────────────────────────

	def _conn(self) -> sqlite3.Connection:
		conn: sqlite3.Connection | None = getattr(self._local, 'conn', None)
		if conn is None:
			conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
			conn.row_factory = sqlite3.Row
			conn.execute("PRAGMA journal_mode = WAL")
			conn.execute("PRAGMA foreign_keys = ON")
			conn.execute("PRAGMA synchronous = NORMAL")
			self._local.conn = conn
		return conn

	def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
		return self._conn().execute(sql, params)

	def _write(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
		with self._write_lock:
			conn = self._conn()
			cur = conn.execute(sql, params)
			conn.commit()
			return cur

	def _write_many(self, ops: list[tuple[str, tuple]]) -> None:
		with self._write_lock:
			conn = self._conn()
			for sql, params in ops:
				conn.execute(sql, params)
			conn.commit()

	# ── contacts ──────────────────────────────────────────────────────────────

	def upsert_contact(
		self,
		name: str,
		role: str,
		organization: str,
		email: str = '',
		phone: str = '',
		linkedin: str = '',
		notes: str = '',
		preferences: dict[str, Any] | None = None,
		tags: list[str] | None = None,
	) -> str:
		"""
		Insert or update a contact matched by (name, organization).

		Returns the contact id.
		"""
		assert name.strip(), "contact name must not be empty"
		preferences = preferences or {}
		tags = tags or []
		now = _now()

		existing = self._execute(
			"SELECT id FROM contacts WHERE name = ? AND organization = ?",
			(name, organization),
		).fetchone()

		if existing:
			contact_id: str = existing[0]
			self._write(
				"""UPDATE contacts
				   SET role=?, email=?, phone=?, linkedin=?, notes=?,
				       preferences=?, tags=?, updated_at=?
				   WHERE id=?""",
				(role, email, phone, linkedin, notes,
				 _dumps(preferences), _dumps(tags), now, contact_id),
			)
			return contact_id

		contact_id = _uuid7str()
		self._write(
			"""INSERT INTO contacts
			   (id, name, role, organization, email, phone, linkedin, notes,
			    preferences, tags, created_at, updated_at)
			   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
			(contact_id, name, role, organization, email, phone, linkedin, notes,
			 _dumps(preferences), _dumps(tags), now, now),
		)
		return contact_id

	def get_contact(self, contact_id: str) -> dict[str, Any] | None:
		row = self._execute(
			"SELECT * FROM contacts WHERE id = ?", (contact_id,)
		).fetchone()
		if row is None:
			return None
		d = dict(row)
		return _hydrate(d, ['preferences', 'tags'])

	def search_contacts(
		self,
		query: str = '',
		organization: str = '',
		role: str = '',
	) -> list[dict[str, Any]]:
		"""
		Full-text search over name/email/notes plus optional exact filters.

		All filters are ANDed. Empty strings mean "no filter".
		"""
		clauses: list[str] = []
		params: list[Any] = []

		if query:
			pattern = f'%{query}%'
			clauses.append(
				"(name LIKE ? OR email LIKE ? OR notes LIKE ? OR linkedin LIKE ?)"
			)
			params.extend([pattern, pattern, pattern, pattern])

		if organization:
			clauses.append("organization = ?")
			params.append(organization)

		if role:
			clauses.append("role LIKE ?")
			params.append(f'%{role}%')

		where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
		sql = f"SELECT * FROM contacts {where} ORDER BY updated_at DESC"
		rows = self._execute(sql, tuple(params)).fetchall()
		return [_hydrate(dict(r), ['preferences', 'tags']) for r in rows]

	# ── interactions ─────────────────────────────────────────────────────────

	def log_interaction(
		self,
		contact_id: str,
		interaction_type: str,
		subject: str,
		notes: str = '',
		rfp_id: str = '',
		outcome: str = '',
	) -> str:
		"""Log an interaction with a contact. Returns the interaction id."""
		assert contact_id, "contact_id required"
		assert interaction_type, "interaction_type required"

		interaction_id = _uuid7str()
		self._write(
			"""INSERT INTO interactions
			   (id, contact_id, interaction_type, subject, notes, rfp_id, outcome, created_at)
			   VALUES (?,?,?,?,?,?,?,?)""",
			(interaction_id, contact_id, interaction_type, subject,
			 notes, rfp_id, outcome, _now()),
		)
		return interaction_id

	def get_contact_history(
		self,
		contact_id: str,
		limit: int = 20,
	) -> list[dict[str, Any]]:
		"""Return the most recent interactions for a contact, newest first."""
		rows = self._execute(
			"""SELECT * FROM interactions
			   WHERE contact_id = ?
			   ORDER BY created_at DESC
			   LIMIT ?""",
			(contact_id, limit),
		).fetchall()
		return [dict(r) for r in rows]

	def get_rfp_contacts(self, rfp_id: str) -> list[dict[str, Any]]:
		"""
		Return all interactions (with joined contact details) related to an RFP.
		"""
		assert rfp_id, "rfp_id required"
		rows = self._execute(
			"""SELECT i.*, c.name AS contact_name, c.role AS contact_role,
			          c.organization AS contact_organization, c.email AS contact_email
			   FROM interactions i
			   JOIN contacts c ON c.id = i.contact_id
			   WHERE i.rfp_id = ?
			   ORDER BY i.created_at DESC""",
			(rfp_id,),
		).fetchall()
		return [dict(r) for r in rows]

	# ── organizations ─────────────────────────────────────────────────────────

	def upsert_org(
		self,
		name: str,
		org_type: str,
		certifications: list[str] | None = None,
		naics_codes: list[str] | None = None,
		sam_uei: str = '',
		website: str = '',
		notes: str = '',
	) -> str:
		"""
		Insert or update an organization by name.

		Returns the organization id.
		"""
		assert name.strip(), "org name must not be empty"
		valid_types = {'agency', 'partner', 'competitor', 'subcontractor', 'prime'}
		assert org_type in valid_types, f"org_type must be one of {valid_types}"

		certifications = certifications or []
		naics_codes = naics_codes or []
		now = _now()

		existing = self._execute(
			"SELECT id FROM organizations WHERE name = ?", (name,)
		).fetchone()

		if existing:
			org_id: str = existing[0]
			self._write(
				"""UPDATE organizations
				   SET org_type=?, certifications=?, naics_codes=?,
				       sam_uei=?, website=?, notes=?, updated_at=?
				   WHERE id=?""",
				(org_type, _dumps(certifications), _dumps(naics_codes),
				 sam_uei, website, notes, now, org_id),
			)
			return org_id

		org_id = _uuid7str()
		self._write(
			"""INSERT INTO organizations
			   (id, name, org_type, certifications, naics_codes,
			    sam_uei, website, notes, updated_at)
			   VALUES (?,?,?,?,?,?,?,?,?)""",
			(org_id, name, org_type, _dumps(certifications), _dumps(naics_codes),
			 sam_uei, website, notes, now),
		)
		return org_id

	def get_org(self, name: str) -> dict[str, Any] | None:
		row = self._execute(
			"SELECT * FROM organizations WHERE name = ?", (name,)
		).fetchone()
		if row is None:
			return None
		d = dict(row)
		return _hydrate(d, ['certifications', 'naics_codes'])

	def certified_partners(self, cert: str) -> list[dict[str, Any]]:
		"""
		Return all organizations whose certifications list contains `cert`.

		Supports common values: '8a', 'SDVOSB', 'HUBZone', 'WOSB', 'VOSB', etc.
		Case-insensitive substring match inside the JSON array.
		"""
		assert cert, "cert must not be empty"
		# JSON stored as a serialised list; use LIKE for a portable substring match.
		pattern = f'%{cert}%'
		rows = self._execute(
			"SELECT * FROM organizations WHERE certifications LIKE ?",
			(pattern,),
		).fetchall()
		results = []
		for row in rows:
			d = _hydrate(dict(row), ['certifications', 'naics_codes'])
			# secondary filter: ensure the cert is actually an element, not a substring
			if any(cert.lower() in c.lower() for c in d['certifications']):
				results.append(d)
		return results

	# ── partnerships ──────────────────────────────────────────────────────────

	def add_partnership(
		self,
		org_name: str,
		partner_type: str,
		capabilities: list[str] | None = None,
		notes: str = '',
	) -> str:
		"""
		Record a partnership with an organization (looked up by name).

		The organization must already exist (call upsert_org first).
		Returns the partnership id.
		"""
		assert org_name, "org_name required"
		assert partner_type, "partner_type required"
		capabilities = capabilities or []

		org = self._execute(
			"SELECT id FROM organizations WHERE name = ?", (org_name,)
		).fetchone()
		if org is None:
			raise ValueError(f"organization '{org_name}' not found — call upsert_org first")

		partnership_id = _uuid7str()
		self._write(
			"""INSERT INTO partnerships
			   (id, org_id, partner_type, active, capabilities, notes, created_at)
			   VALUES (?,?,?,1,?,?,?)""",
			(partnership_id, org[0], partner_type, _dumps(capabilities), notes, _now()),
		)
		return partnership_id

	def get_partners(
		self,
		partner_type: str | None = None,
		active_only: bool = True,
	) -> list[dict[str, Any]]:
		"""
		Return partnerships joined with organization details.

		Filters: partner_type (exact), active_only (default True).
		"""
		clauses: list[str] = []
		params: list[Any] = []

		if active_only:
			clauses.append("p.active = 1")

		if partner_type:
			clauses.append("p.partner_type = ?")
			params.append(partner_type)

		where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
		sql = f"""
			SELECT p.*, o.name AS org_name, o.org_type, o.certifications,
			       o.naics_codes, o.sam_uei, o.website
			FROM partnerships p
			JOIN organizations o ON o.id = p.org_id
			{where}
			ORDER BY p.created_at DESC
		"""
		rows = self._execute(sql, tuple(params)).fetchall()
		results = []
		for row in rows:
			d = dict(row)
			_hydrate(d, ['capabilities', 'certifications', 'naics_codes'])
			results.append(d)
		return results

	# ── housekeeping ──────────────────────────────────────────────────────────

	def close(self) -> None:
		"""Close the per-thread connection, if open."""
		conn: sqlite3.Connection | None = getattr(self._local, 'conn', None)
		if conn is not None:
			conn.close()
			self._local.conn = None


# ── module-level singleton ────────────────────────────────────────────────────

_crm_store: CRMStore | None = None
_crm_store_lock = threading.Lock()


def get_crm_store() -> CRMStore:
	global _crm_store
	if _crm_store is None:
		with _crm_store_lock:
			if _crm_store is None:
				_crm_store = CRMStore()
	return _crm_store

# core/lineage_store.py
"""
LineageStore — provenance tracking for every paragraph/section generated.

Tracks: source KB file, capability version, model used, and full edit history
for every document section produced by the Thuon platform.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd

_DB_PATH = _wdd() / 'lineage.db'

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    doc_type    TEXT NOT NULL,
    rfp_id      TEXT DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS documents_rfp_id   ON documents(rfp_id);

CREATE TABLE IF NOT EXISTS sections (
    id           TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS sections_document_id  ON sections(document_id);
CREATE INDEX IF NOT EXISTS sections_content_hash ON sections(content_hash);

CREATE TABLE IF NOT EXISTS section_sources (
    id             TEXT PRIMARY KEY,
    section_id     TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    source_type    TEXT NOT NULL,           -- 'kb_file' | 'url' | 'user_input' | etc.
    source_ref     TEXT NOT NULL,           -- file path, URL, or identifier
    source_excerpt TEXT NOT NULL DEFAULT '',
    capability     TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS section_sources_section_id  ON section_sources(section_id);
CREATE INDEX IF NOT EXISTS section_sources_source_ref  ON section_sources(source_ref);

CREATE TABLE IF NOT EXISTS edits (
    id          TEXT PRIMARY KEY,
    section_id  TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    editor      TEXT NOT NULL DEFAULT '',
    old_hash    TEXT NOT NULL,
    new_hash    TEXT NOT NULL,
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS edits_section_id ON edits(section_id);
CREATE INDEX IF NOT EXISTS edits_created_at ON edits(created_at);
"""


def _sha256(content: str) -> str:
	return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _new_id() -> str:
	return str(uuid.uuid4())


class LineageStore:
	"""
	Thread-safe SQLite-backed store for document/section provenance.

	All write methods acquire a single threading.Lock before committing so
	concurrent threads share one connection safely (check_same_thread=False +
	WAL mode means readers never block writers in practice).
	"""

	def __init__(self, db_path: Path | None = None) -> None:
		self._path = db_path or _DB_PATH
		self._path.parent.mkdir(parents=True, exist_ok=True)
		self._lock = threading.Lock()
		self._db   = self._open()

	# ── document ──────────────────────────────────────────────────────────────

	def create_document(
		self,
		doc_type: str,
		rfp_id: str = '',
		title: str = '',
	) -> str:
		"""Insert a new document record and return its id."""
		doc_id = _new_id()
		now    = time.time()
		with self._lock:
			self._db.execute(
				"INSERT INTO documents (id, doc_type, rfp_id, title, created_at) VALUES (?,?,?,?,?)",
				(doc_id, doc_type, rfp_id or '', title or '', now),
			)
			self._db.commit()
		return doc_id

	# ── section ───────────────────────────────────────────────────────────────

	def create_section(
		self,
		document_id: str,
		section_name: str,
		content: str,
	) -> str:
		"""
		Insert a new section under *document_id* and return its id.
		*content* is hashed with SHA-256; only the hash is stored here.
		"""
		section_id   = _new_id()
		content_hash = _sha256(content)
		now          = time.time()
		with self._lock:
			self._db.execute(
				"INSERT INTO sections (id, document_id, section_name, content_hash, created_at)"
				" VALUES (?,?,?,?,?)",
				(section_id, document_id, section_name, content_hash, now),
			)
			self._db.commit()
		return section_id

	# ── source attribution ────────────────────────────────────────────────────

	def add_source(
		self,
		section_id: str,
		source_type: str,
		source_ref: str,
		source_excerpt: str = '',
		capability: str = '',
		model: str = '',
	) -> str:
		"""
		Attach a provenance record to *section_id*.

		Parameters
		----------
		source_type:    Category string — e.g. 'kb_file', 'url', 'user_input'.
		source_ref:     Canonical identifier — file path, URL, etc.
		source_excerpt: Optional verbatim snippet from the source.
		capability:     Name/version of the Thuon capability that used this source.
		model:          LLM model identifier (e.g. 'claude-sonnet-4-6').

		Returns the new source record id.
		"""
		src_id = _new_id()
		now    = time.time()
		with self._lock:
			self._db.execute(
				"INSERT INTO section_sources"
				" (id, section_id, source_type, source_ref, source_excerpt, capability, model, created_at)"
				" VALUES (?,?,?,?,?,?,?,?)",
				(src_id, section_id, source_type, source_ref,
				 source_excerpt or '', capability or '', model or '', now),
			)
			self._db.commit()
		return src_id

	# ── edit history ──────────────────────────────────────────────────────────

	def record_edit(
		self,
		section_id: str,
		editor: str,
		old_content: str,
		new_content: str,
	) -> str:
		"""
		Record a content change for *section_id*.

		Both *old_content* and *new_content* are hashed; the section row's
		content_hash is updated to reflect the new state.

		Returns the new edit record id.
		"""
		edit_id  = _new_id()
		old_hash = _sha256(old_content)
		new_hash = _sha256(new_content)
		now      = time.time()
		with self._lock:
			self._db.execute(
				"INSERT INTO edits (id, section_id, editor, old_hash, new_hash, created_at)"
				" VALUES (?,?,?,?,?,?)",
				(edit_id, section_id, editor or '', old_hash, new_hash, now),
			)
			# Keep sections.content_hash current so get_document_lineage always
			# reflects the latest version without joining edits.
			self._db.execute(
				"UPDATE sections SET content_hash=? WHERE id=?",
				(new_hash, section_id),
			)
			self._db.commit()
		return edit_id

	# ── queries ───────────────────────────────────────────────────────────────

	def get_document_lineage(self, document_id: str) -> dict[str, Any]:
		"""
		Return a nested dict describing the full lineage of *document_id*:

		{
		  "document": {id, doc_type, rfp_id, title, created_at},
		  "sections": [
		    {
		      "section": {id, document_id, section_name, content_hash, created_at},
		      "sources": [{id, section_id, source_type, source_ref, ...}, ...],
		      "edits":   [{id, section_id, editor, old_hash, new_hash, created_at}, ...],
		    },
		    ...
		  ]
		}
		"""
		doc_row = self._db.execute(
			"SELECT * FROM documents WHERE id=?", (document_id,)
		).fetchone()
		if doc_row is None:
			return {}

		section_rows = self._db.execute(
			"SELECT * FROM sections WHERE document_id=? ORDER BY created_at ASC",
			(document_id,),
		).fetchall()

		sections_out: list[dict[str, Any]] = []
		for sec in section_rows:
			sec_id = sec['id']
			sources = self._db.execute(
				"SELECT * FROM section_sources WHERE section_id=? ORDER BY created_at ASC",
				(sec_id,),
			).fetchall()
			edits = self._db.execute(
				"SELECT * FROM edits WHERE section_id=? ORDER BY created_at ASC",
				(sec_id,),
			).fetchall()
			sections_out.append({
				'section': dict(sec),
				'sources': [dict(s) for s in sources],
				'edits':   [dict(e) for e in edits],
			})

		return {
			'document': dict(doc_row),
			'sections': sections_out,
		}

	def find_sections_citing(self, source_ref: str) -> list[dict[str, Any]]:
		"""
		Return every section that used *source_ref* as a source.

		Each entry in the returned list is a flat dict merging the section row
		and the matching source row so callers have full context in one pass:

		{
		  section_id, document_id, section_name, content_hash, section_created_at,
		  source_id, source_type, source_ref, source_excerpt, capability, model,
		  source_created_at,
		}
		"""
		rows = self._db.execute(
			"""
			SELECT
			    s.id           AS section_id,
			    s.document_id  AS document_id,
			    s.section_name AS section_name,
			    s.content_hash AS content_hash,
			    s.created_at   AS section_created_at,
			    ss.id          AS source_id,
			    ss.source_type AS source_type,
			    ss.source_ref  AS source_ref,
			    ss.source_excerpt AS source_excerpt,
			    ss.capability  AS capability,
			    ss.model       AS model,
			    ss.created_at  AS source_created_at
			FROM section_sources ss
			JOIN sections s ON s.id = ss.section_id
			WHERE ss.source_ref = ?
			ORDER BY ss.created_at ASC
			""",
			(source_ref,),
		).fetchall()
		return [dict(r) for r in rows]

	def get_section_history(self, section_id: str) -> list[dict[str, Any]]:
		"""
		Return all edit records for *section_id* in chronological order.

		Each dict has: {id, section_id, editor, old_hash, new_hash, created_at}.
		Returns an empty list if the section has never been edited (or does not exist).
		"""
		rows = self._db.execute(
			"SELECT * FROM edits WHERE section_id=? ORDER BY created_at ASC",
			(section_id,),
		).fetchall()
		return [dict(r) for r in rows]

	# ── internals ─────────────────────────────────────────────────────────────

	def _open(self) -> sqlite3.Connection:
		conn = sqlite3.connect(str(self._path), check_same_thread=False)
		conn.row_factory = sqlite3.Row
		conn.executescript(_DDL)
		conn.commit()
		return conn


# ── module-level singleton ─────────────────────────────────────────────────────

_store: LineageStore | None = None
_singleton_lock = threading.Lock()


def get_lineage_store() -> LineageStore:
	"""Return (and lazily initialise) the module-level LineageStore singleton."""
	global _store
	if _store is None:
		with _singleton_lock:
			if _store is None:
				_store = LineageStore()
	return _store

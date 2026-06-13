# core/rfp_tracker.py
"""
RFP record store — JSON-persisted, thread-safe.
Status FSM: discovered → evaluating → awaiting_strategy → responding
             → in_review → submitted → (won | lost | no_bid)
"""

from __future__ import annotations
import json
import threading
import time
from enum import Enum
from pathlib import Path

from uuid6 import uuid7

_STORE_PATH = Path(__file__).parent.parent / 'data' / 'rfp_tracker.json'


def _uuid7str() -> str:
	return str(uuid7())


class RFPStatus(str, Enum):
	DISCOVERED        = 'discovered'
	EVALUATING        = 'evaluating'
	AWAITING_STRATEGY = 'awaiting_strategy'
	RESPONDING        = 'responding'
	IN_REVIEW         = 'in_review'
	SUBMITTED         = 'submitted'
	WON               = 'won'
	LOST              = 'lost'
	NO_BID            = 'no_bid'


# Valid FSM transitions
_TRANSITIONS: dict[RFPStatus, list[RFPStatus]] = {
	RFPStatus.DISCOVERED:        [RFPStatus.EVALUATING, RFPStatus.NO_BID],
	RFPStatus.EVALUATING:        [RFPStatus.AWAITING_STRATEGY, RFPStatus.NO_BID],
	RFPStatus.AWAITING_STRATEGY: [RFPStatus.RESPONDING, RFPStatus.NO_BID],
	RFPStatus.RESPONDING:        [RFPStatus.IN_REVIEW],
	RFPStatus.IN_REVIEW:         [RFPStatus.SUBMITTED, RFPStatus.RESPONDING],
	RFPStatus.SUBMITTED:         [RFPStatus.WON, RFPStatus.LOST],
	RFPStatus.WON:               [],
	RFPStatus.LOST:              [],
	RFPStatus.NO_BID:            [],
}


class RFPRecord:
	__slots__ = (
		'id', 'title', 'issuer', 'source_url', 'deadline', 'summary',
		'bid_score', 'bid_recommendation', 'status', 'pipeline_step',
		'response_dir', 'pipeline_state', 'created_at', 'updated_at',
	)

	def __init__(
		self,
		title: str,
		issuer: str,
		summary: str,
		source_url: str | None = None,
		deadline: str | None = None,
		id: str | None = None,
		bid_score: float | None = None,
		bid_recommendation: str | None = None,
		status: str = RFPStatus.DISCOVERED,
		pipeline_step: str | None = None,
		response_dir: str | None = None,
		pipeline_state: dict | None = None,
		created_at: str | None = None,
		updated_at: str | None = None,
	):
		self.id                 = id or _uuid7str()
		self.title              = title
		self.issuer             = issuer
		self.summary            = summary
		self.source_url         = source_url
		self.deadline           = deadline
		self.bid_score          = bid_score
		self.bid_recommendation = bid_recommendation
		self.status             = RFPStatus(status)
		self.pipeline_step      = pipeline_step
		self.response_dir       = response_dir
		self.pipeline_state     = pipeline_state or {}
		now                     = str(time.time())
		self.created_at         = created_at or now
		self.updated_at         = updated_at or now

	def to_dict(self) -> dict:
		return {
			'id':                 self.id,
			'title':              self.title,
			'issuer':             self.issuer,
			'summary':            self.summary,
			'source_url':         self.source_url,
			'deadline':           self.deadline,
			'bid_score':          self.bid_score,
			'bid_recommendation': self.bid_recommendation,
			'status':             self.status.value,
			'pipeline_step':      self.pipeline_step,
			'response_dir':       self.response_dir,
			'pipeline_state':     self.pipeline_state,
			'created_at':         self.created_at,
			'updated_at':         self.updated_at,
		}

	@classmethod
	def from_dict(cls, d: dict) -> 'RFPRecord':
		return cls(**{k: v for k, v in d.items() if k in cls.__slots__})


class RFPTracker:
	def __init__(self, store_path: Path | str | None = None):
		self._path = Path(store_path or _STORE_PATH)
		self._lock = threading.Lock()
		self._records: dict[str, RFPRecord] = {}
		self._load()

	# ── CRUD ─────────────────────────────────────────────────────────────────

	def add(self, record: RFPRecord) -> RFPRecord:
		with self._lock:
			self._records[record.id] = record
			self._save()
		return record

	def create(self, title: str, issuer: str, summary: str, **kwargs) -> RFPRecord:
		record = RFPRecord(title=title, issuer=issuer, summary=summary, **kwargs)
		return self.add(record)

	def get(self, rfp_id: str) -> RFPRecord | None:
		return self._records.get(rfp_id)

	def all(self, status: str | None = None) -> list[RFPRecord]:
		records = list(self._records.values())
		if status:
			records = [r for r in records if r.status.value == status]
		return sorted(records, key=lambda r: r.created_at, reverse=True)

	def update(self, rfp_id: str, **fields) -> RFPRecord | None:
		with self._lock:
			record = self._records.get(rfp_id)
			if record is None:
				return None
			for k, v in fields.items():
				if hasattr(record, k):
					setattr(record, k, v)
			record.updated_at = str(time.time())
			self._save()
		return record

	def advance_status(self, rfp_id: str, to_status: str) -> RFPRecord | None:
		"""Advance status along the FSM; raises ValueError on invalid transition."""
		with self._lock:
			record = self._records.get(rfp_id)
			if record is None:
				return None
			target = RFPStatus(to_status)
			allowed = _TRANSITIONS.get(record.status, [])
			if target not in allowed:
				raise ValueError(
					f'Invalid transition {record.status.value!r} → {to_status!r}. '
					f'Allowed: {[s.value for s in allowed]}'
				)
			record.status = target
			record.updated_at = str(time.time())
			self._save()
		return record

	# ── Persistence ───────────────────────────────────────────────────────────

	def _save(self) -> None:
		self._path.parent.mkdir(parents=True, exist_ok=True)
		with open(self._path, 'w') as f:
			json.dump([r.to_dict() for r in self._records.values()], f, indent=2)

	def _load(self) -> None:
		if not self._path.exists():
			return
		try:
			with open(self._path) as f:
				raw = json.load(f)
		except (json.JSONDecodeError, OSError):
			return
		for d in raw:
			try:
				r = RFPRecord.from_dict(d)
				self._records[r.id] = r
			except (KeyError, ValueError, TypeError):
				pass


# Module-level singleton
_tracker: RFPTracker | None = None
_tracker_lock = threading.Lock()


def get_rfp_tracker() -> RFPTracker:
	global _tracker
	if _tracker is None:
		with _tracker_lock:
			if _tracker is None:
				_tracker = RFPTracker()
	return _tracker

"""Tests for core/rfp_tracker.py"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from pathlib import Path
import pytest

from core.rfp_tracker import RFPRecord, RFPStatus, RFPTracker, _TRANSITIONS


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _tracker(tmp_path) -> RFPTracker:
	return RFPTracker(store_path=tmp_path / 'rfp.json')


def _minimal(tracker: RFPTracker) -> RFPRecord:
	return tracker.create(title='Test RFP', issuer='Acme Corp', summary='A test')


# ── RFPRecord ─────────────────────────────────────────────────────────────────

class TestRFPRecord:
	def test_defaults(self):
		r = RFPRecord(title='T', issuer='I', summary='S')
		assert r.status == RFPStatus.DISCOVERED
		assert r.id
		assert r.source_url is None
		assert isinstance(r.pipeline_state, dict)

	def test_round_trip(self):
		r = RFPRecord(title='T', issuer='I', summary='S', bid_score=85.5)
		d = r.to_dict()
		r2 = RFPRecord.from_dict(d)
		assert r2.id == r.id
		assert r2.bid_score == 85.5
		assert r2.status == RFPStatus.DISCOVERED

	def test_status_coerced_from_string(self):
		r = RFPRecord(title='T', issuer='I', summary='S', status='evaluating')
		assert r.status == RFPStatus.EVALUATING

	def test_from_dict_all_slots(self):
		r = RFPRecord(
			title='T', issuer='I', summary='S',
			source_url='https://example.com',
			deadline='2026-12-31',
			bid_score=72.0,
			bid_recommendation='go',
			status='responding',
			pipeline_step='section_writer',
			response_dir='/tmp/rfp',
			pipeline_state={'phase': 'writing'},
		)
		r2 = RFPRecord.from_dict(r.to_dict())
		assert r2.source_url == 'https://example.com'
		assert r2.pipeline_state == {'phase': 'writing'}
		assert r2.status == RFPStatus.RESPONDING


# ── RFPTracker CRUD ───────────────────────────────────────────────────────────

class TestRFPTrackerCRUD:
	def test_create_and_get(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		found = t.get(r.id)
		assert found is not None
		assert found.title == 'Test RFP'
		assert found.issuer == 'Acme Corp'

	def test_get_missing_returns_none(self, tmp_path):
		t = _tracker(tmp_path)
		assert t.get('nonexistent-id') is None

	def test_all_returns_list(self, tmp_path):
		t = _tracker(tmp_path)
		assert t.all() == []
		_minimal(t)
		_minimal(t)
		assert len(t.all()) == 2

	def test_all_filter_by_status(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		t.advance_status(r.id, 'evaluating')
		_minimal(t)  # stays discovered

		discovered = t.all(status='discovered')
		evaluating = t.all(status='evaluating')
		assert len(discovered) == 1
		assert len(evaluating) == 1

	def test_update_fields(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		t.update(r.id, bid_score=90.0, bid_recommendation='go')
		updated = t.get(r.id)
		assert updated.bid_score == 90.0
		assert updated.bid_recommendation == 'go'

	def test_update_nonexistent_returns_none(self, tmp_path):
		t = _tracker(tmp_path)
		result = t.update('no-such-id', bid_score=50.0)
		assert result is None

	def test_add_explicit_record(self, tmp_path):
		t = _tracker(tmp_path)
		r = RFPRecord(title='Explicit', issuer='Gov', summary='Direct add')
		t.add(r)
		assert t.get(r.id) is not None


# ── FSM transitions ───────────────────────────────────────────────────────────

class TestRFPFSM:
	def test_valid_chain(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		for step in ('evaluating', 'awaiting_strategy', 'responding', 'in_review', 'submitted', 'won'):
			t.advance_status(r.id, step)
		assert t.get(r.id).status == RFPStatus.WON

	def test_no_bid_from_discovered(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		t.advance_status(r.id, 'no_bid')
		assert t.get(r.id).status == RFPStatus.NO_BID

	def test_invalid_transition_raises(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		with pytest.raises(ValueError, match='Invalid transition'):
			t.advance_status(r.id, 'submitted')

	def test_terminal_states_have_no_exits(self, tmp_path):
		for terminal in (RFPStatus.WON, RFPStatus.LOST, RFPStatus.NO_BID):
			assert _TRANSITIONS[terminal] == []

	def test_in_review_can_go_back_to_responding(self, tmp_path):
		t = _tracker(tmp_path)
		r = _minimal(t)
		for step in ('evaluating', 'awaiting_strategy', 'responding', 'in_review'):
			t.advance_status(r.id, step)
		t.advance_status(r.id, 'responding')
		assert t.get(r.id).status == RFPStatus.RESPONDING

	def test_advance_nonexistent_returns_none(self, tmp_path):
		t = _tracker(tmp_path)
		result = t.advance_status('no-such-id', 'evaluating')
		assert result is None


# ── JSON persistence ──────────────────────────────────────────────────────────

class TestRFPPersistence:
	def test_persist_and_reload(self, tmp_path):
		store = tmp_path / 'rfp.json'
		t1 = RFPTracker(store_path=store)
		r = t1.create(title='Persist Test', issuer='Gov', summary='check')
		t1.advance_status(r.id, 'evaluating')

		# fresh instance loads from same path
		t2 = RFPTracker(store_path=store)
		loaded = t2.get(r.id)
		assert loaded is not None
		assert loaded.title == 'Persist Test'
		assert loaded.status == RFPStatus.EVALUATING

	def test_store_is_valid_json(self, tmp_path):
		store = tmp_path / 'rfp.json'
		t = RFPTracker(store_path=store)
		t.create(title='T', issuer='I', summary='S')
		data = json.loads(store.read_text())
		assert isinstance(data, list)
		assert data[0]['title'] == 'T'

	def test_corrupt_store_ignored(self, tmp_path):
		store = tmp_path / 'rfp.json'
		store.write_text('not-valid-json')
		t = RFPTracker(store_path=store)
		assert t.all() == []

	def test_missing_store_starts_empty(self, tmp_path):
		t = RFPTracker(store_path=tmp_path / 'nonexistent.json')
		assert t.all() == []

	def test_multiple_records_persist(self, tmp_path):
		store = tmp_path / 'rfp.json'
		t1 = RFPTracker(store_path=store)
		for i in range(5):
			t1.create(title=f'RFP {i}', issuer='Corp', summary=f'Summary {i}')

		t2 = RFPTracker(store_path=store)
		assert len(t2.all()) == 5

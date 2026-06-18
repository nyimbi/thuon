# tests/ci/test_rfp_tracker.py
"""
Unit tests for RFPTracker and RFPRecord.
Uses tmp_path for real JSON persistence — no mocks.
"""
from __future__ import annotations

import json

import pytest

from core.rfp_tracker import RFPRecord, RFPStatus, RFPTracker


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path):
	return RFPTracker(store_path=tmp_path / 'rfps.json')


# ── RFPRecord ─────────────────────────────────────────────────────────────────

def test_record_gets_auto_id():
	r = RFPRecord(title='Test RFP', issuer='Acme', summary='Do stuff')
	assert r.id
	assert len(r.id) > 8


def test_record_default_status_is_discovered():
	r = RFPRecord(title='Test', issuer='X', summary='Y')
	assert r.status == RFPStatus.DISCOVERED


def test_record_to_dict_roundtrip():
	r = RFPRecord(title='DRFP', issuer='Gov', summary='Build a bridge',
	              deadline='2026-09-30', bid_score=72.5)
	d = r.to_dict()
	assert d['title'] == 'DRFP'
	assert d['bid_score'] == 72.5
	assert d['status'] == 'discovered'

	r2 = RFPRecord.from_dict(d)
	assert r2.id == r.id
	assert r2.bid_score == 72.5
	assert r2.status == RFPStatus.DISCOVERED


def test_record_status_coerced_from_string():
	r = RFPRecord(title='X', issuer='Y', summary='Z', status='evaluating')
	assert r.status == RFPStatus.EVALUATING


# ── RFPTracker.create / get ───────────────────────────────────────────────────

def test_create_returns_record(tracker):
	rec = tracker.create(title='Cloud Infra', issuer='Ministry', summary='Cloud migration')
	assert isinstance(rec, RFPRecord)
	assert rec.title == 'Cloud Infra'


def test_get_returns_created_record(tracker):
	rec = tracker.create(title='AI Platform', issuer='NatBank', summary='ML pipeline')
	fetched = tracker.get(rec.id)
	assert fetched is not None
	assert fetched.title == 'AI Platform'


def test_get_unknown_id_returns_none(tracker):
	assert tracker.get('nonexistent-id') is None


# ── RFPTracker.all ────────────────────────────────────────────────────────────

def test_all_returns_list(tracker):
	tracker.create(title='A', issuer='X', summary='s')
	tracker.create(title='B', issuer='Y', summary='s')
	assert len(tracker.all()) == 2


def test_all_filters_by_status(tracker):
	r1 = tracker.create(title='A', issuer='X', summary='s')
	r2 = tracker.create(title='B', issuer='Y', summary='s')
	tracker.advance_status(r2.id, RFPStatus.EVALUATING)

	discovered = tracker.all(status='discovered')
	evaluating = tracker.all(status='evaluating')
	assert len(discovered) == 1
	assert discovered[0].id == r1.id
	assert len(evaluating) == 1


def test_all_empty_tracker(tracker):
	assert tracker.all() == []


# ── RFPTracker.update ─────────────────────────────────────────────────────────

def test_update_modifies_fields(tracker):
	rec = tracker.create(title='Orig', issuer='X', summary='s')
	updated = tracker.update(rec.id, title='Updated', bid_score=85.0)
	assert updated.title == 'Updated'
	assert updated.bid_score == 85.0


def test_update_unknown_id_returns_none(tracker):
	assert tracker.update('bad-id', title='X') is None


def test_update_updated_at_changes(tracker):
	rec = tracker.create(title='T', issuer='X', summary='s')
	old_ts = rec.updated_at
	import time; time.sleep(0.01)
	updated = tracker.update(rec.id, title='T2')
	assert updated.updated_at != old_ts


# ── RFPTracker.advance_status ─────────────────────────────────────────────────

def test_advance_status_changes_status(tracker):
	rec = tracker.create(title='RFP1', issuer='X', summary='s')
	result = tracker.advance_status(rec.id, RFPStatus.EVALUATING)
	assert result.status == RFPStatus.EVALUATING


def test_advance_status_invalid_id_returns_none(tracker):
	assert tracker.advance_status('no-such-id', RFPStatus.SUBMITTED) is None


# ── Persistence ───────────────────────────────────────────────────────────────

def test_records_survive_reload(tmp_path):
	path = tmp_path / 'rfps.json'
	t1 = RFPTracker(store_path=path)
	rec = t1.create(title='Persist Test', issuer='Gov', summary='Should survive')

	t2 = RFPTracker(store_path=path)
	fetched = t2.get(rec.id)
	assert fetched is not None
	assert fetched.title == 'Persist Test'


def test_store_file_is_valid_json(tmp_path):
	path = tmp_path / 'rfps.json'
	t = RFPTracker(store_path=path)
	t.create(title='X', issuer='Y', summary='Z')
	data = json.loads(path.read_text())
	assert isinstance(data, list)
	assert data[0]['title'] == 'X'

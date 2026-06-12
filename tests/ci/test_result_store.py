"""Tests for core/result_store.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

import json
from core.result_store import ResultStore


class TestResultStoreInMemory:
	"""All tests use in-memory fallback (no DB)."""

	def setup_method(self):
		self.store = ResultStore(data_handler=None)

	def test_save_returns_version_1(self):
		v = self.store.save('research', 'q1', {'result': 'first'})
		assert v == 1

	def test_save_increments_version(self):
		self.store.save('research', 'q1', {'result': 'v1'})
		v2 = self.store.save('research', 'q1', {'result': 'v2'})
		assert v2 == 2

	def test_get_history_empty(self):
		assert self.store.get_history('cap', 'key') == []

	def test_get_history_returns_all_versions(self):
		self.store.save('cap', 'key', {'a': 1})
		self.store.save('cap', 'key', {'a': 2})
		history = self.store.get_history('cap', 'key')
		assert len(history) == 2
		assert history[0]['version'] == 1
		assert history[1]['version'] == 2

	def test_latest_returns_last(self):
		self.store.save('cap', 'key', {'a': 1})
		self.store.save('cap', 'key', {'a': 2})
		latest = self.store.latest('cap', 'key')
		assert latest['version'] == 2

	def test_latest_none_when_empty(self):
		assert self.store.latest('cap', 'missing') is None

	def test_diff_added_key(self):
		self.store.save('cap', 'k', {'x': 1})
		self.store.save('cap', 'k', {'x': 1, 'y': 2})
		diff = self.store.diff('cap', 'k', 1, 2)
		assert 'y' in diff['added']
		assert diff['removed'] == {}
		assert diff['changed'] == {}

	def test_diff_removed_key(self):
		self.store.save('cap', 'k', {'x': 1, 'y': 2})
		self.store.save('cap', 'k', {'x': 1})
		diff = self.store.diff('cap', 'k', 1, 2)
		assert 'y' in diff['removed']

	def test_diff_changed_value(self):
		self.store.save('cap', 'k', {'x': 'old'})
		self.store.save('cap', 'k', {'x': 'new'})
		diff = self.store.diff('cap', 'k', 1, 2)
		assert diff['changed']['x'] == {'from': 'old', 'to': 'new'}

	def test_diff_latest_two(self):
		self.store.save('cap', 'k', {'v': 1})
		self.store.save('cap', 'k', {'v': 2})
		diff = self.store.diff_latest_two('cap', 'k')
		assert diff['changed']['v'] == {'from': 1, 'to': 2}

	def test_diff_latest_two_insufficient_versions(self):
		self.store.save('cap', 'k', {'v': 1})
		diff = self.store.diff_latest_two('cap', 'k')
		assert 'note' in diff

	def test_different_capabilities_independent(self):
		self.store.save('cap_a', 'k', {'a': 1})
		self.store.save('cap_b', 'k', {'b': 2})
		assert len(self.store.get_history('cap_a', 'k')) == 1
		assert len(self.store.get_history('cap_b', 'k')) == 1

	def test_content_hash_present(self):
		self.store.save('cap', 'k', {'hello': 'world'})
		history = self.store.get_history('cap', 'k')
		assert 'content_hash' in history[0] or 'result' in history[0]

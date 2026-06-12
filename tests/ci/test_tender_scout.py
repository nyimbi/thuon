# tests/ci/test_tender_scout.py
"""Tests for capabilities/tender_scout.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock


def _make_scout(results=None):
	mock_search = MagicMock()
	mock_search.search.return_value = results or [
		{'title': 'ICT tender Kenya 2025', 'href': 'https://tenders.go.ke/ict-001',
		 'body': 'Government ICT procurement. Deadline: January 31, 2025'},
		{'title': 'IT services tender', 'href': 'https://example.com/tender',
		 'body': 'Technology services procurement Africa'},
	]
	from capabilities.tender_scout import TenderScout
	return TenderScout(mock_search), mock_search


class TestTenderScoutSearch:
	def test_returns_dict_with_status_ok(self):
		scout, _ = _make_scout()
		result = scout.search('ICT')
		assert result['status'] == 'ok'

	def test_results_list_present(self):
		scout, _ = _make_scout()
		result = scout.search('construction')
		assert 'results' in result
		assert isinstance(result['results'], list)

	def test_portal_match_detected(self):
		scout, _ = _make_scout([
			{'title': 'Kenya ICT tender', 'href': 'https://tenders.go.ke/ict-001',
			 'body': 'Government ICT'},
		])
		result = scout.search('ICT')
		portal_results = [r for r in result['results'] if r.get('is_portal_match')]
		assert len(portal_results) > 0

	def test_country_filter_limits_queries(self):
		scout, mock_search = _make_scout()
		scout.search('healthcare', countries=['Kenya', 'Nigeria'])
		assert mock_search.search.call_count >= 1

	def test_keyword_filter_used(self):
		scout, mock_search = _make_scout()
		scout.search('energy', keywords=['solar', 'renewable'])
		# At least one query should include the keyword
		all_queries = [call.args[0] for call in mock_search.search.call_args_list]
		assert any('solar' in q or 'renewable' in q for q in all_queries)

	def test_max_results_cap(self):
		many_results = [
			{'title': f'Tender {i}', 'href': f'https://example.com/{i}', 'body': 'content'}
			for i in range(50)
		]
		mock_search = MagicMock()
		mock_search.search.return_value = many_results
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(mock_search)
		result = scout.search('ICT', max_results=10)
		assert len(result['results']) <= 10

	def test_deduplication_prevents_duplicates(self):
		dup_results = [
			{'title': 'Same tender', 'href': 'https://example.com/same', 'body': 'content'},
			{'title': 'Same tender', 'href': 'https://example.com/same', 'body': 'content'},
		]
		mock_search = MagicMock()
		mock_search.search.return_value = dup_results
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(mock_search)
		result = scout.search('ICT')
		urls = [r['url'] for r in result['results']]
		assert len(urls) == len(set(urls))

	def test_search_engine_exception_handled(self):
		mock_search = MagicMock()
		mock_search.search.side_effect = Exception('network error')
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(mock_search)
		result = scout.search('ICT')
		assert result['status'] == 'ok'
		assert result['total_found'] == 0

	def test_searched_at_timestamp(self):
		scout, _ = _make_scout()
		result = scout.search('ICT')
		assert 'searched_at' in result

	def test_queries_run_count(self):
		scout, _ = _make_scout()
		result = scout.search('ICT')
		assert result['queries_run'] >= 1


class TestTenderScoutHelpers:
	def test_detect_country_from_domain(self):
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(MagicMock())
		country = scout._detect_country('https://tenders.go.ke/tender-001')
		assert country == 'Kenya'

	def test_detect_country_from_name(self):
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(MagicMock())
		country = scout._detect_country('Nigeria federal government procurement')
		assert country == 'Nigeria'

	def test_detect_country_unknown(self):
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(MagicMock())
		country = scout._detect_country('random content with no country info')
		assert country == 'Unknown'

	def test_extract_deadline_from_text(self):
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(MagicMock())
		deadline = scout._extract_deadline('Closing date: 15/03/2025. Submit all documents.')
		assert deadline is not None
		assert '2025' in deadline

	def test_extract_deadline_none_if_absent(self):
		from capabilities.tender_scout import TenderScout
		scout = TenderScout(MagicMock())
		deadline = scout._extract_deadline('No deadline information here.')
		assert deadline is None

	def test_all_portals_have_domains(self):
		from capabilities.tender_scout import _PORTALS
		for country, domains in _PORTALS.items():
			assert len(domains) > 0, f'{country} has no portal domains'

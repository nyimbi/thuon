"""
Tests for core/data_sources/* — all HTTP is mocked via unittest.mock.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

import json
from unittest.mock import patch, MagicMock


# ── Semantic Scholar ─────────────────────────────────────────────────────────

class TestSemanticScholar:
	def _mock_response(self, data):
		m = MagicMock()
		m.json.return_value = data
		m.raise_for_status.return_value = None
		return m

	def test_search_papers_returns_list(self):
		from core.data_sources.semantic_scholar import search_papers
		papers = [{'title': 'Test', 'authors': [], 'year': 2024, 'citationCount': 5, 'url': 'http://x'}]
		with patch('requests.get', return_value=self._mock_response({'data': papers})):
			result = search_papers('neural networks', limit=1)
		assert isinstance(result, list)
		assert result[0]['title'] == 'Test'

	def test_search_papers_empty_on_error(self):
		from core.data_sources.semantic_scholar import search_papers
		with patch('requests.get', side_effect=Exception('timeout')):
			result = search_papers('anything')
		assert result == []

	def test_get_citations_returns_list(self):
		from core.data_sources.semantic_scholar import get_citations
		citing = [{'citingPaper': {'title': 'Citing Paper', 'year': 2024}}]
		with patch('requests.get', return_value=self._mock_response({'data': citing})):
			result = get_citations('abc123')
		assert result[0]['title'] == 'Citing Paper'

	def test_get_references_returns_list(self):
		from core.data_sources.semantic_scholar import get_references
		refs = [{'citedPaper': {'title': 'Ref Paper', 'year': 2020}}]
		with patch('requests.get', return_value=self._mock_response({'data': refs})):
			result = get_references('abc123')
		assert result[0]['title'] == 'Ref Paper'

	def test_format_papers_for_context(self):
		from core.data_sources.semantic_scholar import format_papers_for_context
		papers = [{
			'title': 'My Paper', 'year': 2023,
			'authors': [{'name': 'Alice'}],
			'citationCount': 10, 'url': 'http://ss',
			'abstract': 'Some abstract text.',
		}]
		text = format_papers_for_context(papers)
		assert 'My Paper' in text
		assert 'Alice' in text
		assert '2023' in text

	def test_format_papers_empty(self):
		from core.data_sources.semantic_scholar import format_papers_for_context
		assert format_papers_for_context([]) == ''


# ── arXiv ────────────────────────────────────────────────────────────────────

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Deep Learning Survey</title>
    <summary>A comprehensive survey of deep learning.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Bob Smith</name></author>
    <link type="text/html" href="https://arxiv.org/abs/2401.00001"/>
    <category term="cs.LG"/>
  </entry>
</feed>"""


class TestArxivClient:
	def test_search_returns_entries(self):
		from core.data_sources.arxiv_client import search
		m = MagicMock()
		m.text = _ARXIV_XML
		m.raise_for_status.return_value = None
		with patch('requests.get', return_value=m):
			result = search('deep learning', max_results=1)
		assert len(result) == 1
		assert result[0]['title'] == 'Deep Learning Survey'
		assert result[0]['published'] == '2024-01-15'
		assert 'Bob Smith' in result[0]['authors']

	def test_search_returns_empty_on_error(self):
		from core.data_sources.arxiv_client import search
		with patch('requests.get', side_effect=ConnectionError()):
			assert search('anything') == []

	def test_format_papers(self):
		from core.data_sources.arxiv_client import format_papers
		papers = [{'title': 'T', 'published': '2024-01', 'authors': ['A'], 'summary': 'S', 'url': 'U'}]
		text = format_papers(papers)
		assert 'T' in text and 'A' in text


# ── NVD ──────────────────────────────────────────────────────────────────────

_NVD_RESPONSE = {
	'vulnerabilities': [{
		'cve': {
			'id': 'CVE-2024-0001',
			'descriptions': [{'lang': 'en', 'value': 'Remote code execution in Foo.'}],
			'metrics': {
				'cvssMetricV31': [{
					'cvssData': {'baseScore': 9.8, 'baseSeverity': 'CRITICAL', 'vectorString': 'AV:N/AC:L'}
				}]
			},
			'published': '2024-01-10T00:00:00',
			'lastModified': '2024-01-12T00:00:00',
			'references': [{'url': 'https://example.com/advisory'}, {'url': 'https://example.com/patch'}],
		}
	}]
}


class TestNVD:
	def _mock(self, data):
		m = MagicMock()
		m.json.return_value = data
		m.raise_for_status.return_value = None
		return m

	def test_search_cves_returns_list(self):
		from core.data_sources.nvd import search_cves
		with patch('requests.get', return_value=self._mock(_NVD_RESPONSE)):
			result = search_cves('remote code execution')
		assert len(result) == 1
		assert result[0]['cve_id'] == 'CVE-2024-0001'
		assert result[0]['score'] == 9.8
		assert result[0]['severity'] == 'CRITICAL'

	def test_search_cves_empty_on_error(self):
		from core.data_sources.nvd import search_cves
		with patch('requests.get', side_effect=Exception('timeout')):
			assert search_cves('foo') == []

	def test_get_cve(self):
		from core.data_sources.nvd import get_cve
		with patch('requests.get', return_value=self._mock(_NVD_RESPONSE)):
			result = get_cve('CVE-2024-0001')
		assert result['cve_id'] == 'CVE-2024-0001'

	def test_patch_available_detection(self):
		from core.data_sources.nvd import search_cves
		with patch('requests.get', return_value=self._mock(_NVD_RESPONSE)):
			result = search_cves()
		assert result[0]['patch_available'] is True

	def test_format_cves_for_context(self):
		from core.data_sources.nvd import search_cves, format_cves_for_context
		with patch('requests.get', return_value=self._mock(_NVD_RESPONSE)):
			cves = search_cves()
		text = format_cves_for_context(cves)
		assert 'CVE-2024-0001' in text
		assert 'CRITICAL' in text


# ── SEC EDGAR ────────────────────────────────────────────────────────────────

_EDGAR_SEARCH = {
	'hits': {'hits': [{
		'_source': {
			'entity_name': 'Acme Corp',
			'form_type': '10-K',
			'file_date': '2024-03-01',
			'entity_id': '0001234567',
		}
	}]}
}

_EDGAR_FACTS = {
	'entityName': 'Acme Corp',
	'facts': {
		'us-gaap': {
			'Revenues': {
				'units': {
					'USD': [
						{'val': 50000000, 'end': '2023-12-31', 'form': '10-K'}
					]
				}
			}
		}
	}
}


class TestSECEdgar:
	def _mock(self, data):
		m = MagicMock()
		m.json.return_value = data
		m.raise_for_status.return_value = None
		return m

	def test_search_filings(self):
		from core.data_sources.sec_edgar import search_filings
		with patch('requests.get', return_value=self._mock(_EDGAR_SEARCH)):
			result = search_filings('Acme Corp')
		assert len(result) == 1
		assert result[0]['entity'] == 'Acme Corp'
		assert result[0]['cik'] == '0001234567'

	def test_search_company_cik(self):
		from core.data_sources.sec_edgar import search_company_cik
		with patch('requests.get', return_value=self._mock(_EDGAR_SEARCH)):
			cik = search_company_cik('Acme')
		assert cik == '0001234567'

	def test_get_company_facts(self):
		from core.data_sources.sec_edgar import get_company_facts
		with patch('requests.get', return_value=self._mock(_EDGAR_FACTS)):
			result = get_company_facts('1234567')
		assert result['entity'] == 'Acme Corp'
		assert 'Revenues' in result['metrics']
		assert result['metrics']['Revenues']['value'] == 50000000

	def test_search_filings_empty_on_error(self):
		from core.data_sources.sec_edgar import search_filings
		with patch('requests.get', side_effect=Exception('timeout')):
			assert search_filings('x') == []

	def test_format_financials(self):
		from core.data_sources.sec_edgar import get_company_facts, format_financials_for_context
		with patch('requests.get', return_value=self._mock(_EDGAR_FACTS)):
			facts = get_company_facts('1234567')
		text = format_financials_for_context(facts)
		assert 'Acme Corp' in text
		assert 'Revenues' in text

	def test_format_financials_empty(self):
		from core.data_sources.sec_edgar import format_financials_for_context
		assert 'No EDGAR' in format_financials_for_context({})


# ── Patents ──────────────────────────────────────────────────────────────────

_PATENT_RESPONSE = {
	'patents': [{
		'patent_id': 'US10000001',
		'patent_title': 'Widget Assembly Method',
		'patent_abstract': 'A method for assembling widgets.',
		'patent_date': '2023-06-15',
		'assignees': [{'assignee_organization': 'Widget Corp'}],
	}]
}


class TestPatents:
	def _mock(self, data):
		m = MagicMock()
		m.json.return_value = data
		m.raise_for_status.return_value = None
		return m

	def test_search_patents_returns_list(self):
		from core.data_sources.patents import search_patents
		with patch('requests.post', return_value=self._mock(_PATENT_RESPONSE)):
			result = search_patents('widget')
		assert len(result) == 1
		assert result[0]['patent_id'] == 'US10000001'

	def test_search_patents_empty_on_error(self):
		from core.data_sources.patents import search_patents
		with patch('requests.post', side_effect=Exception('timeout')):
			assert search_patents('foo') == []

	def test_format_patents_for_context(self):
		from core.data_sources.patents import search_patents, format_patents_for_context
		with patch('requests.post', return_value=self._mock(_PATENT_RESPONSE)):
			patents = search_patents('widget')
		text = format_patents_for_context(patents)
		assert 'Widget Assembly Method' in text
		assert 'Widget Corp' in text

	def test_format_empty(self):
		from core.data_sources.patents import format_patents_for_context
		assert format_patents_for_context([]) == ''


# ── OpenCorporates ────────────────────────────────────────────────────────────

_OC_RESPONSE = {
	'results': {
		'companies': [{
			'company': {
				'name': 'Acme Ltd',
				'jurisdiction_code': 'gb',
				'current_status': 'Active',
				'company_number': '12345678',
				'incorporation_date': '2010-01-01',
				'registered_address_in_full': '1 Main St, London',
				'company_type': 'Private limited company',
				'opencorporates_url': 'https://opencorporates.com/companies/gb/12345678',
			}
		}]
	}
}


class TestOpenCorporates:
	def _mock(self, data):
		m = MagicMock()
		m.json.return_value = data
		m.raise_for_status.return_value = None
		return m

	def test_search_company_returns_list(self):
		from core.data_sources.opencorporates import search_company
		with patch('requests.get', return_value=self._mock(_OC_RESPONSE)):
			result = search_company('Acme')
		assert len(result) == 1
		assert result[0]['name'] == 'Acme Ltd'
		assert result[0]['jurisdiction'] == 'gb'

	def test_search_company_empty_on_error(self):
		from core.data_sources.opencorporates import search_company
		with patch('requests.get', side_effect=Exception('timeout')):
			assert search_company('x') == []

	def test_format_companies_for_context(self):
		from core.data_sources.opencorporates import search_company, format_companies_for_context
		with patch('requests.get', return_value=self._mock(_OC_RESPONSE)):
			companies = search_company('Acme')
		text = format_companies_for_context(companies)
		assert 'Acme Ltd' in text
		assert 'GB' in text

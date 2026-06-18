# tests/ci/test_rfp_capabilities.py
"""
Unit tests for RFP atomic capabilities.
All LLM calls are mocked — tests verify routing, param handling, output shape.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ai(response: str = '') -> MagicMock:
	m = MagicMock()
	m.generate_text.return_value = response
	return m


_INGESTER_JSON = json.dumps({
	'title': 'Cloud Services Procurement',
	'issuer': 'Ministry of ICT',
	'deadline': '2026-09-30',
	'scope_summary': 'Procurement of cloud hosting services.',
	'evaluation_criteria': [{'criterion': 'Technical', 'weight_pct': 60, 'description': ''}],
	'requirements': [{'req_id': 'R1', 'text': 'Must be ISO 27001', 'type': 'shall', 'section': '3.1'}],
	'page_limits': {'total': 50},
	'budget': 'KES 10M',
	'attachments_required': ['Form A', 'Insurance cert'],
})

_BID_JSON = json.dumps({
	'bid_score': 78,
	'bid_recommendation': 'go',
	'disqualifiers': [],
	'risks': ['tight timeline'],
	'rationale': 'Strong fit with capabilities.',
	'estimated_win_probability': 0.45,
	'scoring_breakdown': {},
})

_SECTION_JSON = json.dumps({
	'content': 'Our technical approach leverages cloud-native...',
	'word_count': 350,
	'requirements_addressed': ['R1', 'R2'],
	'placeholders': [],
})

_STRATEGY_JSON = json.dumps({
	'win_themes': [{'theme': 'Local expertise', 'headline': 'We know Kenya', 'proof_points': [], 'ghosting_angle': ''}],
	'solution_outline': 'Phased migration approach.',
	'executive_summary_blueprint': 'Start with compliance.',
})


# ── RFPIngester ───────────────────────────────────────────────────────────────

class TestRFPIngester:
	def test_ingest_text_returns_required_keys(self):
		from capabilities.rfp_ingester import RFPIngester
		cap = RFPIngester(_ai(_INGESTER_JSON))
		result = cap.ingest('This is raw RFP text describing procurement needs...')
		assert 'title' in result
		assert 'issuer' in result
		assert 'requirements' in result
		assert 'scope_summary' in result

	def test_ingest_calls_llm(self):
		from capabilities.rfp_ingester import RFPIngester
		ai = _ai(_INGESTER_JSON)
		cap = RFPIngester(ai)
		cap.ingest('RFP text here')
		ai.generate_text.assert_called_once()

	def test_ingest_invalid_json_returns_raw_text(self):
		from capabilities.rfp_ingester import RFPIngester
		cap = RFPIngester(_ai('not valid json at all'))
		result = cap.ingest('Some RFP text')
		assert isinstance(result, dict)
		assert 'raw_text' in result or 'title' in result

	def test_ingest_url_fetches_content(self):
		from capabilities.rfp_ingester import RFPIngester
		ai = _ai(_INGESTER_JSON)
		mock_resp = MagicMock()
		mock_resp.text = '<html><body>RFP content for cloud services</body></html>'
		mock_resp.raise_for_status = MagicMock()
		# trafilatura is tried first — return None so requests fallback runs
		with patch('trafilatura.fetch_url', return_value=None), \
		     patch('requests.get', return_value=mock_resp):
			cap = RFPIngester(ai)
			result = cap.ingest('https://example.gov/rfp/12345')
		assert isinstance(result, dict)


# ── RFPBidEvaluator ───────────────────────────────────────────────────────────

class TestRFPBidEvaluator:
	def test_evaluate_returns_required_keys(self):
		from capabilities.rfp_bid_evaluator import RFPBidEvaluator
		cap = RFPBidEvaluator(_ai(_BID_JSON))
		result = cap.evaluate(scope_summary='Cloud migration for Ministry of ICT')
		assert 'bid_score' in result
		assert 'bid_recommendation' in result

	def test_evaluate_calls_llm(self):
		from capabilities.rfp_bid_evaluator import RFPBidEvaluator
		ai = _ai(_BID_JSON)
		cap = RFPBidEvaluator(ai)
		cap.evaluate(scope_summary='Some scope')
		ai.generate_text.assert_called_once()

	def test_evaluate_go_recommendation(self):
		from capabilities.rfp_bid_evaluator import RFPBidEvaluator
		cap = RFPBidEvaluator(_ai(_BID_JSON))
		result = cap.evaluate(scope_summary='Good fit', budget='KES 10M')
		assert result['bid_recommendation'] in ('go', 'no-go', 'conditional')

	def test_evaluate_invalid_llm_json_does_not_raise(self):
		from capabilities.rfp_bid_evaluator import RFPBidEvaluator
		cap = RFPBidEvaluator(_ai('broken json'))
		# Capability may return None on parse failure — that is acceptable;
		# it must not raise an exception.
		result = cap.evaluate(scope_summary='Scope')
		assert result is None or isinstance(result, dict)


# ── RFPSectionWriter ──────────────────────────────────────────────────────────

class TestRFPSectionWriter:
	def test_write_section_returns_content(self):
		from capabilities.rfp_section_writer import RFPSectionWriter
		cap = RFPSectionWriter(_ai(_SECTION_JSON))
		result = cap.write_section(
			section_name='technical_approach',
			requirements=['R1: Must be ISO 27001'],
			win_themes=['Local expertise'],
		)
		assert 'content' in result
		assert isinstance(result['content'], str)

	def test_write_section_calls_llm(self):
		from capabilities.rfp_section_writer import RFPSectionWriter
		ai = _ai(_SECTION_JSON)
		cap = RFPSectionWriter(ai)
		cap.write_section(section_name='executive_summary')
		ai.generate_text.assert_called_once()


# ── RFPWinStrategyBuilder ─────────────────────────────────────────────────────

class TestRFPWinStrategyBuilder:
	def test_build_returns_win_themes(self):
		from capabilities.rfp_win_strategy_builder import RFPWinStrategyBuilder
		cap = RFPWinStrategyBuilder(_ai(_STRATEGY_JSON))
		result = cap.build_strategy(
			evaluation_criteria=[{'criterion': 'Technical', 'weight_pct': 60}],
			customer_research='Ministry values local talent.',
			competitor_analysis='Incumbent is Telkom Kenya.',
		)
		assert 'win_themes' in result
		assert isinstance(result['win_themes'], list)


# ── RFPConsistencyChecker ─────────────────────────────────────────────────────

class TestRFPConsistencyChecker:
	def test_check_returns_issues_and_coverage(self):
		from capabilities.rfp_consistency_checker import RFPConsistencyChecker
		llm_json = json.dumps({
			'issues': [],
			'coverage_pct': 95,
			'uncovered_requirements': [],
		})
		cap = RFPConsistencyChecker(_ai(llm_json))
		result = cap.check(
			sections={'executive_summary': {'content': 'We will...'}},
			compliance_matrix=[{'req_id': 'R1', 'text': 'ISO 27001'}],
		)
		assert 'coverage_pct' in result or 'issues' in result

# tests/ci/test_contract_renegotiator.py
"""Tests for capabilities/contract_renegotiator.py"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock


def _make_renegotiator(ai_response=None):
	mock_ai = MagicMock()
	mock_ai.generate_text.return_value = ai_response or json.dumps({
		'renewal_date': '2025-12-01', 'notice_period_days': 30,
		'auto_renewal': True, 'price_escalation_clause': '5% annual CPI',
		'sla_commitments': ['99.9% uptime'], 'negotiation_leverage': ['competitor pricing'],
		'recommended_tactics': ['request multi-year discount'], 'risk_of_staying': 'low',
		'estimated_savings_percent': 20,
	})
	from capabilities.contract_renegotiator import ContractRenegotiator
	return ContractRenegotiator(mock_ai), mock_ai


class TestAnalyzeContract:
	def test_returns_dict_with_status_ok(self):
		renegotiator, _ = _make_renegotiator()
		result = renegotiator.analyze_contract('Service Agreement: Term 12 months...', vendor='AWS')
		assert result['status'] == 'ok'

	def test_vendor_added_to_result(self):
		renegotiator, _ = _make_renegotiator()
		result = renegotiator.analyze_contract('contract text', vendor='Slack')
		assert result['vendor'] == 'Slack'

	def test_category_discount_ceiling(self):
		renegotiator, _ = _make_renegotiator()
		result = renegotiator.analyze_contract('contract', category='saas')
		assert result['estimated_discount_ceiling'] == '25%'

	def test_utilties_low_discount(self):
		renegotiator, _ = _make_renegotiator()
		result = renegotiator.analyze_contract('contract', category='utilities')
		assert result['estimated_discount_ceiling'] == '5%'

	def test_contract_text_truncated_in_prompt(self):
		renegotiator, mock_ai = _make_renegotiator()
		long_contract = 'clause ' * 5000
		renegotiator.analyze_contract(long_contract, vendor='X')
		prompt = mock_ai.generate_text.call_args[0][0]
		# Confirm prompt doesn't exceed reasonable limit
		assert len(prompt) < 10000

	def test_bad_json_response_handled(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = 'not json'
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(mock_ai)
		result = renegotiator.analyze_contract('text')
		assert 'raw_response' in result or result.get('status') == 'ok'

	def test_market_context_injected_when_search_available(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = json.dumps({'renewal_date': None})
		mock_search = MagicMock()
		mock_search.search.return_value = [{'body': 'competitor pricing info'}]
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(mock_ai, search_engine=mock_search)
		renegotiator.analyze_contract('text', vendor='AWS', category='cloud')
		prompt = mock_ai.generate_text.call_args[0][0]
		assert 'competitor pricing info' in prompt


class TestDraftEmail:
	def test_discount_email_fields(self):
		renegotiator, mock_ai = _make_renegotiator(json.dumps({
			'subject': 'Discount Request', 'body': 'Dear AWS...', 'tone': 'professional',
			'key_points': ['loyal customer', 'competitor pricing'],
		}))
		result = renegotiator.draft_email('AWS', 5000.0, email_type='discount')
		assert result['status'] == 'ok'
		assert result['vendor'] == 'AWS'
		assert result['current_price'] == 5000.0
		assert result['target_price'] < 5000.0

	def test_cancel_email_type(self):
		renegotiator, mock_ai = _make_renegotiator(json.dumps({
			'subject': 'Cancellation Notice', 'body': 'We are cancelling...', 'tone': 'firm',
			'key_points': ['cost optimization'],
		}))
		result = renegotiator.draft_email('Netflix', 1500.0, email_type='cancel')
		assert result['email_type'] == 'cancel'

	def test_price_match_email_type(self):
		renegotiator, _ = _make_renegotiator(json.dumps({
			'subject': 'Price Match Request', 'body': '...', 'tone': 'professional',
			'key_points': [],
		}))
		result = renegotiator.draft_email('Slack', 10000.0, email_type='price_match')
		assert result['email_type'] == 'price_match'

	def test_potential_savings_computed(self):
		renegotiator, _ = _make_renegotiator(json.dumps({
			'subject': 'X', 'body': 'Y', 'tone': 'firm', 'key_points': [],
		}))
		result = renegotiator.draft_email('AWS', 10000.0, email_type='discount')
		assert result['potential_savings_monthly'] > 0
		assert result['target_price'] < result['current_price']

	def test_vendor_category_detection(self):
		renegotiator, _ = _make_renegotiator(json.dumps({'subject': 'X', 'body': 'Y', 'tone': 'X', 'key_points': []}))
		# AWS → cloud category → 20% discount ceiling
		result = renegotiator.draft_email('AWS Cloud Services', 10000.0)
		# cloud discount = 20%, target = 8000
		assert abs(result['target_price'] - 8000.0) < 1


class TestAnalyzePortfolio:
	def test_returns_totals(self):
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(MagicMock())
		subs = [
			{'vendor': 'AWS', 'monthly_cost': 50000, 'currency': 'KES', 'category': 'cloud'},
			{'vendor': 'Slack', 'monthly_cost': 10000, 'currency': 'KES', 'category': 'saas'},
			{'vendor': 'Netflix', 'monthly_cost': 1500, 'currency': 'KES', 'category': 'streaming'},
		]
		result = renegotiator.analyze_portfolio(subs)
		assert result['status'] == 'ok'
		assert result['total_monthly_spend'] == 61500
		assert result['total_annual_spend'] == 61500 * 12

	def test_opportunities_sorted_by_savings(self):
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(MagicMock())
		subs = [
			{'vendor': 'Cheap', 'monthly_cost': 100, 'category': 'saas'},
			{'vendor': 'Expensive', 'monthly_cost': 50000, 'category': 'cloud'},
		]
		result = renegotiator.analyze_portfolio(subs)
		# Most expensive should be first
		assert result['opportunities'][0]['vendor'] == 'Expensive'

	def test_high_priority_threshold(self):
		from capabilities.contract_renegotiator import ContractRenegotiator, _CATEGORY_DISCOUNT
		renegotiator = ContractRenegotiator(MagicMock())
		# cloud at 20% discount: 50000 * 0.20 = 10000 > 500 → high
		subs = [{'vendor': 'AWS', 'monthly_cost': 50000, 'category': 'cloud'}]
		result = renegotiator.analyze_portfolio(subs)
		assert result['opportunities'][0]['priority'] == 'high'

	def test_savings_rate_string(self):
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(MagicMock())
		subs = [{'vendor': 'X', 'monthly_cost': 10000, 'category': 'saas'}]
		result = renegotiator.analyze_portfolio(subs)
		assert result['savings_rate'].endswith('%')

	def test_empty_portfolio(self):
		from capabilities.contract_renegotiator import ContractRenegotiator
		renegotiator = ContractRenegotiator(MagicMock())
		result = renegotiator.analyze_portfolio([])
		assert result['total_monthly_spend'] == 0
		assert result['opportunities'] == []

# tests/ci/test_receipt_analyzer.py
"""Tests for capabilities/receipt_analyzer.py"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock, patch


def _make_analyzer():
	mock_vision = MagicMock()
	with patch('core.ai_engine.OllamaVisionModel', return_value=mock_vision):
		from capabilities.receipt_analyzer import ReceiptAnalyzer
		analyzer = ReceiptAnalyzer()
	analyzer._vision = mock_vision
	return analyzer, mock_vision


class TestReceiptAnalyzerAnalyze:
	def test_returns_dict_with_status_ok(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'Naivas Supermarket', 'date': '2025-06-12',
			'total': 1250.50, 'currency': 'KES', 'tax': 0,
			'payment_method': 'mpesa', 'category': 'food',
			'items': [{'name': 'Milk', 'quantity': 2, 'unit_price': 75, 'total_price': 150}],
			'confidence': 'high', 'notes': '',
		})
		result = analyzer.analyze('/tmp/receipt.jpg')
		assert result['status'] == 'ok'
		assert result['vendor'] == 'Naivas Supermarket'

	def test_normalizes_total_to_float(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'Shop', 'total': '1,234.50', 'currency': 'KES',
			'date': None, 'tax': 0, 'payment_method': 'cash',
			'items': [], 'category': 'shopping', 'confidence': 'medium', 'notes': '',
		})
		result = analyzer.analyze('/tmp/r.png')
		assert result['total'] == 1234.50

	def test_normalizes_date_format(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'Shop', 'date': '12/06/2025', 'total': 500,
			'currency': 'KES', 'tax': 0, 'payment_method': 'cash',
			'items': [], 'category': 'food', 'confidence': 'high', 'notes': '',
		})
		result = analyzer.analyze('/tmp/r.png')
		assert result['date'] == '2025-06-12'

	def test_image_path_added_to_result(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'X', 'date': None, 'total': 0, 'currency': 'KES',
			'tax': 0, 'payment_method': 'cash', 'items': [],
			'category': 'other', 'confidence': 'low', 'notes': '',
		})
		result = analyzer.analyze('/tmp/test_receipt.png')
		assert result['image_path'] == '/tmp/test_receipt.png'

	def test_analyzed_at_timestamp_present(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'X', 'date': None, 'total': 0, 'currency': 'KES',
			'tax': 0, 'payment_method': 'cash', 'items': [],
			'category': 'other', 'confidence': 'low', 'notes': '',
		})
		result = analyzer.analyze('/tmp/r.png')
		assert 'analyzed_at' in result

	def test_parse_failed_on_bad_json(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = 'not json at all'
		result = analyzer.analyze('/tmp/r.png')
		assert result['status'] == 'parse_failed' or result.get('raw_text') is not None

	def test_analyze_batch_processes_all(self):
		analyzer, mock_vision = _make_analyzer()
		mock_vision.analyze_image.return_value = json.dumps({
			'vendor': 'Shop', 'date': None, 'total': 100, 'currency': 'KES',
			'tax': 0, 'payment_method': 'cash', 'items': [],
			'category': 'food', 'confidence': 'high', 'notes': '',
		})
		results = analyzer.analyze_batch(['/tmp/a.png', '/tmp/b.png', '/tmp/c.png'])
		assert len(results) == 3


class TestReceiptAnalyzerToTransaction:
	def test_converts_to_transaction_format(self):
		analyzer, _ = _make_analyzer()
		receipt = {
			'vendor': 'Java House', 'date': '2025-06-12',
			'total': 850.0, 'currency': 'KES', 'tax': 0,
			'payment_method': 'card', 'category': 'food', 'items': [],
		}
		tx = analyzer.to_transaction(receipt)
		assert tx['amount'] == 850.0
		assert tx['currency'] == 'KES'
		assert tx['category'] == 'food'
		assert tx['source'] == 'receipt_ocr'
		assert 'Java House' in tx['description']

	def test_defaults_currency_to_kes(self):
		analyzer, _ = _make_analyzer()
		tx = analyzer.to_transaction({'vendor': 'X', 'total': 100})
		assert tx['currency'] == 'KES'


class TestDateNormalization:
	def test_iso_format_unchanged(self):
		from capabilities.receipt_analyzer import ReceiptAnalyzer
		with patch('core.ai_engine.OllamaVisionModel'):
			analyzer = ReceiptAnalyzer()
		result = analyzer._normalize_date('2025-01-15')
		assert result == '2025-01-15'

	def test_slash_format_dmy(self):
		from capabilities.receipt_analyzer import ReceiptAnalyzer
		with patch('core.ai_engine.OllamaVisionModel'):
			analyzer = ReceiptAnalyzer()
		result = analyzer._normalize_date('15/01/2025')
		assert result == '2025-01-15'

	def test_long_month_name(self):
		from capabilities.receipt_analyzer import ReceiptAnalyzer
		with patch('core.ai_engine.OllamaVisionModel'):
			analyzer = ReceiptAnalyzer()
		result = analyzer._normalize_date('January 15, 2025')
		assert result == '2025-01-15'

	def test_unknown_format_returns_original(self):
		from capabilities.receipt_analyzer import ReceiptAnalyzer
		with patch('core.ai_engine.OllamaVisionModel'):
			analyzer = ReceiptAnalyzer()
		result = analyzer._normalize_date('weird-date-format')
		assert result == 'weird-date-format'

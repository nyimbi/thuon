# capabilities/receipt_analyzer.py
"""
Receipt and invoice OCR + structured data extraction.
Uses OllamaVisionModel to parse receipt images and return transaction-ready data.
"""

from __future__ import annotations
import json
import re
from datetime import datetime


_DATE_FORMATS = (
	'%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
	'%B %d, %Y', '%d %b %Y', '%b %d %Y',
)

_RECEIPT_PROMPT = (
	'This is a receipt or invoice image. Extract all transaction data precisely.\n\n'
	'Return JSON with these exact keys:\n'
	'- vendor: store/restaurant/service name\n'
	'- date: ISO format YYYY-MM-DD (null if not visible)\n'
	'- total: numeric total amount, no currency symbol\n'
	'- currency: 3-letter ISO code (KES, USD, GBP, EUR, etc.)\n'
	'- tax: numeric tax amount (0 if not shown)\n'
	'- payment_method: cash | card | mpesa | bank_transfer | unknown\n'
	'- items: list of {name, quantity, unit_price, total_price}\n'
	'- category: food | transport | utilities | entertainment | health | shopping | services | other\n'
	'- confidence: high | medium | low (based on image clarity)\n'
	'- notes: any important observations\n\n'
	'Return ONLY the JSON object, no other text.'
)


class ReceiptAnalyzer:
	def __init__(self, ai_engine=None):
		self.ai_engine = ai_engine
		from core.ai_engine import OllamaVisionModel
		self._vision = OllamaVisionModel()

	def analyze(self, image_path: str) -> dict:
		"""
		Extract structured data from a receipt/invoice image.

		Returns dict with: vendor, date, total, currency, tax, payment_method,
		items, category, confidence, notes, image_path, analyzed_at, status.
		"""
		raw = self._vision.analyze_image(image_path, _RECEIPT_PROMPT)
		data = self._parse_json(raw)

		if data.get('date'):
			data['date'] = self._normalize_date(str(data['date']))
		if 'total' in data:
			try:
				data['total'] = float(str(data['total']).replace(',', ''))
			except (ValueError, TypeError):
				pass
		if 'tax' in data:
			try:
				data['tax'] = float(str(data['tax']).replace(',', ''))
			except (ValueError, TypeError):
				data['tax'] = 0.0

		data['image_path']   = image_path
		data['analyzed_at']  = datetime.utcnow().isoformat()
		data['status']       = 'ok'
		return data

	def analyze_batch(self, image_paths: list[str]) -> list[dict]:
		return [self.analyze(p) for p in image_paths]

	def to_transaction(self, receipt: dict) -> dict:
		"""Convert analyzed receipt to a standard finance transaction dict."""
		return {
			'date':        receipt.get('date'),
			'description': f"Purchase at {receipt.get('vendor', 'Unknown')}",
			'amount':      receipt.get('total', 0),
			'currency':    receipt.get('currency', 'KES'),
			'category':    receipt.get('category', 'other'),
			'payment':     receipt.get('payment_method', 'unknown'),
			'source':      'receipt_ocr',
			'items':       receipt.get('items', []),
			'tax':         receipt.get('tax', 0),
		}

	def _parse_json(self, raw: str) -> dict:
		try:
			match = re.search(r'\{.*\}', raw, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'raw_text': raw, 'status': 'parse_failed'}

	def _normalize_date(self, date_str: str) -> str:
		for fmt in _DATE_FORMATS:
			try:
				return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
			except ValueError:
				continue
		return date_str

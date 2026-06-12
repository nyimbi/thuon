# capabilities/FinancialAccountant.py

import json
import re
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


class FinancialAccountant:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def create_invoice(self, customer_id: str, invoice_items: list, invoice_date: str, due_date: str) -> dict:
		items_str = json.dumps(invoice_items, indent=2)
		prompt = (
			f"You are a financial accountant. Generate a detailed invoice.\n\n"
			f"Customer ID: {customer_id}\nInvoice Date: {invoice_date}\nDue Date: {due_date}\n"
			f"Items:\n{items_str}\n\n"
			f"Return JSON with keys: invoice_number (generate one), customer_id, invoice_date, due_date, "
			f"line_items (list with: description, quantity, unit_price, tax_rate, line_total), "
			f"subtotal, tax_amount, discount_amount, total_amount, currency, "
			f"payment_terms, payment_methods_accepted (list), "
			f"late_payment_penalty_percent, accounting_codes (list with: code, amount, description), "
			f"notes, status."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				invoice = json.loads(match.group())
				if self.data_handler:
					try:
						self.data_handler.insert_data('invoices', {
							'customer_id': customer_id,
							'invoice_date': invoice_date,
							'due_date': due_date,
							'total_amount': invoice.get('total_amount', 0),
							'status': invoice.get('status', 'pending'),
						})
					except Exception:
						pass
				return invoice
		except Exception:
			pass
		return {'customer_id': customer_id, 'invoice_date': invoice_date, 'due_date': due_date, 'result': response, 'status': 'success'}

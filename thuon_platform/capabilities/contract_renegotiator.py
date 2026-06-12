# capabilities/contract_renegotiator.py
"""
Contract/subscription renegotiation analyzer.
Analyzes contract text and subscription portfolios to surface renewal intelligence,
negotiation leverage, and draft negotiation/cancellation emails.
"""

from __future__ import annotations
import json
import re


_CATEGORY_DISCOUNT = {
	'saas':        0.25,
	'telecom':     0.20,
	'insurance':   0.15,
	'cloud':       0.20,
	'streaming':   0.10,
	'gym':         0.30,
	'software':    0.25,
	'office':      0.15,
	'utilities':   0.05,
	'other':       0.10,
}

_VENDOR_CATEGORY: dict[str, str] = {
	'aws': 'cloud', 'azure': 'cloud', 'gcp': 'cloud', 'digitalocean': 'cloud',
	'slack': 'saas', 'notion': 'saas', 'salesforce': 'saas', 'hubspot': 'saas',
	'zoom': 'saas', 'asana': 'saas', 'monday': 'saas',
	'netflix': 'streaming', 'spotify': 'streaming', 'youtube': 'streaming',
	'safaricom': 'telecom', 'airtel': 'telecom', 'telkom': 'telecom',
	'microsoft': 'software', 'adobe': 'software', 'atlassian': 'software',
	'gym': 'gym', 'fitness': 'gym',
}


class ContractRenegotiator:
	def __init__(self, ai_engine, search_engine=None):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def analyze_contract(
		self,
		contract_text: str,
		vendor: str = '',
		category: str = 'other',
	) -> dict:
		"""
		Analyze contract text and return negotiation intelligence.

		Returns: renewal_date, notice_period_days, auto_renewal, price_escalation_clause,
		sla_commitments, negotiation_leverage, recommended_tactics, risk_of_staying,
		estimated_savings_percent, estimated_discount_ceiling.
		"""
		market_ctx = self._market_context(vendor, category) if self.search_engine else ''
		discount = _CATEGORY_DISCOUNT.get(category.lower(), 0.10)

		prompt = (
			f'You are a contract negotiation expert. Analyze this contract carefully.\n\n'
			f'Identify:\n'
			f'1. Renewal and termination clauses with exact notice periods\n'
			f'2. Price escalation or auto-renewal provisions\n'
			f'3. SLA commitments and penalty clauses\n'
			f'4. Negotiation leverage (switching costs, alternatives)\n'
			f'5. Recommended tactics for {vendor or "this vendor"} in the {category} category\n\n'
			+ (f'Market context: {market_ctx}\n\n' if market_ctx else '')
			+ f'Contract (first 4000 chars):\n{contract_text[:4000]}\n\n'
			f'Return JSON with keys: renewal_date (YYYY-MM-DD or null), '
			f'notice_period_days (int), auto_renewal (bool), '
			f'price_escalation_clause (string or null), '
			f'sla_commitments (list of strings), '
			f'negotiation_leverage (list of strings), '
			f'recommended_tactics (list of strings), '
			f'risk_of_staying (low|medium|high), '
			f'estimated_savings_percent (int).\n\nJSON:'
		)
		raw = self.ai_engine.generate_text(prompt)
		result = self._parse_json(raw)
		result['vendor']                    = vendor
		result['category']                  = category
		result['estimated_discount_ceiling'] = f'{int(discount * 100)}%'
		result['status']                    = 'ok'
		return result

	def draft_email(
		self,
		vendor: str,
		current_price: float,
		email_type: str = 'discount',
		currency: str = 'KES',
		context: str = '',
	) -> dict:
		"""
		Draft a negotiation, cancellation, or price-match email.

		Args:
			vendor:        Vendor name
			current_price: Current monthly cost
			email_type:    'discount' | 'cancel' | 'price_match'
			currency:      3-letter currency code
			context:       Additional context for the LLM
		"""
		category = self._guess_category(vendor)
		discount = _CATEGORY_DISCOUNT.get(category, 0.15)
		target   = current_price * (1 - discount)

		prompts = {
			'discount': (
				f'Write a professional email to {vendor} requesting a '
				f'{int(discount*100)}% discount on our current subscription of '
				f'{currency} {current_price:.2f}/month. We are a loyal customer. '
				f'Mention that competitors offer comparable pricing. Be firm but polite.'
			),
			'cancel': (
				f'Write a professional cancellation notice to {vendor} for our '
				f'{currency} {current_price:.2f}/month subscription. Cite cost '
				f'optimization. Leave door open for a retention counter-offer.'
			),
			'price_match': (
				f'Write a price match request to {vendor}. We pay {currency} '
				f'{current_price:.2f}/month but found a comparable alternative at '
				f'{currency} {target:.2f}/month. Request they match the lower price.'
			),
		}
		prompt = (
			prompts.get(email_type, prompts['discount'])
			+ (f'\nAdditional context: {context}' if context else '')
			+ '\n\nReturn JSON with keys: subject, body, tone, key_points (list of strings).'
		)
		raw = self.ai_engine.generate_text(prompt)
		result = self._parse_json(raw)
		result.update({
			'email_type':                email_type,
			'vendor':                    vendor,
			'current_price':             current_price,
			'target_price':              round(target, 2),
			'potential_savings_monthly': round(current_price - target, 2),
			'currency':                  currency,
			'status':                    'ok',
		})
		return result

	def analyze_portfolio(self, subscriptions: list[dict]) -> dict:
		"""
		Prioritize renegotiation targets across a subscription portfolio.

		Each subscription dict: {vendor, monthly_cost, currency, category, renewal_date (optional)}
		"""
		total_monthly = sum(float(s.get('monthly_cost', 0)) for s in subscriptions)
		opportunities = []

		for sub in subscriptions:
			cat      = sub.get('category', 'other').lower()
			discount = _CATEGORY_DISCOUNT.get(cat, 0.10)
			cost     = float(sub.get('monthly_cost', 0))
			savings  = cost * discount
			opportunities.append({
				**sub,
				'potential_monthly_savings': round(savings, 2),
				'potential_annual_savings':  round(savings * 12, 2),
				'discount_ceiling_pct':      int(discount * 100),
				'priority':                  'high' if savings > 500 else ('medium' if savings > 100 else 'low'),
			})

		opportunities.sort(key=lambda x: -x['potential_annual_savings'])
		total_potential = sum(o['potential_annual_savings'] for o in opportunities)

		return {
			'total_monthly_spend':          round(total_monthly, 2),
			'total_annual_spend':           round(total_monthly * 12, 2),
			'total_potential_annual_savings': round(total_potential, 2),
			'savings_rate':                 f"{int(total_potential / max(total_monthly * 12, 1) * 100)}%",
			'opportunities':               opportunities,
			'high_priority_count':         sum(1 for o in opportunities if o['priority'] == 'high'),
			'status':                       'ok',
		}

	def _market_context(self, vendor: str, category: str) -> str:
		try:
			results = self.search_engine.search(
				f'{vendor} {category} pricing competitors alternatives 2025', num_results=3
			)
			return ' '.join(r.get('body', r.get('snippet', '')) for r in results[:2])[:500]
		except Exception:
			return ''

	def _guess_category(self, vendor: str) -> str:
		vl = vendor.lower()
		for key, cat in _VENDOR_CATEGORY.items():
			if key in vl:
				return cat
		return 'other'

	def _parse_json(self, raw: str) -> dict:
		try:
			m = re.search(r'\{.*\}', raw, re.DOTALL)
			if m:
				return json.loads(m.group())
		except Exception:
			pass
		return {'raw_response': raw}

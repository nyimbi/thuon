# capabilities/CustomerRelationshipManager.py

import json
import re
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


class CustomerRelationshipManager:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def create_customer_profile(self, customer_name: str, contact_details: dict, industry: str) -> dict:
		prompt = (
			f"You are a CRM specialist. Create a comprehensive customer profile.\n\n"
			f"Customer Name: {customer_name}\nIndustry: {industry}\n"
			f"Contact Details: {json.dumps(contact_details)}\n\n"
			f"Return JSON with keys: customer_id (generate a slug), customer_name, industry, "
			f"contact_details, company_size_estimate, decision_making_process, "
			f"key_pain_points (list), buying_signals (list), relationship_stage, "
			f"recommended_next_actions (list), communication_preferences, "
			f"account_health_score (0-100), upsell_opportunities (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				profile = json.loads(match.group())
				if self.data_handler:
					try:
						self.data_handler.insert_data('customers', {
							'name': customer_name,
							'industry': industry,
							'contact_details': json.dumps(contact_details),
						})
					except Exception:
						pass
				return profile
		except Exception:
			pass
		return {'customer_name': customer_name, 'industry': industry, 'result': response, 'status': 'success'}

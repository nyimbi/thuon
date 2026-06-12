# capabilities/talent_analytics_succession_forecaster.py

import json
import re
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


class TalentAnalyticsSuccessionForecaster:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def predict_succession_candidates(self, job_role: str, employee_data_table: str, criteria: list = ['performance_ratings', 'skill_scores', 'leadership_potential']) -> dict:
		employee_data = []
		if self.data_handler:
			try:
				employee_data = self.data_handler.fetch_data(employee_data_table)
			except Exception:
				pass

		data_summary = json.dumps(employee_data[:10], indent=2) if employee_data else f"No data loaded from {employee_data_table}"
		criteria_str = ', '.join(criteria)
		prompt = (
			f"You are a talent analytics expert. Identify succession candidates for the role of {job_role}.\n\n"
			f"Evaluation criteria: {criteria_str}\n"
			f"Employee data sample: {data_summary}\n\n"
			f"Return JSON with keys: role, top_candidates (list, each with: name/id, readiness_level, "
			f"strengths (list), development_gaps (list), estimated_readiness_date, overall_score), "
			f"talent_pipeline_health, critical_gaps (list), development_recommendations (list), "
			f"succession_risk_level."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'role': job_role, 'criteria': criteria, 'status': 'success'}

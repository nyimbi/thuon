# capabilities/cultural_transformation_designer.py

import json
import re
from core.ai_engine import AIModel


class CulturalTransformationDesigner:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def design_cultural_transformation_plan(self, current_culture_description: str, desired_culture_description: str, change_objectives: list = ['improved_collaboration', 'increased_innovation', 'enhanced_customer_centricity']) -> dict:
		objectives_str = ', '.join(change_objectives)
		prompt = (
			f"You are an organizational change expert. Design a cultural transformation plan.\n\n"
			f"Current Culture: {current_culture_description}\n"
			f"Desired Culture: {desired_culture_description}\n"
			f"Change Objectives: {objectives_str}\n\n"
			f"Return JSON with keys: transformation_vision, gap_analysis (list of gaps between current and desired), "
			f"transformation_phases (list, each with: phase_name, duration, key_initiatives (list), "
			f"success_metrics (list), change_agents), leadership_actions (list), "
			f"employee_engagement_strategies (list), resistance_management (list), "
			f"measurement_framework (list of KPIs), timeline_months, estimated_roi, risks (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'change_objectives': change_objectives, 'status': 'success'}

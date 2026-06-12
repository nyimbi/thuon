# capabilities/crisis_simulation_response_architect.py

import json
import re
from core.ai_engine import AIModel


class CrisisSimulationResponseArchitect:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def simulate_crisis_scenario(self, crisis_type: str, organization_profile: str, external_factors: list = ['economic_downturn', 'natural_disaster', 'reputational_damage']) -> dict:
		factors_str = ', '.join(external_factors)
		prompt = (
			f"You are a crisis management expert. Simulate a {crisis_type} crisis scenario and develop a response plan.\n\n"
			f"Organization Profile: {organization_profile}\n"
			f"External Factors: {factors_str}\n\n"
			f"Return JSON with keys: scenario_description, impact_assessment (object with: financial_impact, "
			f"operational_impact, reputational_impact, severity_level), response_phases (list, each with: "
			f"phase, timeframe, actions (list), responsible_parties), communication_plan, "
			f"resource_requirements (list), recovery_timeline, lessons_learned (list), prevention_measures (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'crisis_type': crisis_type, 'external_factors': external_factors, 'status': 'success'}

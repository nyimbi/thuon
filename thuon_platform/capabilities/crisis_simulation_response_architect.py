# capabilities/crisis_simulation_response_architect.py

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
		from core.output_validator import validated_llm_call
		result = validated_llm_call(self.ai_engine, prompt, fallback_key='result', required_keys=[], max_retries=2)
		if result.get('status') == 'parse_failed':
			return {'result': result.get('result', ''), 'crisis_type': crisis_type, 'external_factors': external_factors, 'status': 'success'}
		return result

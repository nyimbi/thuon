# capabilities/DataIntegrator.py

import json
import re
from core.ai_engine import AIModel


class DataIntegrator:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def connect_to_data_source(self, source_name: str, source_type: str, connection_parameters: dict) -> dict:
		safe_params = {k: v for k, v in connection_parameters.items() if 'password' not in k.lower() and 'secret' not in k.lower()}
		prompt = (
			f"You are a data integration architect. Design an integration plan for a data source.\n\n"
			f"Source Name: {source_name}\nSource Type: {source_type}\n"
			f"Connection Parameters: {json.dumps(safe_params)}\n\n"
			f"Return JSON with keys: connection_id (generate a slug), source_name, source_type, "
			f"connection_status (simulated: connected/failed), "
			f"schema_discovery (list of tables/endpoints with: name, fields (list), record_count_estimate), "
			f"data_quality_assessment (list with: field, quality_score, issues (list)), "
			f"recommended_transformations (list), sync_strategy (full/incremental/streaming), "
			f"estimated_data_volume_gb, integration_pipeline_steps (list), "
			f"monitoring_metrics (list), error_handling_strategy."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'source_name': source_name, 'source_type': source_type, 'result': response, 'status': 'success'}

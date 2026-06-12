# capabilities/WorkflowAutomator.py

import json
import re
from core.ai_engine import AIModel


class WorkflowAutomator:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def create_workflow(self, workflow_name: str, description: str, triggers: list, actions: list) -> dict:
		triggers_str = '\n'.join(f"- {t}" for t in triggers)
		actions_str = '\n'.join(f"- {a}" for a in actions)
		prompt = (
			f"You are a workflow automation architect. Design a detailed automated workflow.\n\n"
			f"Workflow Name: {workflow_name}\nDescription: {description}\n"
			f"Triggers:\n{triggers_str}\nActions:\n{actions_str}\n\n"
			f"Return JSON with keys: workflow_id (generate a slug), workflow_name, description, "
			f"trigger_conditions (list with: trigger_type, condition, data_inputs (list)), "
			f"workflow_steps (list with: step_number, step_name, action_type, "
			f"input_mapping, output_mapping, error_handling, retry_policy), "
			f"decision_nodes (list with: condition, true_branch, false_branch), "
			f"data_flow (description), integration_requirements (list), "
			f"monitoring_alerts (list), estimated_time_saved_hours_per_month, "
			f"implementation_notes (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'workflow_name': workflow_name, 'triggers': triggers, 'actions': actions, 'status': 'success'}

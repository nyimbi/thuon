# capabilities/ProjectTaskManager.py

import json
import re
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


class ProjectTaskManager:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def create_project(self, project_name: str, description: str, team_members: list, deadline: str) -> dict:
		members_str = ', '.join(team_members)
		prompt = (
			f"You are a project management expert. Create a detailed project plan.\n\n"
			f"Project: {project_name}\nDescription: {description}\n"
			f"Team: {members_str}\nDeadline: {deadline}\n\n"
			f"Return JSON with keys: project_id (generate a slug), project_name, description, "
			f"team_members (list with: name, role, responsibilities (list)), "
			f"milestones (list with: name, due_date, deliverables (list), owner), "
			f"tasks (list with: task_id, name, description, assignee, priority, "
			f"estimated_hours, dependencies (list of task_ids), status), "
			f"risks (list with: risk, probability, impact, mitigation), "
			f"communication_plan (meeting_cadence, reporting_format, escalation_path), "
			f"success_criteria (list), estimated_total_hours, project_health_indicators (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				project = json.loads(match.group())
				if self.data_handler:
					try:
						self.data_handler.insert_data('projects', {
							'name': project_name,
							'description': description,
							'deadline': deadline,
							'team_members': json.dumps(team_members),
							'status': 'active',
						})
					except Exception:
						pass
				return project
		except Exception:
			pass
		return {'project_name': project_name, 'team_members': team_members, 'deadline': deadline, 'result': response, 'status': 'success'}

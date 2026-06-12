# capabilities/HumanResourceManager.py

import json
import re
from core.ai_engine import AIModel
from core.data_handler import DatabaseHandler


class HumanResourceManager:
	def __init__(self, ai_engine: AIModel, data_handler: DatabaseHandler = None):
		self.ai_engine = ai_engine
		self.data_handler = data_handler

	def onboard_new_employee(self, employee_name: str, job_title: str, department: str, start_date: str) -> dict:
		prompt = (
			f"You are an HR specialist. Create a comprehensive onboarding plan.\n\n"
			f"Employee: {employee_name}\nJob Title: {job_title}\nDepartment: {department}\nStart Date: {start_date}\n\n"
			f"Return JSON with keys: employee_id (generate a slug), employee_name, job_title, department, start_date, "
			f"onboarding_schedule (list with: day, week, activities (list), responsible_party), "
			f"required_training (list with: course_name, duration_hours, deadline, mandatory), "
			f"systems_access_needed (list with: system, access_level, request_date), "
			f"equipment_checklist (list), buddy_program_suggestions, "
			f"30_60_90_day_goals (object with day_30, day_60, day_90 each as list of goals), "
			f"key_contacts (list with: name, role, contact_purpose), "
			f"compliance_requirements (list), onboarding_completion_criteria (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				plan = json.loads(match.group())
				if self.data_handler:
					try:
						self.data_handler.insert_data('employees', {
							'name': employee_name,
							'job_title': job_title,
							'department': department,
							'start_date': start_date,
						})
					except Exception:
						pass
				return plan
		except Exception:
			pass
		return {'employee_name': employee_name, 'job_title': job_title, 'department': department, 'result': response, 'status': 'success'}

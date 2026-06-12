# capabilities/course_creator.py

import json
import re
from core.ai_engine import AIModel


class CourseCreator:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def design_course_outline(
		self,
		topic: str,
		learning_objectives: list,
		target_audience: str,
		duration_hours: int = 10,
	) -> dict:
		objectives_str = '\n'.join(f"- {o}" for o in learning_objectives)
		modules_count  = max(3, duration_hours // 2)

		# Pass 1: Generate course structure + modules
		outline_prompt = (
			f"You are an expert instructional designer. Design a comprehensive course outline.\n\n"
			f"Topic: {topic}\n"
			f"Target Audience: {target_audience}\n"
			f"Duration: {duration_hours} hours\n"
			f"Learning Objectives:\n{objectives_str}\n\n"
			f"Create {modules_count} course modules. Return JSON with keys: "
			f"course_title, description, prerequisites, modules (list, each with: module_number, title, "
			f"duration_hours, topics (list), activities (list), assessment_type), "
			f"total_duration_hours, assessment_strategy, resources (list), certification_criteria."
		)
		response = self.ai_engine.generate_text(outline_prompt)
		try:
			match   = re.search(r'\{.*\}', response, re.DOTALL)
			outline = json.loads(match.group()) if match else {}
		except Exception:
			outline = {}

		if not outline:
			return {'result': response, 'topic': topic, 'target_audience': target_audience,
			        'duration_hours': duration_hours, 'status': 'success'}

		# Pass 2: Generate concrete assessments per module
		modules_summary = json.dumps([
			{'number': m.get('module_number'), 'title': m.get('title'), 'topics': m.get('topics', [])}
			for m in outline.get('modules', [])
		], indent=2)
		assessment_prompt = (
			f"You are an instructional designer. Generate specific assessments for each course module.\n\n"
			f"Course: {outline.get('course_title', topic)}\n"
			f"Target Audience: {target_audience}\n\n"
			f"Modules:\n{modules_summary}\n\n"
			f"For each module, create 2-3 concrete assessment items. "
			f"Return a JSON list, each item: module_number, module_title, "
			f"assessments (list with: type (quiz/project/practical), question_or_task, "
			f"correct_answer_or_rubric, points)."
		)
		assessment_response = self.ai_engine.generate_text(assessment_prompt)
		try:
			match       = re.search(r'\[.*\]', assessment_response, re.DOTALL)
			assessments = json.loads(match.group()) if match else []
		except Exception:
			assessments = []

		outline['module_assessments'] = assessments
		outline['topic']           = topic
		outline['target_audience'] = target_audience
		return outline

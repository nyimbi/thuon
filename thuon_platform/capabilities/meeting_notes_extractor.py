"""
Extracts structured meeting notes, decisions, and action items from raw transcripts.
Action items are automatically pushed to TaskStore. Calendar events for follow-ups.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any


class MeetingNotesExtractor:
	def __init__(self, ai_engine: Any, company_profile: Any | None = None) -> None:
		self._ai      = ai_engine
		self._profile = company_profile

	def extract(
		self,
		transcript: str,
		meeting_title: str = '',
		attendees: str = '',
		meeting_date: str = '',
		auto_create_tasks: bool = True,
	) -> dict[str, Any]:
		"""
		Extract structured notes from a meeting transcript.

		Returns:
		  summary, key_points, decisions, action_items, open_questions,
		  follow_up_dates, sentiment, tags, tasks_created
		"""
		company_context = ''
		if self._profile:
			try:
				company_context = self._profile.get_context('meeting client project')[:600]
			except Exception:
				pass

		prompt = f"""You are extracting structured meeting notes from a transcript.

{f'Company context: {company_context}' if company_context else ''}
{f'Meeting title: {meeting_title}' if meeting_title else ''}
{f'Attendees: {attendees}' if attendees else ''}
{f'Meeting date: {meeting_date}' if meeting_date else ''}

TRANSCRIPT:
{transcript[:8000]}

Extract and return JSON with exactly this structure:
{{
  "summary": "2-3 sentence executive summary of the meeting",
  "key_points": ["bullet point 1", "bullet point 2"],
  "decisions": [
    {{"decision": "what was decided", "owner": "who owns it or empty string", "context": "why"}}
  ],
  "action_items": [
    {{
      "task": "specific actionable task description",
      "owner": "person responsible (first name or role)",
      "deadline": "YYYY-MM-DD or empty string",
      "priority": 1,
      "notes": "any context"
    }}
  ],
  "open_questions": ["question 1", "question 2"],
  "follow_up_dates": [
    {{"title": "follow-up event title", "date": "YYYY-MM-DD", "type": "meeting|milestone|reminder"}}
  ],
  "sentiment": "positive|neutral|tense|mixed",
  "tags": ["tag1", "tag2"],
  "risks_flagged": ["any risks mentioned in the meeting"]
}}

Be specific about deadlines when mentioned. Use YYYY-MM-DD format for all dates.
If no date was mentioned for an action item, leave deadline as empty string.
Return only the JSON object."""

		response = self._ai.generate(prompt)
		data = self._parse_json(response)

		tasks_created: list[str] = []
		if auto_create_tasks and data.get('action_items'):
			try:
				from core.task_store import get_task_store
				store = get_task_store()
				for item in data['action_items']:
					task = store.create(
						title=item.get('task', ''),
						notes=f"From meeting: {meeting_title or 'untitled'}\nOwner: {item.get('owner', '')}\n{item.get('notes', '')}",
						priority=item.get('priority', 2),
						due_date=item.get('deadline') or None,
						project=meeting_title or '',
						tags='meeting,action-item',
					)
					tasks_created.append(task['id'])
			except Exception:
				pass

		follow_ups_created: list[str] = []
		if data.get('follow_up_dates'):
			try:
				from core.calendar_store import get_calendar_store
				cal = get_calendar_store()
				for fu in data['follow_up_dates']:
					if fu.get('date'):
						ev_type = {'meeting': 'meeting', 'milestone': 'milestone'}.get(fu.get('type', ''), 'reminder')
						cal.create(
							title=fu.get('title', 'Follow-up'),
							date=fu['date'],
							event_type=ev_type,
							notes=f'Auto-created from meeting: {meeting_title}',
						)
						follow_ups_created.append(fu['date'])
			except Exception:
				pass

		# Log to memory store
		try:
			from core.memory_store import get_memory_store
			import uuid
			ms = get_memory_store()
			session_id = str(uuid.uuid4())
			ms.log_episode(
				session_id=session_id,
				event_type='meeting',
				content=f"Meeting: {meeting_title or 'untitled'}\n{data.get('summary', '')}",
				metadata={'action_items': len(data.get('action_items', [])), 'date': meeting_date},
			)
		except Exception:
			pass

		data['tasks_created'] = len(tasks_created)
		data['task_ids'] = tasks_created
		data['follow_ups_created'] = len(follow_ups_created)
		return data

	@staticmethod
	def _parse_json(text: str) -> dict[str, Any]:
		text = text.strip()
		m = re.search(r'\{.*\}', text, re.DOTALL)
		if m:
			try:
				return json.loads(m.group())
			except json.JSONDecodeError:
				pass
		return {
			'summary': text[:500],
			'key_points': [],
			'decisions': [],
			'action_items': [],
			'open_questions': [],
			'follow_up_dates': [],
			'sentiment': 'neutral',
			'tags': [],
			'risks_flagged': [],
		}

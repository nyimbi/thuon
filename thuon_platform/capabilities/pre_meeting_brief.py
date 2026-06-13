"""
Generates a pre-meeting brief: who you're meeting, history, talking points,
open action items, recent news about the org.
"""
from __future__ import annotations

import json
import re
from typing import Any


class PreMeetingBrief:
	def __init__(self, ai_engine: Any, search_engine: Any | None = None, company_profile: Any | None = None) -> None:
		self._ai      = ai_engine
		self._search  = search_engine
		self._profile = company_profile

	def generate(
		self,
		attendees: str,
		meeting_purpose: str = '',
		meeting_date: str = '',
		duration_minutes: int = 60,
	) -> dict[str, Any]:
		"""
		Generate a pre-meeting brief.

		Returns:
		  attendee_profiles, relationship_history, talking_points,
		  open_action_items, context_summary, suggested_questions,
		  risks, prep_checklist
		"""
		company_context = ''
		if self._profile:
			try:
				company_context = self._profile.get_context(meeting_purpose or attendees)[:800]
			except Exception:
				pass

		# Pull open action items related to these attendees from task store
		open_items: list[str] = []
		try:
			from core.task_store import get_task_store
			store = get_task_store()
			tasks = store.all()
			for t in tasks:
				if any(name.strip().lower() in (t['title'] + t['notes']).lower()
				       for name in attendees.split(',')):
					open_items.append(f"- {t['title']} (due: {t['due_date'] or 'no date'})")
		except Exception:
			pass

		# Pull relevant memory
		memory_context = ''
		try:
			from core.memory_store import get_memory_store
			ms = get_memory_store()
			memory_context = ms.get_context_block(query=f'{attendees} {meeting_purpose}', top_episodes=5)
		except Exception:
			pass

		# Search for recent news about attendees/orgs
		search_context = ''
		if self._search:
			try:
				query = f'{attendees} {meeting_purpose}'[:100]
				results = self._search.search(query, max_results=3)
				if results:
					search_context = '\n'.join(r.get('body', r.get('title', ''))[:200] for r in results[:3])
			except Exception:
				pass

		open_items_text = '\n'.join(open_items) if open_items else 'None found'

		prompt = f"""Generate a pre-meeting brief for an upcoming meeting.

ATTENDEES: {attendees}
PURPOSE: {meeting_purpose or 'General meeting'}
DATE: {meeting_date or 'Not specified'}
DURATION: {duration_minutes} minutes

COMPANY CONTEXT:
{company_context or 'No company context available'}

OPEN ACTION ITEMS WITH THESE ATTENDEES:
{open_items_text}

MEMORY / HISTORY:
{memory_context or 'No prior history found'}

RECENT NEWS/CONTEXT:
{search_context or 'No recent news available'}

Generate a comprehensive pre-meeting brief in JSON format:
{{
  "attendee_profiles": [
    {{
      "name": "person name",
      "role": "their title/role",
      "org": "their organization",
      "background": "what we know about them",
      "communication_style": "how they prefer to engage",
      "priorities": ["what they care about"]
    }}
  ],
  "relationship_history": "summary of past interactions and relationship status",
  "context_summary": "key context going into this meeting — what's the situation",
  "talking_points": [
    {{"point": "specific talking point", "rationale": "why this matters", "desired_outcome": "what you want from this point"}}
  ],
  "open_action_items": ["items from prior interactions needing follow-up"],
  "suggested_questions": ["question to ask them"],
  "things_to_avoid": ["sensitive topics, past friction points"],
  "desired_outcomes": ["what success looks like for this meeting"],
  "prep_checklist": ["thing to prepare or review before the meeting"],
  "risks": ["potential issues or blockers to be aware of"]
}}

Return only the JSON object."""

		response = self._ai.generate(prompt)
		data = self._parse_json(response)
		data['_meta'] = {
			'attendees': attendees,
			'purpose': meeting_purpose,
			'date': meeting_date,
			'duration_minutes': duration_minutes,
		}
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
			'attendee_profiles': [],
			'relationship_history': '',
			'context_summary': text[:500],
			'talking_points': [],
			'open_action_items': [],
			'suggested_questions': [],
			'things_to_avoid': [],
			'desired_outcomes': [],
			'prep_checklist': [],
			'risks': [],
		}

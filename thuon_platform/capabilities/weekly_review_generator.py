"""
Generates an executive weekly review: pipeline, financials, tasks, risks, wins.
Aggregates data from RFP tracker, task store, calendar, and memory — no inputs required.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any


class WeeklyReviewGenerator:
	def __init__(self, ai_engine: Any, company_profile: Any | None = None) -> None:
		self._ai      = ai_engine
		self._profile = company_profile

	def generate(self, week_ending: str = '') -> dict[str, Any]:
		"""
		Generate a comprehensive weekly review.
		week_ending: ISO date string (defaults to last Friday).
		"""
		if not week_ending:
			today = date.today()
			days_since_friday = (today.weekday() - 4) % 7
			last_friday = today - timedelta(days=days_since_friday)
			week_ending = last_friday.isoformat()

		week_start = (date.fromisoformat(week_ending) - timedelta(days=6)).isoformat()

		# Gather data from all stores
		context_parts: list[str] = []

		# RFP pipeline
		rfp_summary = self._gather_rfp_context()
		if rfp_summary:
			context_parts.append(f'## RFP PIPELINE\n{rfp_summary}')

		# Tasks
		task_summary = self._gather_task_context()
		if task_summary:
			context_parts.append(f'## TASKS\n{task_summary}')

		# Calendar upcoming
		cal_summary = self._gather_calendar_context()
		if cal_summary:
			context_parts.append(f'## UPCOMING DATES\n{cal_summary}')

		# Memory context
		memory_summary = self._gather_memory_context()
		if memory_summary:
			context_parts.append(f'## RECENT ACTIVITY / CONTEXT\n{memory_summary}')

		# Company context
		company_context = ''
		if self._profile:
			try:
				company_context = self._profile.get_context('pipeline revenue staffing')[:600]
			except Exception:
				pass

		context_block = '\n\n'.join(context_parts) if context_parts else 'No data available yet.'

		prompt = f"""Generate a comprehensive executive weekly review.

Week ending: {week_ending}
Week start: {week_start}

COMPANY CONTEXT:
{company_context or 'Not configured'}

CURRENT DATA:
{context_block}

Generate a structured weekly review in JSON format:
{{
  "week_ending": "{week_ending}",
  "headline": "one-sentence characterization of the week",
  "wins": ["notable achievements this week"],
  "pipeline": {{
    "summary": "2-3 sentence pipeline status",
    "active_rfps": 0,
    "upcoming_deadlines": ["deadline description"],
    "opportunities_added": 0,
    "opportunities_advanced": 0
  }},
  "tasks": {{
    "completed_this_week": 0,
    "overdue": 0,
    "due_next_week": 0,
    "top_priorities": ["task 1", "task 2", "task 3"]
  }},
  "upcoming_key_dates": [
    {{"date": "YYYY-MM-DD", "event": "description", "action_required": "what to do"}}
  ],
  "risks_and_blockers": [
    {{"risk": "description", "severity": "high|medium|low", "mitigation": "what to do about it"}}
  ],
  "focus_next_week": ["top 3 priorities for next week"],
  "metrics_snapshot": {{
    "rfps_active": 0,
    "tasks_pending": 0,
    "tasks_overdue": 0,
    "days_until_next_deadline": null
  }},
  "notes": "any additional context or observations"
}}

Return only the JSON object."""

		response = self._ai.generate(prompt)
		return self._parse_json(response)

	def _gather_rfp_context(self) -> str:
		try:
			from core.rfp_tracker import get_rfp_tracker
			tracker = get_rfp_tracker()
			records = tracker.all()
			if not records:
				return 'No RFPs tracked yet.'
			lines = []
			active_statuses = {'discovered', 'evaluating', 'awaiting_strategy', 'responding', 'in_review'}
			for r in records:
				if r.status.value in active_statuses:
					deadline = f" | Deadline: {r.deadline}" if r.deadline else ''
					lines.append(f"- [{r.status.value}] {r.title} ({r.issuer}){deadline}")
			return '\n'.join(lines) if lines else 'No active RFPs.'
		except Exception:
			return ''

	def _gather_task_context(self) -> str:
		try:
			from core.task_store import get_task_store
			store = get_task_store()
			stats = store.stats()
			overdue = store.overdue()
			due_soon = store.due_soon(days=7)
			lines = [
				f"Pending: {stats['pending']} | In Progress: {stats['in_progress']} | "
				f"Completed: {stats['completed']} | Overdue: {stats['overdue']}"
			]
			if overdue:
				lines.append('OVERDUE:')
				lines.extend(f"  - {t['title']} (was due {t['due_date']})" for t in overdue[:5])
			if due_soon:
				lines.append('DUE THIS WEEK:')
				lines.extend(f"  - {t['title']} (due {t['due_date']})" for t in due_soon[:5])
			return '\n'.join(lines)
		except Exception:
			return ''

	def _gather_calendar_context(self) -> str:
		try:
			from core.calendar_store import get_calendar_store
			cal = get_calendar_store()
			upcoming = cal.upcoming(days=14)
			if not upcoming:
				return 'No upcoming events in next 14 days.'
			lines = []
			for ev in upcoming[:8]:
				icon = ev['_type_meta']['icon']
				lines.append(f"- {ev['date']}: {icon} {ev['title']}")
			return '\n'.join(lines)
		except Exception:
			return ''

	def _gather_memory_context(self) -> str:
		try:
			from core.memory_store import get_memory_store
			ms = get_memory_store()
			episodes = ms.recent_episodes(limit=8)
			if not episodes:
				return ''
			return '\n'.join(f"- [{e['type']}] {e['content'][:150]}" for e in episodes)
		except Exception:
			return ''

	@staticmethod
	def _parse_json(text: str) -> dict[str, Any]:
		text = text.strip()
		m = re.search(r'\{.*\}', text, re.DOTALL)
		if m:
			try:
				return json.loads(m.group())
			except json.JSONDecodeError:
				pass
		return {'headline': 'Weekly review generated', 'notes': text[:1000]}

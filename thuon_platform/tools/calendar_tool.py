from datetime import datetime, timedelta, timezone, date
from typing import Any
from uuid import uuid4

try:
	from icalendar import Calendar, Event
except ImportError:
	Calendar = None
	Event = None

from core.settings_manager import get_settings


class CalendarTool:

	def get_events(self, days_ahead: int = 7, calendar_path: str = '') -> dict[str, Any]:
		try:
			if Calendar is None:
				return {'status': 'error', 'error': 'Package icalendar not installed. Run: uv add icalendar'}

			settings = get_settings()
			path = calendar_path or settings.get_setting('tools.calendar.ics_path', '')
			if not path:
				return {'status': 'error', 'error': 'No calendar_path provided and tools.calendar.ics_path not configured'}

			with open(path, 'rb') as f:
				cal = Calendar.from_ical(f.read())

			now = datetime.now(tz=timezone.utc)
			cutoff = now + timedelta(days=days_ahead)
			events: list[dict[str, Any]] = []

			for component in cal.walk():
				if component.name != 'VEVENT':
					continue

				dtstart = component.get('DTSTART')
				dtend = component.get('DTEND')
				if dtstart is None:
					continue

				start_val = dtstart.dt
				end_val = dtend.dt if dtend else start_val

				# normalize date to datetime for comparison
				if isinstance(start_val, date) and not isinstance(start_val, datetime):
					start_val = datetime(start_val.year, start_val.month, start_val.day, tzinfo=timezone.utc)
				elif isinstance(start_val, datetime) and start_val.tzinfo is None:
					start_val = start_val.replace(tzinfo=timezone.utc)

				if isinstance(end_val, date) and not isinstance(end_val, datetime):
					end_val = datetime(end_val.year, end_val.month, end_val.day, tzinfo=timezone.utc)
				elif isinstance(end_val, datetime) and end_val.tzinfo is None:
					end_val = end_val.replace(tzinfo=timezone.utc)

				if start_val < now or start_val > cutoff:
					continue

				summary = str(component.get('SUMMARY', ''))
				description = str(component.get('DESCRIPTION', ''))
				location = str(component.get('LOCATION', ''))
				uid = str(component.get('UID', ''))

				events.append({
					'title': summary,
					'start': start_val.isoformat(),
					'end': end_val.isoformat(),
					'description': description,
					'location': location,
					'uid': uid,
				})

			events.sort(key=lambda e: e['start'])
			return {'status': 'success', 'events': events, 'count': len(events), 'days_ahead': days_ahead}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def create_event(
		self,
		title: str,
		start: str,
		end: str,
		description: str = '',
		location: str = '',
		calendar_path: str = '',
	) -> dict[str, Any]:
		try:
			if Calendar is None or Event is None:
				return {'status': 'error', 'error': 'Package icalendar not installed. Run: uv add icalendar'}

			settings = get_settings()
			path = calendar_path or settings.get_setting('tools.calendar.ics_path', '')
			if not path:
				return {'status': 'error', 'error': 'No calendar_path provided and tools.calendar.ics_path not configured'}

			start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) if datetime.fromisoformat(start).tzinfo is None else datetime.fromisoformat(start)
			end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if datetime.fromisoformat(end).tzinfo is None else datetime.fromisoformat(end)

			uid = str(uuid4())

			event = Event()
			event.add('SUMMARY', title)
			event.add('DTSTART', start_dt)
			event.add('DTEND', end_dt)
			event.add('UID', uid)
			if description:
				event.add('DESCRIPTION', description)
			if location:
				event.add('LOCATION', location)

			import os
			if os.path.exists(path):
				with open(path, 'rb') as f:
					cal = Calendar.from_ical(f.read())
			else:
				cal = Calendar()
				cal.add('PRODID', '-//CalendarTool//EN')
				cal.add('VERSION', '2.0')

			cal.add_component(event)

			with open(path, 'wb') as f:
				f.write(cal.to_ical())

			return {
				'status': 'success',
				'uid': uid,
				'title': title,
				'start': start_dt.isoformat(),
				'end': end_dt.isoformat(),
				'calendar_path': path,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

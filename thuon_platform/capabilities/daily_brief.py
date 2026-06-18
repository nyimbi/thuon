# capabilities/daily_brief.py
"""
Daily brief aggregator — three-tier architecture.

Tier 1 (zero-auth, always runs):
  FX rates (open.er-api.com) · Pending todos (Obsidian + data/todos/) ·
  Calendar summary (CalendarStore) · News digest (search, Kenya/EA + global)

Tier 2 (config, no OAuth):
  Weather (wttr.in) · Economic calendar (Forex Factory RSS + search fallback)

Tier 3 (credentials required):
  iCal import (icalendar lib, configured path) · Email summaries (IMAP)
"""
from __future__ import annotations

import email as _email_lib
import imaplib
import json
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.bundle import writable_data_dir as _wdd
_TODOS_DIR = _wdd() / 'todos'

_FX_URL  = 'https://open.er-api.com/v6/latest/USD'
_WTTR_URL = 'https://wttr.in/{location}?format=j1'
_FF_RSS  = 'https://rss.forexfactory.com/'

_EA_QUERIES = [
	'Kenya business economy news today',
	'East Africa markets trade news today',
	'Nairobi financial news today',
	'Kenya government policy regulation news',
]
_POLITICS_QUERIES = [
	'Kenya politics parliament news today',
	'William Ruto government Kenya news today',
	'Kenya opposition ODM Raila news today',
]
_CONFLICT_QUERIES = [
	'Ukraine Russia war latest news today',
	'Iran war conflict military news today',
	'Middle East conflict latest news today',
]
_SPORTS_QUERIES = [
	'FIFA World Cup 2026 news results today',
	'Kenya Simbas rugby news results today',
	'World Rugby international test match results today',
	'Six Nations Rugby Championship news results today',
	'polo world cup championship news results today',
	'major sports results today',
]
_GLOBAL_QUERIES = [
	'global markets economy news today',
	'US Federal Reserve ECB interest rate decision news',
	'world major economic events today',
]


class DailyBrief:
	def __init__(
		self,
		ai_engine,
		search_engine=None,
		knowledge_pipeline=None,
		calendar_store=None,
		obsidian_bridge=None,
		config: dict | None = None,
	):
		self.ai_engine          = ai_engine
		self.search_engine      = search_engine
		self.knowledge_pipeline = knowledge_pipeline
		self.calendar_store     = calendar_store
		self.obsidian_bridge    = obsidian_bridge
		self.cfg                = config or {}

	# ── Public ────────────────────────────────────────────────────────────────

	def generate(
		self,
		date_str: str | None = None,
		include_sections: list[str] | None = None,
	) -> dict:
		today   = date_str or date.today().isoformat()
		display = datetime.strptime(today, '%Y-%m-%d').strftime('%A, %d %B %Y')
		run     = set(include_sections) if include_sections else {
			'fx', 'weather', 'news', 'economic_calendar', 'calendar', 'todos', 'emails',
		}

		brief: dict[str, Any] = {
			'generated_at': datetime.utcnow().isoformat(),
			'date': today,
			'display_date': display,
			'sections': {},
		}
		sec = brief['sections']

		if 'fx'                 in run: sec['fx']                 = self._fetch_fx()
		if 'weather'            in run: sec['weather']            = self._weather()
		if 'news'               in run: sec['news']               = self._news_digest(today)
		if 'economic_calendar'  in run: sec['economic_calendar']  = self._economic_calendar(today)
		if 'calendar'           in run: sec['calendar']           = self._calendar_summary(today)
		if 'todos'              in run: sec['todos']              = self._collect_todos(today)
		if 'emails'             in run: sec['emails']             = self._email_summaries()

		sec['synthesis']        = self._synthesize(sec, today)
		brief['formatted_text'] = self._format(brief)
		brief['word_count']     = len(brief['formatted_text'].split())
		brief['status']         = 'ok'
		return brief

	# ── Tier 1: FX ────────────────────────────────────────────────────────────

	def _fetch_fx(self) -> dict:
		"""Fetch FX rates from open.er-api.com (free, no key). Base: KES."""
		pairs = self.cfg.get('fx_pairs', ['USD', 'EUR', 'GBP', 'UGX', 'TZS', 'ZAR', 'CNY'])
		try:
			with urllib.request.urlopen(_FX_URL, timeout=6) as r:
				data = json.loads(r.read())
			usd_rates   = data.get('rates', {})
			kes_per_usd = usd_rates.get('KES', 1.0)
			rates: dict[str, float] = {}
			for sym in pairs:
				if sym == 'USD':
					rates['USD'] = round(kes_per_usd, 2)
				elif sym in usd_rates and usd_rates[sym]:
					rates[sym] = round(kes_per_usd / usd_rates[sym], 2)
			return {
				'base':    'KES',
				'quote':   '1 foreign unit = N KES',
				'rates':   rates,
				'source':  'open.er-api.com',
				'as_of':   data.get('time_last_update_utc', ''),
			}
		except Exception as exc:
			return {'rates': {}, 'error': str(exc)}

	# ── Tier 2: Weather ───────────────────────────────────────────────────────

	def _weather(self) -> dict:
		"""Fetch weather from wttr.in (free, no key)."""
		location = self.cfg.get('weather_location', 'Nairobi')
		url = _WTTR_URL.format(location=urllib.request.quote(location))
		try:
			with urllib.request.urlopen(url, timeout=6) as r:
				data = json.loads(r.read())
			cur     = data['current_condition'][0]
			today_w = data.get('weather', [{}])[0]
			return {
				'location':    location,
				'condition':   cur.get('weatherDesc', [{}])[0].get('value', ''),
				'temp_c':      cur.get('temp_C', ''),
				'feels_like_c': cur.get('FeelsLikeC', ''),
				'humidity_pct': cur.get('humidity', ''),
				'wind_kmph':   cur.get('windspeedKmph', ''),
				'max_c':       today_w.get('maxtempC', ''),
				'min_c':       today_w.get('mintempC', ''),
				'uv_index':    today_w.get('uvIndex', ''),
			}
		except Exception as exc:
			return {'error': str(exc)}

	# ── Tier 1: News ─────────────────────────────────────────────────────────

	def _news_digest(self, date_str: str) -> dict:
		if not self.search_engine:
			return {'items': {}, 'summary': 'Search engine not configured.'}

		month = date_str[:7]

		def _fetch(queries: list[str], per_query: int = 3, cap: int = 6) -> list[dict]:
			results: list[dict] = []
			for q in queries:
				try:
					for r in self.search_engine.search(
						f'{q} {month}',
						num_results=per_query + 1,
						time_range='week',
					)[:per_query]:
						results.append({
							'title':   r.get('title', ''),
							'snippet': r.get('body', r.get('snippet', ''))[:300],
							'url':     r.get('href', r.get('url', '')),
						})
				except Exception:
					pass
			return results[:cap]

		ea       = _fetch(_EA_QUERIES,       per_query=3, cap=8)
		politics = _fetch(_POLITICS_QUERIES, per_query=3, cap=6)
		conflict = _fetch(_CONFLICT_QUERIES, per_query=3, cap=6)
		sports   = _fetch(_SPORTS_QUERIES,   per_query=3, cap=6)
		economy  = _fetch(_GLOBAL_QUERIES,   per_query=2, cap=4)

		all_items = ea + politics + conflict + sports + economy
		if not all_items:
			return {'items': {}, 'summary': 'No news retrieved.'}

		def _block(tag: str, items: list[dict]) -> str:
			return '\n'.join(f'[{tag}] {it["title"]}: {it["snippet"]}' for it in items)

		headlines = '\n'.join([
			_block('EA-BIZ',      ea),
			_block('KE-POLITICS', politics),
			_block('CONFLICT',    conflict),
			_block('SPORTS',      sports),
			_block('GLOBAL-ECON', economy),
		])

		prompt = (
			f'Date: {date_str}\n'
			'Brief a Nairobi-based professional services executive.\n'
			'Summarize into FOUR blocks — use exactly these bold headings:\n'
			'**Kenya Business & East Africa** — 3-4 bullets, business/regulatory impact\n'
			'**Kenyan Politics** — 2-3 bullets, key political developments\n'
			'**Conflicts & Geopolitics** — 2-3 bullets covering Ukraine, Iran/Middle East\n'
			'**Sports** — 2-3 bullets: FIFA World Cup, Kenya Simbas rugby, world rugby, polo\n\n'
			f'{headlines}\n\n'
			'Direct bullets only. No preamble. Omit a block only if zero relevant headlines exist for it.'
		)
		return {
			'items': {'ea': ea, 'politics': politics, 'conflict': conflict, 'sports': sports, 'economy': economy},
			'summary': self._llm(prompt),
		}

	# ── Tier 2: Economic calendar ─────────────────────────────────────────────

	def _economic_calendar(self, date_str: str) -> dict:
		events: list[dict] = []

		# Forex Factory RSS via feedparser
		try:
			import feedparser
			feed = feedparser.parse(_FF_RSS)
			ym   = date_str[:7]
			for entry in feed.entries[:30]:
				pub = entry.get('published', '')
				if ym in pub or not pub:
					events.append({
						'event':  entry.get('title', ''),
						'detail': entry.get('summary', '')[:200],
						'source': 'ForexFactory',
					})
		except Exception:
			pass

		# Supplement with targeted Kenya/macro queries if RSS is empty or unavailable
		if len(events) < 3 and self.search_engine:
			month = datetime.strptime(date_str, '%Y-%m-%d').strftime('%B %Y')
			for q in [
				f'CBK Central Bank Kenya MPC meeting decision {month}',
				f'Kenya National Treasury budget announcement {month}',
				f'IMF World Bank Africa economic outlook {month}',
			]:
				try:
					for r in self.search_engine.search(q, num_results=2)[:1]:
						title = r.get('title', '')
						# Skip generic aggregators and encyclopedias
						url = r.get('href', r.get('url', ''))
						if any(skip in url for skip in ('wikipedia.', 'economist.com', 'e-conomic')):
							continue
						events.append({
							'event':  title,
							'detail': r.get('body', r.get('snippet', ''))[:200],
							'source': 'search',
						})
				except Exception:
					pass

		return {'events': events[:10]}

	# ── Tier 1: Calendar ──────────────────────────────────────────────────────

	def _calendar_summary(self, date_str: str) -> dict:
		today_events: list[dict] = []
		upcoming:     list[dict] = []

		if self.calendar_store:
			try:
				today_events = self.calendar_store.for_date(date_str)
				next7        = self.calendar_store.upcoming(days=7)
				upcoming     = [e for e in next7 if e['date'] != date_str][:10]
			except Exception:
				pass

		# Tier 3: merge iCal events
		ical_path = self.cfg.get('ical_path')
		if ical_path:
			today_events = today_events + self._parse_ical(ical_path, date_str)

		return {
			'today':       today_events,
			'upcoming_7d': upcoming,
			'today_count': len(today_events),
		}

	# ── Tier 3: iCal ─────────────────────────────────────────────────────────

	def _parse_ical(self, ical_path: str, date_str: str) -> list[dict]:
		try:
			from icalendar import Calendar  # type: ignore[import]
		except ImportError:
			return []
		try:
			cal    = Calendar.from_ical(Path(ical_path).expanduser().read_bytes())
			target = date.fromisoformat(date_str)
			events = []
			for component in cal.walk():
				if component.name != 'VEVENT':
					continue
				dtstart = component.get('DTSTART')
				if dtstart is None:
					continue
				ev_date = dtstart.dt
				if hasattr(ev_date, 'date'):
					ev_date = ev_date.date()
				if ev_date == target:
					events.append({
						'title':    str(component.get('SUMMARY', 'Untitled')),
						'time':     dtstart.dt.strftime('%H:%M') if hasattr(dtstart.dt, 'hour') else '',
						'location': str(component.get('LOCATION', '')),
						'notes':    str(component.get('DESCRIPTION', ''))[:80],
						'source':   'ical',
					})
			return events
		except Exception:
			return []

	# ── Tier 1: Todos ─────────────────────────────────────────────────────────

	def _collect_todos(self, date_str: str) -> dict:
		items: list[dict] = []
		_CHECKBOX = re.compile(r'^[-*]\s+\[ \]\s+(.+)', re.MULTILINE)
		_DUE      = re.compile(
			r'📅\s*(\d{4}-\d{2}-\d{2})|due:?\s*(\d{4}-\d{2}-\d{2})',
			re.IGNORECASE,
		)

		def _extract(text: str, source: str) -> None:
			for m in _CHECKBOX.finditer(text):
				raw = m.group(1).strip()
				dm  = _DUE.search(raw)
				due = (dm.group(1) or dm.group(2)) if dm else None
				if dm:
					raw = _DUE.sub('', raw).strip()
				items.append({'text': raw[:120], 'source': source, 'due': due})

		# Local data/todos/
		_TODOS_DIR.mkdir(parents=True, exist_ok=True)
		for f in sorted(_TODOS_DIR.glob('*.md')):
			try:
				_extract(f.read_text(encoding='utf-8'), f.name)
			except Exception:
				pass

		# Obsidian vault
		if self.obsidian_bridge and self.obsidian_bridge.enabled:
			vault = self.obsidian_bridge._vault
			scan  = self.cfg.get('todo_vault_folders', ['Tasks', 'Todos', 'Daily'])

			# Top-level vault .md files that contain checkboxes
			try:
				for f in vault.glob('*.md'):
					try:
						content = f.read_text(encoding='utf-8', errors='ignore')
						if '- [ ]' in content:
							_extract(content, f'obsidian:{f.stem}')
					except Exception:
						pass
			except Exception:
				pass

			# Configured sub-folders
			for folder_name in scan:
				try:
					for doc in self.obsidian_bridge.read_folder(folder_name):
						_extract(doc['content'], f"obsidian:{folder_name}/{doc['name']}")
				except Exception:
					pass

		today_s   = date_str
		overdue   = [i for i in items if i.get('due') and i['due'] < today_s]
		due_today = [i for i in items if i.get('due') == today_s]

		def _sort_key(it: dict) -> tuple:
			d = it.get('due') or '9999-99-99'
			return (0 if d < today_s else (1 if d == today_s else 2), d)

		items.sort(key=_sort_key)
		return {
			'items':          items[:50],
			'count':          len(items),
			'overdue_count':  len(overdue),
			'due_today_count': len(due_today),
		}

	# ── Tier 3: Email ─────────────────────────────────────────────────────────

	def _email_summaries(self) -> dict:
		host      = self.cfg.get('imap_host', '')
		port      = int(self.cfg.get('imap_port', 993))
		username  = self.cfg.get('imap_username', '')
		password  = self.cfg.get('imap_password', '')
		folder    = self.cfg.get('imap_folder', 'INBOX')
		max_mails = int(self.cfg.get('email_max', 10))

		if not all([host, username, password]):
			return {'summaries': [], 'note': 'IMAP not configured (set imap_host/username/password).'}

		conn = None
		try:
			conn = imaplib.IMAP4_SSL(host, port)
			conn.login(username, password)
			conn.select(folder, readonly=True)

			_, data    = conn.search(None, 'UNSEEN')
			all_uids   = data[0].split()
			uids       = all_uids[-max_mails:]  # most recent N unseen

			summaries: list[dict] = []
			for uid in reversed(uids):
				try:
					_, msg_data = conn.fetch(uid, '(RFC822)')
					msg = _email_lib.message_from_bytes(msg_data[0][1])

					raw_subj  = _email_lib.header.decode_header(msg.get('Subject', ''))[0]
					subject   = (
						raw_subj[0].decode(
							raw_subj[1].decode() if isinstance(raw_subj[1], bytes) else (raw_subj[1] or 'utf-8')
						)
						if isinstance(raw_subj[0], bytes)
						else str(raw_subj[0])
					)
					from_addr = msg.get('From', '')
					body      = _extract_email_body(msg)[:1500]

					if body.strip():
						prompt  = (
							f'Subject: {subject}\nFrom: {from_addr}\n\n{body}\n\n'
							'One or two sentences: what is this about and what action (if any) is required?'
						)
						summary = self._llm(prompt)
					else:
						summary = subject

					summaries.append({'from': from_addr, 'subject': subject, 'summary': summary})
				except Exception:
					continue

			return {'summaries': summaries, 'unread_count': len(all_uids)}
		except Exception as exc:
			return {'summaries': [], 'error': str(exc)}
		finally:
			if conn is not None:
				try:
					conn.logout()
				except Exception:
					pass

	# ── Synthesis ─────────────────────────────────────────────────────────────

	def _synthesize(self, sections: dict, date_str: str) -> dict:
		parts: list[str] = []

		fx = sections.get('fx', {})
		if fx.get('rates'):
			row = ' | '.join(f'{k} {v:,.2f}' for k, v in list(fx['rates'].items())[:5])
			parts.append(f'FX (per 1 unit in KES): {row}')

		wx = sections.get('weather', {})
		if wx and not wx.get('error'):
			parts.append(
				f"Weather {wx.get('location')}: {wx.get('condition')}, "
				f"{wx.get('temp_c')}°C, H{wx.get('max_c')}/L{wx.get('min_c')}"
			)

		news_sum = sections.get('news', {}).get('summary', '')
		if news_sum:
			parts.append(f'News:\n{news_sum}')

		todos = sections.get('todos', {})
		if todos.get('count'):
			overdue = todos.get('overdue_count', 0)
			top5    = '; '.join(t['text'][:60] for t in todos.get('items', [])[:5])
			parts.append(
				f"Open todos: {todos['count']}"
				+ (f' ({overdue} OVERDUE)' if overdue else '')
				+ f'. Top: {top5}'
			)

		today_evs = sections.get('calendar', {}).get('today', [])
		if today_evs:
			ev_str = ', '.join(
				f"{e.get('time', '')} {e.get('title', '')[:40]}".strip()
				for e in today_evs[:5]
			)
			parts.append(f'Schedule today: {ev_str}')

		email_sec = sections.get('emails', {})
		if email_sec.get('summaries'):
			top3 = '; '.join(e['subject'][:40] for e in email_sec['summaries'][:3])
			parts.append(
				f"Unread emails ({email_sec.get('unread_count', '?')}): {top3}"
			)

		econ = sections.get('economic_calendar', {})
		if econ.get('events'):
			top3 = '; '.join(e['event'][:50] for e in econ['events'][:3])
			parts.append(f'Economic events: {top3}')

		if not parts:
			return {'priorities': [], 'action_items': []}

		context = '\n\n'.join(parts)
		prompt  = (
			f'Daily brief: {date_str}. Executive, Nairobi-based professional services firm.\n\n'
			f'{context}\n\n'
			'Produce exactly:\n'
			'**Top 3 Priorities** (numbered, one line each, most urgent first)\n'
			'**5 Concrete Action Items** (numbered, verb + object + by-when)'
		)
		return {'raw': self._llm(prompt), 'sections_used': len(parts)}

	# ── Formatting ────────────────────────────────────────────────────────────

	def _format(self, brief: dict) -> str:
		lines: list[str] = [f"# Daily Brief — {brief['display_date']}", '']
		s = brief.get('sections', {})

		# FX — major pairs show as X/KES; regional micro-currencies inverted to KES/X
		fx = s.get('fx', {})
		if fx.get('rates'):
			lines.append('## FX Rates')
			lines.append('| Pair | Rate |')
			lines.append('|------|-----:|')
			for sym, val in fx['rates'].items():
				if val >= 1:
					lines.append(f'| 1 {sym} → KES | {val:,.2f} |')
				else:
					inv = round(1 / val) if val else 0
					lines.append(f'| 1 KES → {sym} | {inv:,} |')
			if fx.get('as_of'):
				lines.append(f"*{fx['as_of']}  ·  {fx.get('source', '')}*")
			lines.append('')

		# Weather
		wx = s.get('weather', {})
		if wx and not wx.get('error'):
			lines += [
				'## Weather',
				(
					f"**{wx.get('location')}** — {wx.get('condition')} · "
					f"{wx.get('temp_c')}°C (feels {wx.get('feels_like_c')}°C) · "
					f"↑{wx.get('max_c')}° ↓{wx.get('min_c')}° · "
					f"💧{wx.get('humidity_pct')}% · 🌬 {wx.get('wind_kmph')} km/h"
					+ (f" · UV {wx.get('uv_index')}" if wx.get('uv_index') else '')
				),
				'',
			]

		# Schedule
		cal       = s.get('calendar', {})
		today_evs = cal.get('today', [])
		if today_evs:
			lines.append("## Today's Schedule")
			for ev in today_evs:
				t    = (ev.get('time') or '').ljust(5)
				icon = ev.get('_type_meta', {}).get('icon', '•')
				note = f"  _{ev['notes'][:60]}_" if ev.get('notes') else ''
				lines.append(f"- `{t}` {icon} **{ev.get('title', '')}**{note}")
			lines.append('')
		upcoming = cal.get('upcoming_7d', [])
		if upcoming:
			lines.append('## Coming Up (7 days)')
			for ev in upcoming[:6]:
				icon = ev.get('_type_meta', {}).get('icon', '•')
				lines.append(f"- {ev.get('date')} {icon} {ev.get('title', '')}")
			lines.append('')

		# Todos
		todos = s.get('todos', {})
		if todos.get('count'):
			overdue = todos.get('overdue_count', 0)
			header  = f"## Todos  *({todos['count']} open"
			if overdue:
				header += f', ⚠ {overdue} overdue'
			header += ')*'
			lines.append(header)
			for item in todos.get('items', [])[:12]:
				due_tag = f" `due {item['due']}`" if item.get('due') else ''
				src     = item['source']
				lines.append(f"- [ ] {item['text']}{due_tag}  —  *{src}*")
			lines.append('')

		# News
		news_sum = s.get('news', {}).get('summary', '')
		if news_sum:
			lines += ['## News — Kenya, East Africa & World', '', news_sum, '']

		# Economic calendar
		econ = s.get('economic_calendar', {})
		if econ.get('events'):
			lines.append('## Economic Calendar')
			for ev in econ['events'][:6]:
				detail = ev.get('detail', '')[:100]
				lines.append(f"- **{ev.get('event', '')}**" + (f': {detail}' if detail else ''))
			lines.append('')

		# Emails
		emails = s.get('emails', {})
		if emails.get('summaries'):
			unread = emails.get('unread_count', '?')
			lines.append(f'## Emails  *({unread} unread)*')
			for em in emails['summaries'][:6]:
				lines.append(f"- **{em['subject'][:55]}**  `{em['from'][:35]}`")
				lines.append(f"  {em['summary']}")
			lines.append('')

		# Synthesis
		synth = s.get('synthesis', {})
		if synth.get('raw'):
			lines += ['## Priorities & Actions', '', synth['raw'], '']

		return '\n'.join(lines)

	# ── Internal ──────────────────────────────────────────────────────────────

	def _llm(self, prompt: str) -> str:
		try:
			raw = self.ai_engine.generate_text(prompt).strip()
			return _strip_think(raw)
		except Exception:
			return ''


def _strip_think(text: str) -> str:
	"""Strip <think>…</think> reasoning blocks emitted by lfm2.5/Qwen3."""
	if '<think>' not in text:
		return text
	parts = text.split('</think>')
	if len(parts) > 1:
		return parts[-1].strip()
	return text[:text.index('<think>')].strip()


def _extract_email_body(msg: _email_lib.message.Message) -> str:
	"""Walk MIME tree, prefer plain text, fall back to HTML→text."""
	for part in msg.walk():
		ct = part.get_content_type()
		if ct == 'text/plain':
			try:
				return part.get_payload(decode=True).decode(
					part.get_content_charset() or 'utf-8', errors='replace'
				)
			except Exception:
				pass
		if ct == 'text/html':
			try:
				from bs4 import BeautifulSoup
				return BeautifulSoup(
					part.get_payload(decode=True), 'html.parser'
				).get_text(' ')
			except Exception:
				pass
	return ''

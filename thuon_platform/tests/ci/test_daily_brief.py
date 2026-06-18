# tests/ci/test_daily_brief.py
"""
Unit tests for DailyBrief — all network/LLM calls mocked.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from capabilities.daily_brief import DailyBrief, _extract_email_body


# ── Helpers ──────────────────────────────────────────────────────────────────

class FakeAI:
	def generate_text(self, prompt: str) -> str:
		return 'LLM response.'


def _brief(config=None, search=None, calendar=None, obsidian=None) -> DailyBrief:
	return DailyBrief(
		ai_engine       = FakeAI(),
		search_engine   = search,
		calendar_store  = calendar,
		obsidian_bridge = obsidian,
		config          = config or {},
	)


# ── FX ───────────────────────────────────────────────────────────────────────

_FX_PAYLOAD = json.dumps({
	'result': 'success',
	'time_last_update_utc': 'Fri, 13 Jun 2026 00:00:00 +0000',
	'rates': {'KES': 129.5, 'EUR': 0.92, 'GBP': 0.79, 'UGX': 3745.0, 'TZS': 2553.0, 'ZAR': 18.2, 'CNY': 7.25},
}).encode()


def test_fetch_fx_rates():
	b = _brief()
	with patch('urllib.request.urlopen') as mock_open:
		mock_open.return_value.__enter__.return_value.read.return_value = _FX_PAYLOAD
		result = b._fetch_fx()

	assert result['base'] == 'KES'
	assert 'USD' in result['rates']
	assert result['rates']['USD'] == pytest.approx(129.5, rel=1e-3)
	# EUR: 129.5 / 0.92 ≈ 140.76
	assert result['rates']['EUR'] == pytest.approx(129.5 / 0.92, rel=1e-2)


def test_fetch_fx_network_error():
	b = _brief()
	with patch('urllib.request.urlopen', side_effect=OSError('timeout')):
		result = b._fetch_fx()
	assert result['rates'] == {}
	assert 'error' in result


# ── Weather ───────────────────────────────────────────────────────────────────

_WTTR_PAYLOAD = json.dumps({
	'current_condition': [{
		'temp_C': '22', 'FeelsLikeC': '21', 'humidity': '60',
		'windspeedKmph': '15',
		'weatherDesc': [{'value': 'Partly cloudy'}],
	}],
	'weather': [{'maxtempC': '28', 'mintempC': '16', 'uvIndex': '7'}],
}).encode()


def test_weather_parses_correctly():
	b = _brief(config={'weather_location': 'Nairobi'})
	with patch('urllib.request.urlopen') as mock_open:
		mock_open.return_value.__enter__.return_value.read.return_value = _WTTR_PAYLOAD
		result = b._weather()

	assert result['location'] == 'Nairobi'
	assert result['temp_c'] == '22'
	assert result['condition'] == 'Partly cloudy'
	assert result['max_c'] == '28'


def test_weather_error_graceful():
	b = _brief()
	with patch('urllib.request.urlopen', side_effect=OSError('timeout')):
		result = b._weather()
	assert 'error' in result


# ── News ─────────────────────────────────────────────────────────────────────

def test_news_no_search_engine():
	b = _brief()
	result = b._news_digest('2026-06-13')
	assert result['summary'] == 'Search engine not configured.'


def test_news_digest_calls_search_and_llm():
	mock_search = MagicMock()
	mock_search.search.return_value = [
		{'title': 'CBK holds rate', 'body': 'Central Bank Kenya...', 'href': 'https://example.com'},
	]
	b = _brief(search=mock_search)
	result = b._news_digest('2026-06-13')

	assert mock_search.search.call_count >= 1
	# Verify at least one EA query was used
	all_queries = [call[0][0].lower() for call in mock_search.search.call_args_list]
	assert any(any(kw in q for kw in ['kenya', 'east africa', 'nairobi']) for q in all_queries)
	assert result['summary'] == 'LLM response.'
	# New structure: items dict with category keys
	assert 'items' in result
	assert 'ea' in result['items']


# ── Calendar ─────────────────────────────────────────────────────────────────

def test_calendar_no_store():
	b = _brief()
	result = b._calendar_summary('2026-06-13')
	assert result['today'] == []
	assert result['upcoming_7d'] == []


def test_calendar_uses_store():
	mock_store = MagicMock()
	mock_store.for_date.return_value = [
		{'title': 'Board meeting', 'date': '2026-06-13', 'time': '09:00', 'notes': '', '_type_meta': {'icon': '📅'}},
	]
	mock_store.upcoming.return_value = [
		{'title': 'RFP Deadline', 'date': '2026-06-18', '_type_meta': {'icon': '⚑'}},
	]
	b = _brief(calendar=mock_store)
	result = b._calendar_summary('2026-06-13')

	assert result['today_count'] == 1
	assert result['today'][0]['title'] == 'Board meeting'
	assert len(result['upcoming_7d']) == 1


# ── Todos ─────────────────────────────────────────────────────────────────────

def test_todos_local_files(tmp_path):
	todos_dir = tmp_path / 'todos'
	todos_dir.mkdir()
	(todos_dir / 'work.md').write_text(
		'# Work\n- [ ] Review contract 📅 2026-06-10\n- [x] Done already\n- [ ] Call supplier\n'
	)

	b = _brief()
	with patch('capabilities.daily_brief._TODOS_DIR', todos_dir):
		result = b._collect_todos('2025-01-15')

	assert result['count'] == 2
	texts = [i['text'] for i in result['items']]
	assert any('Review contract' in t for t in texts)
	assert any('Call supplier' in t for t in texts)
	# Completed item excluded
	assert not any('Done already' in t for t in texts)


def test_todos_overdue_sorted_first(tmp_path):
	todos_dir = tmp_path / 'todos'
	todos_dir.mkdir()
	(todos_dir / 'tasks.md').write_text(
		'- [ ] Future task due: 2099-01-01\n'
		'- [ ] Overdue task 📅 2020-01-01\n'
		'- [ ] No due date\n'
	)
	b = _brief()
	with patch('capabilities.daily_brief._TODOS_DIR', todos_dir):
		result = b._collect_todos('2025-01-15')

	assert result['overdue_count'] == 1
	assert result['items'][0]['text'] == 'Overdue task'


def test_todos_no_files(tmp_path):
	b = _brief()
	empty_dir = tmp_path / 'empty_todos'
	empty_dir.mkdir()
	with patch('capabilities.daily_brief._TODOS_DIR', empty_dir):
		result = b._collect_todos('2025-01-15')
	assert result['count'] == 0
	assert result['items'] == []


# ── Email ─────────────────────────────────────────────────────────────────────

def test_email_not_configured():
	b = _brief()
	result = b._email_summaries()
	assert result['summaries'] == []
	assert 'note' in result


def test_extract_email_body_plain():
	import email as em
	msg = em.message_from_string(
		'From: a@b.com\nSubject: Test\nContent-Type: text/plain\n\nHello world'
	)
	assert _extract_email_body(msg) == 'Hello world'


def test_extract_email_body_no_text():
	import email as em
	msg = em.message_from_string('From: a@b.com\nSubject: Test\n\n')
	assert _extract_email_body(msg) == ''


# ── generate() integration ────────────────────────────────────────────────────

def test_generate_returns_required_keys(tmp_path):
	empty_todos = tmp_path / 'todos'
	empty_todos.mkdir()
	b = _brief()
	with (
		patch('capabilities.daily_brief._TODOS_DIR', empty_todos),
		patch('urllib.request.urlopen', side_effect=OSError('offline')),
	):
		result = b.generate(date_str='2026-06-13', include_sections=['fx', 'todos'])

	assert result['status'] == 'ok'
	assert 'formatted_text' in result
	assert 'word_count' in result
	assert result['date'] == '2026-06-13'
	assert 'sections' in result


def test_generate_formatted_text_contains_date(tmp_path):
	empty_todos = tmp_path / 'todos'
	empty_todos.mkdir()
	b = _brief()
	with (
		patch('capabilities.daily_brief._TODOS_DIR', empty_todos),
		patch('urllib.request.urlopen', side_effect=OSError('offline')),
	):
		result = b.generate(date_str='2026-06-13', include_sections=['todos'])

	assert '2026' in result['formatted_text']


# ── Economic calendar ─────────────────────────────────────────────────────────

def test_economic_calendar_no_source():
	b = _brief()
	with patch('feedparser.parse', side_effect=Exception('no network')):
		result = b._economic_calendar('2026-06-13')
	assert 'events' in result


def test_economic_calendar_feedparser(tmp_path):
	# feedparser entries are FeedParserDict (dict subclass) — use plain dicts here
	fake_feed = SimpleNamespace(entries=[
		{'title': 'CBK Rate Decision', 'summary': 'CBK holds at 13%', 'published': '2026-06'},
		{'title': 'US CPI Release',    'summary': 'Inflation data',    'published': '2026-06'},
	])
	b = _brief()
	with patch('feedparser.parse', return_value=fake_feed):
		result = b._economic_calendar('2026-06-13')
	assert len(result['events']) == 2
	assert result['events'][0]['event'] == 'CBK Rate Decision'


# ── Formatting smoke test ────────────────────────────────────────────────────

def test_format_fx_table():
	b = _brief()
	brief = {
		'display_date': 'Friday, 13 June 2026',
		'sections': {
			'fx': {
				'rates': {'USD': 129.5, 'EUR': 140.76},
				'as_of': 'Fri, 13 Jun 2026',
				'source': 'open.er-api.com',
			},
			'synthesis': {},
		},
	}
	text = b._format(brief)
	assert 'USD' in text
	assert '129' in text
	assert 'FX Rates' in text


def test_format_todos_section():
	b = _brief()
	brief = {
		'display_date': 'Friday, 13 June 2026',
		'sections': {
			'todos': {
				'items': [
					{'text': 'Send proposal', 'source': 'work.md', 'due': '2026-06-14'},
				],
				'count': 1,
				'overdue_count': 0,
				'due_today_count': 0,
			},
			'synthesis': {},
		},
	}
	text = b._format(brief)
	assert 'Send proposal' in text
	assert 'due 2026-06-14' in text

# tests/ci/test_daily_brief.py
"""Tests for capabilities/daily_brief.py"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock, patch


def _make_brief(ai_response='- Key insight 1\n- Key insight 2', search_results=None):
	mock_ai = MagicMock()
	mock_ai.generate_text.return_value = ai_response
	mock_search = MagicMock()
	mock_search.search.return_value = search_results or [
		{'title': 'AI breakthrough 2025', 'href': 'https://example.com/ai',
		 'body': 'Researchers announce new LLM capabilities'},
		{'title': 'Kenya tech sector grows', 'href': 'https://example.com/ke',
		 'body': 'Nairobi tech hub expands significantly'},
	]
	from capabilities.daily_brief import DailyBrief
	return DailyBrief(mock_ai, search_engine=mock_search), mock_ai, mock_search


class TestDailyBriefGenerate:
	def test_returns_dict_with_status_ok(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert result['status'] == 'ok'

	def test_sections_populated(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert 'sections' in result
		assert 'news' in result['sections']

	def test_date_present(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert 'date' in result
		assert len(result['date']) > 5

	def test_generated_at_present(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert 'generated_at' in result

	def test_formatted_text_is_string(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert isinstance(result['formatted_text'], str)
		assert len(result['formatted_text']) > 10

	def test_word_count_positive(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert result['word_count'] > 0

	def test_include_sections_filter(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert 'news' in result['sections']
		assert 'fx' not in result['sections']

	def test_no_search_engine_graceful(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = '- Point 1'
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=None)
		result = brief.generate(include_sections=['news'])
		assert result['status'] == 'ok'


class TestNewsDigest:
	def test_articles_collected(self):
		brief, mock_ai, mock_search = _make_brief()
		mock_ai.generate_text.return_value = '- AI is growing fast\n- Business expanding'
		result = brief._news_digest('2026-06-13')
		assert 'items' in result
		assert 'summary' in result

	def test_no_search_engine_returns_summary_note(self):
		mock_ai = MagicMock()
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=None)
		result = brief._news_digest('2026-06-13')
		assert 'summary' in result

	def test_search_exception_handled(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = '- summary'
		mock_search = MagicMock()
		mock_search.search.side_effect = Exception('network error')
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=mock_search)
		result = brief._news_digest('2026-06-13')
		assert 'summary' in result  # graceful — returns note, not exception


class TestSynthesize:
	def test_empty_sections_returns_empty_lists(self):
		brief, _, _ = _make_brief()
		result = brief._synthesize({}, '2026-06-13')
		assert 'priorities' in result or 'raw' in result

	def test_sections_with_news_calls_llm(self):
		brief, mock_ai, _ = _make_brief()
		mock_ai.generate_text.return_value = '**Top 3 Priorities**\n1. Review AI policy\n2. Client call\n3. Budget'
		sections = {'news': {'summary': 'AI is growing. Businesses should adapt.'}}
		result = brief._synthesize(sections, '2026-06-13')
		assert 'raw' in result
		mock_ai.generate_text.assert_called_once()

	def test_no_news_section_skips_llm(self):
		brief, mock_ai, _ = _make_brief()
		result = brief._synthesize({}, '2026-06-13')
		mock_ai.generate_text.assert_not_called()

	def test_sections_used_count(self):
		brief, mock_ai, _ = _make_brief()
		mock_ai.generate_text.return_value = 'Priorities...'
		sections = {
			'news': {'summary': 'Important news today.'},
			'todos': {'count': 3, 'items': [{'text': 'Do X', 'due': None, 'source': 'local'}], 'overdue_count': 0},
		}
		result = brief._synthesize(sections, '2026-06-13')
		assert result.get('sections_used', 0) >= 2


class TestFormat:
	def test_formatted_text_has_heading(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news'])
		assert '# Daily Brief' in result['formatted_text']

	def test_formatted_text_has_news_section(self):
		brief, mock_ai, _ = _make_brief()
		mock_ai.generate_text.return_value = '- AI insight\n- Business update'
		result = brief.generate(include_sections=['news'])
		assert '## News' in result['formatted_text']

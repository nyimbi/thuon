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
		result = brief.generate(topics=['AI', 'business'])
		assert result['status'] == 'ok'

	def test_sections_populated(self):
		brief, _, _ = _make_brief()
		result = brief.generate()
		assert 'sections' in result
		assert 'news_summary' in result['sections']

	def test_date_present(self):
		brief, _, _ = _make_brief()
		result = brief.generate()
		assert 'date' in result
		assert len(result['date']) > 5

	def test_generated_at_present(self):
		brief, _, _ = _make_brief()
		result = brief.generate()
		assert 'generated_at' in result

	def test_formatted_text_is_string(self):
		brief, _, _ = _make_brief()
		result = brief.generate()
		assert isinstance(result['formatted_text'], str)
		assert len(result['formatted_text']) > 10

	def test_word_count_positive(self):
		brief, _, _ = _make_brief()
		result = brief.generate()
		assert result['word_count'] > 0

	def test_include_sections_filter(self):
		brief, _, _ = _make_brief()
		result = brief.generate(include_sections=['news_summary'])
		assert 'news_summary' in result['sections']
		assert 'market_pulse' not in result['sections']

	def test_no_search_engine_graceful(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = '- Point 1'
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=None)
		result = brief.generate()
		assert result['status'] == 'ok'


class TestNewsSummary:
	def test_articles_collected(self):
		brief, mock_ai, mock_search = _make_brief()
		mock_ai.generate_text.return_value = '- AI is growing fast\n- Business expanding'
		result = brief._news_summary(['AI', 'business'])
		assert 'items' in result
		assert 'summary' in result
		assert result['article_count'] >= 0

	def test_no_search_engine_returns_empty(self):
		mock_ai = MagicMock()
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=None)
		result = brief._news_summary(['AI'])
		assert result['article_count'] == 0

	def test_search_exception_handled(self):
		mock_ai = MagicMock()
		mock_ai.generate_text.return_value = '- summary'
		mock_search = MagicMock()
		mock_search.search.side_effect = Exception('network error')
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, search_engine=mock_search)
		result = brief._news_summary(['tech'])
		assert result['article_count'] == 0


class TestKnowledgeHighlights:
	def test_no_kb_pipeline_returns_note(self):
		mock_ai = MagicMock()
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, knowledge_pipeline=None)
		result = brief._knowledge_highlights(['AI'])
		assert 'note' in result

	def test_empty_kb_returns_note(self):
		mock_ai = MagicMock()
		mock_kb = MagicMock()
		mock_kb.chunk_count = 0
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, knowledge_pipeline=mock_kb)
		result = brief._knowledge_highlights(['AI'])
		assert 'note' in result

	def test_kb_with_content_returns_highlights(self):
		mock_ai = MagicMock()
		mock_kb = MagicMock()
		mock_kb.chunk_count = 10
		mock_kb.source_count = 2
		mock_kb.search.return_value = [
			{'score': 0.8, 'source': 'report.pdf', 'text': 'AI regulation overview...'},
		]
		from capabilities.daily_brief import DailyBrief
		brief = DailyBrief(mock_ai, knowledge_pipeline=mock_kb)
		result = brief._knowledge_highlights(['AI regulation'])
		assert len(result['highlights']) > 0


class TestActionItems:
	def test_action_items_from_news(self):
		brief, mock_ai, _ = _make_brief(ai_response='["Review AI policy", "Contact client"]')
		mock_ai.generate_text.return_value = '["Review AI policy", "Contact client"]'
		sections = {
			'news_summary': {'summary': 'AI is growing. Businesses should adapt.'}
		}
		result = brief._action_items(sections)
		assert 'items' in result
		assert isinstance(result['items'], list)

	def test_empty_news_returns_note(self):
		brief, _, _ = _make_brief()
		result = brief._action_items({'news_summary': {'summary': ''}})
		assert 'note' in result

	def test_no_news_section_returns_note(self):
		brief, _, _ = _make_brief()
		result = brief._action_items({})
		assert 'note' in result

	def test_items_capped_at_five(self):
		brief, mock_ai, _ = _make_brief()
		mock_ai.generate_text.return_value = json.dumps([f'action {i}' for i in range(10)])
		sections = {'news_summary': {'summary': 'There is lots of news today.'}}
		result = brief._action_items(sections)
		assert len(result['items']) <= 5


class TestFormat:
	def test_formatted_text_has_heading(self):
		brief, _, _ = _make_brief()
		result = brief.generate(topics=['tech'])
		assert '# Daily Brief' in result['formatted_text']

	def test_formatted_text_has_news_section(self):
		brief, mock_ai, _ = _make_brief()
		mock_ai.generate_text.return_value = '- AI insight\n- Business update'
		result = brief.generate(topics=['tech'])
		assert '## News Summary' in result['formatted_text']

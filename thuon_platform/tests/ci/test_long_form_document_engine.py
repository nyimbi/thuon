# tests/ci/test_long_form_document_engine.py
"""
Tests for LongFormDocumentEngine.

No LLM calls — uses a mock AIModel that returns deterministic JSON/text.
Covers: RefRegistry numbering, token resolution, audit, ToC generation,
section assembly, entity state updates, PDF render fallback.
"""

from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest

from capabilities.long_form_document_engine import (
	DocumentPlan,
	ExhibitSpec,
	GeneratedSection,
	LongFormDocumentEngine,
	RefRegistry,
	SectionSpec,
	_build_toc,
	_github_slug,
	_parse_headings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_plan() -> DocumentPlan:
	return DocumentPlan(
		title         = 'Digital Transformation Strategy',
		subtitle      = '2025 Edition',
		document_type = 'strategy',
		target_audience = 'C-suite executives',
		sections = [
			SectionSpec(
				id='executive_summary', title='Executive Summary',
				level=1, word_target=500, is_key=True,
			),
			SectionSpec(
				id='market_analysis', title='Market Analysis',
				level=1, word_target=2000,
				exhibits=[
					ExhibitSpec(
						id='market_size_table',
						type='table',
						title='Market Size by Segment 2024-2030',
						description='Revenue with CAGR',
					),
					ExhibitSpec(
						id='growth_chart',
						type='mermaid',
						title='Growth Trajectory',
						description='xychart-beta bar chart',
					),
				],
			),
			SectionSpec(
				id='market_segments', title='Market Segments',
				level=2, parent_id='market_analysis', word_target=800,
				dependencies=['market_analysis'],
			),
			SectionSpec(
				id='conclusions', title='Conclusions and Recommendations',
				level=1, word_target=600, is_key=True,
			),
		],
		total_word_target = 4000,
	)


def _make_mock_ai() -> MagicMock:
	ai = MagicMock()
	# Default: return a short paragraph (non-JSON for section generation)
	ai.generate_text.return_value = (
		'This section covers the key strategic considerations '
		'for the digital transformation initiative. '
		'Market data shows growth of **15% CAGR** through 2030. '
		'The **Total Addressable Market** is estimated at $45 billion. '
		'See [[SEC:market_analysis]] for detailed market breakdown and [[EX:market_size_table]] for data.'
	)
	return ai


# ---------------------------------------------------------------------------
# RefRegistry tests
# ---------------------------------------------------------------------------

class TestRefRegistry:

	def test_section_numbering_h1(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		assert reg.sections['executive_summary'] == '1'
		assert reg.sections['market_analysis'] == '2'
		# conclusions is the 3rd H1 (market_segments is H2, doesn't advance H1 counter)
		assert reg.sections['conclusions'] == '3'

	def test_section_numbering_h2_resets(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		# market_segments is level=2 under market_analysis (which is "2")
		assert reg.sections['market_segments'] == '2.1'

	def test_exhibit_flat_numbering(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		assert reg.exhibits['market_size_table'] == 'Exhibit 1'
		assert reg.exhibits['growth_chart'] == 'Exhibit 2'

	def test_token_resolution_sec(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		text = 'As discussed in [[SEC:market_analysis]], the market is large.'
		resolved = reg.resolve(text)
		assert '[[SEC:market_analysis]]' not in resolved
		assert 'Section 2' in resolved

	def test_token_resolution_ex(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		text = 'See [[EX:market_size_table]] for the breakdown.'
		resolved = reg.resolve(text)
		assert '[[EX:market_size_table]]' not in resolved
		assert 'Exhibit 1' in resolved

	def test_token_resolution_unknown_key(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		text = 'See [[SEC:nonexistent]] for details.'
		resolved = reg.resolve(text)
		assert '[§nonexistent]' in resolved

	def test_audit_bare_numbers_detected(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		# Resolved text should pass; bare numbers should fail
		clean = 'See Section 2 for details.'
		issues = reg.audit(clean)
		assert any('Bare number' in i for i in issues)

	def test_audit_tokens_not_flagged(self):
		# Tokens in raw LLM output are correct usage — audit should NOT flag them
		plan = _make_plan()
		reg = RefRegistry(plan)
		raw = 'See [[SEC:executive_summary]] and [[EX:market_size_table]] here.'
		issues = reg.audit(raw)
		assert issues == []

	def test_audit_clean_text_no_issues(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		# Audit operates on RAW LLM output (pre-resolution) to detect leakage
		raw = 'See [[SEC:executive_summary]] for overview.'
		issues = reg.audit(raw)
		assert issues == []  # tokens present but not bare numbers → no issues

	def test_prompt_block_contains_all_sections(self):
		plan = _make_plan()
		reg = RefRegistry(plan)
		block = reg.to_prompt_block()
		assert '[[SEC:executive_summary]]' in block
		assert '[[EX:market_size_table]]' in block


# ---------------------------------------------------------------------------
# ToC utilities tests
# ---------------------------------------------------------------------------

class TestToCUtilities:

	def test_github_slug_basic(self):
		assert _github_slug('Market Analysis') == 'market-analysis'

	def test_github_slug_strips_special(self):
		assert _github_slug('Q&A: Key Topics!') == 'qa-key-topics'

	def test_parse_headings_levels(self):
		md = '# Title\n## Subtitle\n### Sub-sub\n'
		headings = _parse_headings(md)
		assert len(headings) == 3
		assert headings[0]['level'] == 1
		assert headings[1]['level'] == 2
		assert headings[2]['level'] == 3

	def test_parse_headings_anchors(self):
		md = '# Executive Summary\n## Market Analysis\n'
		headings = _parse_headings(md)
		assert headings[0]['anchor'] == 'executive-summary'
		assert headings[1]['anchor'] == 'market-analysis'

	def test_parse_headings_deduplication(self):
		md = '## Analysis\n## Analysis\n'
		headings = _parse_headings(md)
		assert headings[0]['anchor'] == 'analysis'
		assert headings[1]['anchor'] == 'analysis-1'

	def test_build_toc_indent(self):
		md = '# H1\n## H2\n### H3\n'
		headings = _parse_headings(md)
		toc = _build_toc(headings)
		lines = toc.splitlines()
		# H2 gets 2-space indent, H3 gets 4-space indent
		h2_line = next(l for l in lines if 'H2' in l)
		h3_line = next(l for l in lines if 'H3' in l)
		assert h2_line.startswith('  -')
		assert h3_line.startswith('    -')

	def test_build_toc_links(self):
		md = '# Executive Summary\n'
		headings = _parse_headings(md)
		toc = _build_toc(headings)
		assert '[Executive Summary](#executive-summary)' in toc


# ---------------------------------------------------------------------------
# Entity state tests
# ---------------------------------------------------------------------------

class TestEntityState:

	def setup_method(self):
		self.ai = _make_mock_ai()
		self.engine = LongFormDocumentEngine(self.ai)

	def test_init_entity_state_keys(self):
		plan = _make_plan()
		state = self.engine._init_entity_state('Digital transformation', plan)
		assert 'defined_terms' in state
		assert 'key_statistics' in state
		assert 'topic' in state

	def test_update_entity_state_extracts_stats(self):
		plan = _make_plan()
		state = self.engine._init_entity_state('test', plan)
		self.engine._update_entity_state(state, 'Market grows at 15% CAGR through 2030.')
		assert any('15%' in s for s in state['key_statistics'])

	def test_update_entity_state_extracts_bold_terms(self):
		plan = _make_plan()
		state = self.engine._init_entity_state('test', plan)
		self.engine._update_entity_state(state, 'The **Total Addressable Market** is large.')
		assert 'Total Addressable Market' in state['defined_terms']

	def test_update_entity_state_caps_stats(self):
		plan = _make_plan()
		state = self.engine._init_entity_state('test', plan)
		# Add many stats
		for i in range(30):
			self.engine._update_entity_state(state, f'{i}% growth rate seen here')
		# Should be capped at 25
		assert len(state['key_statistics']) <= 25


# ---------------------------------------------------------------------------
# Engine integration (mock LLM) tests
# ---------------------------------------------------------------------------

class TestLongFormDocumentEngine:

	def setup_method(self):
		self.ai = _make_mock_ai()
		self.engine = LongFormDocumentEngine(self.ai)

	def test_generate_returns_required_keys(self):
		# Mock plan response
		plan = _make_plan()
		plan_json = plan.model_dump()
		# Serialize exhibits and sections for JSON response
		plan_dict = {
			'title': plan.title,
			'subtitle': plan.subtitle,
			'document_type': plan.document_type,
			'target_audience': plan.target_audience,
			'executive_summary_brief': 'Digital transformation drives value.',
			'total_word_target': 4000,
			'sections': [
				{
					'id': s.id, 'title': s.title, 'level': s.level,
					'parent_id': s.parent_id, 'key_points': s.key_points,
					'word_target': s.word_target, 'is_key': s.is_key,
					'exhibits': [
						{'id': e.id, 'type': e.type, 'title': e.title,
						 'description': e.description, 'data': e.data}
						for e in s.exhibits
					],
					'dependencies': s.dependencies,
				}
				for s in plan.sections
			],
		}
		self.ai.generate_text.return_value = json.dumps(plan_dict)
		result = self.engine.generate(
			topic='Digital Transformation',
			target_pages=5,
			save_output=False,
		)
		assert result['status'] == 'ok'
		for key in ('title', 'markdown', 'toc', 'word_count', 'section_count',
		            'exhibit_count', 'elapsed_seconds'):
			assert key in result

	def test_generate_toc_in_markdown(self):
		plan_dict = {
			'title': 'Test Doc', 'subtitle': '', 'document_type': 'report',
			'target_audience': '', 'executive_summary_brief': '',
			'total_word_target': 1000,
			'sections': [
				{'id': 'intro', 'title': 'Introduction', 'level': 1,
				 'parent_id': None, 'key_points': [], 'word_target': 500,
				 'is_key': False, 'exhibits': [], 'dependencies': []},
			],
		}
		self.ai.generate_text.return_value = json.dumps(plan_dict)
		result = self.engine.generate(topic='Test', target_pages=2, save_output=False)
		assert 'Table of Contents' in result['markdown']

	def test_generate_section_count_matches_plan(self):
		plan_dict = {
			'title': 'Report', 'subtitle': '', 'document_type': 'report',
			'target_audience': '', 'executive_summary_brief': '',
			'total_word_target': 2000,
			'sections': [
				{'id': f'sec_{i}', 'title': f'Section {i}', 'level': 1,
				 'parent_id': None, 'key_points': [], 'word_target': 400,
				 'is_key': False, 'exhibits': [], 'dependencies': []}
				for i in range(3)
			],
		}
		self.ai.generate_text.return_value = json.dumps(plan_dict)
		result = self.engine.generate(topic='Test', target_pages=5, save_output=False)
		assert result['section_count'] == 3

	def test_generate_fallback_plan_on_bad_json(self):
		self.ai.generate_text.return_value = 'not valid json at all {{'
		result = self.engine.generate(topic='Fallback test', target_pages=5, save_output=False)
		assert result['status'] == 'ok'
		assert result['section_count'] >= 4  # minimal plan has ≥4 sections

	def test_generate_tokens_resolved_in_output(self):
		# Section content contains tokens; they should be resolved in final markdown
		self.ai.generate_text.return_value = (
			'See [[SEC:intro]] for background and [[EX:data_table]] for the data.'
		)
		plan_dict = {
			'title': 'Token Test', 'subtitle': '', 'document_type': 'report',
			'target_audience': '', 'executive_summary_brief': '',
			'total_word_target': 1000,
			'sections': [
				{'id': 'intro', 'title': 'Introduction', 'level': 1,
				 'parent_id': None, 'key_points': [], 'word_target': 300,
				 'is_key': False,
				 'exhibits': [
					 {'id': 'data_table', 'type': 'table', 'title': 'Data Table',
					  'description': 'Key data', 'data': None}
				 ],
				 'dependencies': []},
			],
		}
		# First call returns the plan, subsequent calls return the section content
		call_count = [0]
		def side_effect(prompt):
			call_count[0] += 1
			if call_count[0] == 1:
				return json.dumps(plan_dict)
			return 'See [[SEC:intro]] for background and [[EX:data_table]] for the data.'
		self.ai.generate_text.side_effect = side_effect

		result = self.engine.generate(topic='Token Test', target_pages=2, save_output=False)
		# Tokens should be resolved
		assert '[[SEC:intro]]' not in result['markdown']
		assert '[[EX:data_table]]' not in result['markdown']
		assert 'Section 1' in result['markdown']
		assert 'Exhibit 1' in result['markdown']

	def test_minimal_plan_structure(self):
		plan = self.engine._minimal_plan('My Topic', 'report', 'executives', 10_000)
		assert plan.sections[0].id == 'executive_summary'
		assert plan.sections[0].is_key is True
		assert plan.sections[-1].is_key is True
		total = sum(s.word_target for s in plan.sections)
		# Total should be in ballpark of requested
		assert total > 5_000

	def test_pdf_render_returns_none_when_pandoc_missing(self, tmp_path):
		md_path = str(tmp_path / 'test.md')
		with open(md_path, 'w') as f:
			f.write('# Test\n\nHello world.\n')
		# If pandoc is not installed, should return None without raising
		result = self.engine._render_pdf(md_path)
		# May return a path (if pandoc available) or None — both acceptable
		assert result is None or result.endswith('.pdf')

	def test_save_markdown_creates_file(self, tmp_path):
		import capabilities.long_form_document_engine as mod
		original_dir = mod._OUTPUT_DIR
		mod._OUTPUT_DIR = tmp_path
		try:
			path = self.engine._save_markdown('My Test Document', '# Hello\n\nContent here.')
			assert path.endswith('.md')
			assert (tmp_path / path.split('/')[-1]).exists()
		finally:
			mod._OUTPUT_DIR = original_dir

	def test_rolling_context_caps_length(self):
		summaries = ['Section A: content here'] * 10
		generated: list[GeneratedSection] = []
		ctx = self.engine._build_rolling_context(summaries, generated)
		assert len(ctx) <= 4_100  # slight tolerance

	def test_key_section_uses_self_consistency(self):
		# is_key=True sections should call generate_text N=3 times
		# Return 600 words so word-count enforcement never fires extra calls
		plan = self.engine._minimal_plan('Topic', 'report', '', 2000)
		registry = RefRegistry(plan)
		entity_state = self.engine._init_entity_state('Topic', plan)
		key_sec = next(s for s in plan.sections if s.is_key)

		call_count = [0]
		def count_calls(prompt):
			call_count[0] += 1
			return 'word ' * 600
		self.ai.generate_text.side_effect = count_calls

		self.engine._generate_section(key_sec, plan, registry, '', entity_state, '', '', {})
		from capabilities.long_form_document_engine import _SELF_CONSISTENCY_N
		assert call_count[0] == _SELF_CONSISTENCY_N

	def test_non_key_section_single_call(self):
		plan = self.engine._minimal_plan('Topic', 'report', '', 2000)
		registry = RefRegistry(plan)
		entity_state = self.engine._init_entity_state('Topic', plan)
		non_key = next(s for s in plan.sections if not s.is_key)

		call_count = [0]
		def count_calls(prompt):
			call_count[0] += 1
			return 'word ' * 600
		self.ai.generate_text.side_effect = count_calls

		self.engine._generate_section(non_key, plan, registry, '', entity_state, '', '', {})
		assert call_count[0] == 1

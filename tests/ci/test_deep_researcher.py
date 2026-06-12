# tests/ci/test_deep_researcher.py

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_ai(response='{"summary": "Test summary.", "key_points": ["point1"]}'):
	ai = MagicMock()
	ai.generate_text.return_value = response
	ai.summarize_text.return_value = response
	return ai


def _mock_search(results=None):
	if results is None:
		results = [
			{'title': 'Source A', 'body': 'Content about topic A.', 'href': 'https://ex.com/a'},
			{'title': 'Source B', 'body': 'Content about topic B.', 'href': 'https://ex.com/b'},
			{'title': 'Source C', 'body': 'Content about topic C.', 'href': 'https://ex.com/c'},
		]
	se = MagicMock()
	se.search.return_value = results
	return se


def _make_deep_researcher(ai_response=None, search_results=None):
	from capabilities.deep_researcher import DeepResearcher
	ai = _mock_ai(ai_response or '{"summary": "Test.", "key_points": ["p1"]}')
	search = _mock_search(search_results)
	return DeepResearcher(ai_engine=ai, search_engine=search), ai, search


# ── RESEARCH_LEVELS constant ─────────────────────────────────────────────────

def test_research_levels_has_all_seven():
	from capabilities.deep_researcher import RESEARCH_LEVELS
	expected = {'quick', 'shallow', 'medium', 'deep', 'comprehensive', 'academic', 'phd'}
	assert expected == set(RESEARCH_LEVELS.keys())


def test_research_levels_labels_present():
	from capabilities.deep_researcher import RESEARCH_LEVELS
	for level, cfg in RESEARCH_LEVELS.items():
		assert 'label' in cfg, f'{level} missing label'


# ── quick level ───────────────────────────────────────────────────────────────

def test_quick_level_returns_dict():
	dr, ai, search = _make_deep_researcher()
	result = dr.research('What is quantum computing?', level='quick')
	assert isinstance(result, dict)
	assert result['level'] == 'quick'
	assert result['query'] == 'What is quantum computing?'
	assert 'elapsed_seconds' in result


def test_quick_level_calls_ai_not_search():
	dr, ai, search = _make_deep_researcher()
	dr.research('test query', level='quick')
	ai.generate_text.assert_called_once()
	search.search.assert_not_called()


# ── shallow level ─────────────────────────────────────────────────────────────

def test_shallow_level_calls_search():
	dr, ai, search = _make_deep_researcher()
	result = dr.research('climate change', level='shallow')
	assert isinstance(result, dict)
	search.search.assert_called_once()
	assert result['level'] == 'shallow'


def test_shallow_level_includes_source_count():
	dr, ai, search = _make_deep_researcher()
	result = dr.research('renewable energy', level='shallow')
	assert 'sources_searched' in result
	assert result['sources_searched'] >= 0


# ── medium / deep / comprehensive (agent loop) ───────────────────────────────

def test_medium_level_uses_agent_loop():
	dr, ai, search = _make_deep_researcher()
	mock_result = {
		'answer': 'Medium research answer.',
		'iterations': 5,
		'tool_calls': [],
		'elapsed_seconds': 2.1,
		'status': 'success',
	}
	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.return_value = mock_result
		mock_factory.return_value = mock_agent
		result = dr.research('AI in healthcare', level='medium')
	mock_factory.assert_called_once_with(max_iterations=10)
	assert result['level'] == 'medium'


def test_deep_level_uses_agent_loop_with_more_iterations():
	dr, ai, search = _make_deep_researcher()
	mock_result = {'answer': 'Deep answer.', 'iterations': 12, 'tool_calls': [], 'status': 'success', 'elapsed_seconds': 5.0}
	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.return_value = mock_result
		mock_factory.return_value = mock_agent
		result = dr.research('CRISPR gene editing', level='deep')
	mock_factory.assert_called_once_with(max_iterations=20)
	assert result['level'] == 'deep'


def test_comprehensive_level_uses_35_iterations():
	dr, ai, search = _make_deep_researcher()
	mock_result = {'answer': 'Comprehensive.', 'iterations': 20, 'tool_calls': [], 'status': 'success', 'elapsed_seconds': 8.0}
	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.return_value = mock_result
		mock_factory.return_value = mock_agent
		result = dr.research('blockchain scalability', level='comprehensive')
	mock_factory.assert_called_once_with(max_iterations=35)
	assert result['level'] == 'comprehensive'


# ── academic level ────────────────────────────────────────────────────────────

def test_academic_level_returns_phases():
	dr, ai, search = _make_deep_researcher(
		ai_response='["What is X?", "How does X work?", "What are X applications?", "What are X limitations?", "What is the future of X?"]'
	)

	def _agent_run_stub(query):
		return {'answer': f'Answer for: {query}', 'iterations': 3, 'tool_calls': [], 'status': 'success', 'elapsed_seconds': 1.0}

	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.side_effect = _agent_run_stub
		mock_factory.return_value = mock_agent

		# After decompose, AI returns plain text for syntheses/integration/critique/report
		ai_responses = [
			'["What is X?", "How does X work?", "What are X applications?", "What are X limitations?", "What is the future of X?"]',
			'Sub-question synthesis 1.',
			'Sub-question synthesis 2.',
			'Sub-question synthesis 3.',
			'Sub-question synthesis 4.',
			'Sub-question synthesis 5.',
			'Integrated analysis of all findings.',
			'{"strengths": ["good coverage"], "weaknesses": ["limited sources"], "overall_rating": 7}',
			'{"abstract": "This report covers X.", "conclusion": "X is important.", "research_quality_score": 7}',
		]
		dr.ai_engine.generate_text.side_effect = ai_responses
		result = dr.research('impact of AI on education', level='academic')

	assert isinstance(result, dict)
	assert result['level'] == 'academic'
	assert 'phases' in result
	phases = result['phases']
	assert 'decomposition' in phases
	assert isinstance(phases['decomposition'], list)
	assert len(phases['decomposition']) > 0


def test_academic_level_has_investigations():
	dr, ai, search = _make_deep_researcher()

	def _agent_run_stub(query):
		return {'answer': f'Finding for: {query}', 'iterations': 2, 'tool_calls': [], 'status': 'success', 'elapsed_seconds': 0.5}

	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.side_effect = _agent_run_stub
		mock_factory.return_value = mock_agent

		# LLM returns decomposition JSON for first call, text for rest
		ai_responses = (
			['["sub-q 1", "sub-q 2", "sub-q 3", "sub-q 4", "sub-q 5"]']
			+ ['Synthesis text.'] * 5
			+ ['Integrated analysis.']
			+ ['{"strengths": [], "overall_rating": 6}']
			+ ['{"abstract": "Abstract text.", "research_quality_score": 6}']
		)
		dr.ai_engine.generate_text.side_effect = ai_responses
		result = dr.research('climate policy effectiveness', level='academic')

	assert 'investigations' in result['phases']
	assert len(result['phases']['investigations']) > 0


# ── phd level ─────────────────────────────────────────────────────────────────

def test_phd_level_returns_phases_dict():
	dr, ai, search = _make_deep_researcher()

	json_responses = [
		# formulate_research_question
		'{"research_question": "How does AI affect education quality?", "research_objectives": ["obj1"], "scope": "K-12", "hypothesis": "AI improves outcomes"}',
		# define_scope
		'{"inclusion_criteria": ["peer-reviewed"], "exclusion_criteria": ["pre-2015"], "primary_keywords": ["AI", "education"], "secondary_keywords": ["learning"]}',
		# evaluate_sources
		'[{"url": "https://ex.com/a", "include": true, "relevance_score": 8, "reason": "highly relevant"}]',
		# thematic_analysis
		'{"themes": [{"theme_name": "Personalization", "description": "AI enables personalized learning", "supporting_sources": ["https://ex.com/a"], "evidence_strength": "strong"}], "dominant_paradigm": "constructivism"}',
		# map_contradictions
		'{"contradictions": [], "consensus_areas": ["AI improves engagement"], "contested_areas": ["long-term impact"]}',
		# gap_analysis
		'{"knowledge_gaps": [{"gap_description": "Longitudinal studies lacking", "significance": "high", "suggested_approach": "RCT"}], "priority_gaps": ["longitudinal data"]}',
		# original_synthesis
		'A novel synthesis: AI acts as a cognitive scaffold...',
		# write_thesis_chapter
		'{"title": "AI in Education", "abstract": "This chapter reviews AI in education.", "literature_review": "Extensive review...", "conclusion": "AI is beneficial.", "academic_quality_score": 8}',
		# self_critique
		'{"strengths": ["comprehensive"], "limitations": ["web sources only"], "overall_contribution": "Solid review"}',
	]
	dr.ai_engine.generate_text.side_effect = json_responses

	result = dr.research('impact of AI on K-12 education', level='phd')

	assert isinstance(result, dict)
	assert result['level'] == 'phd'
	assert 'phases' in result
	phases = result['phases']
	assert 'research_question' in phases
	assert 'scope' in phases
	assert 'search_vectors' in phases
	assert 'themes' in phases
	assert 'gaps' in phases


def test_phd_level_formulates_research_question():
	dr, ai, search = _make_deep_researcher()
	json_responses = [
		'{"research_question": "How does AI affect education quality?", "research_objectives": ["obj1"], "scope": "K-12"}',
		'{"inclusion_criteria": ["peer-reviewed"], "primary_keywords": ["AI"]}',
		'[{"url": "https://ex.com/a", "include": true, "relevance_score": 8}]',
		'{"themes": [], "dominant_paradigm": "empirical"}',
		'{"contradictions": [], "consensus_areas": [], "contested_areas": []}',
		'{"knowledge_gaps": [], "priority_gaps": []}',
		'Original synthesis text.',
		'{"title": "AI Education Review", "abstract": "Abstract.", "academic_quality_score": 7}',
		'{"strengths": [], "limitations": []}',
	]
	dr.ai_engine.generate_text.side_effect = json_responses

	result = dr.research('AI and student outcomes', level='phd')
	rq = result['phases']['research_question']
	assert isinstance(rq, dict)
	assert 'research_question' in rq or 'result' in rq  # fallback ok too


def test_phd_level_produces_self_critique():
	dr, ai, search = _make_deep_researcher()
	json_responses = [
		'{"research_question": "RQ", "scope": "broad"}',
		'{"inclusion_criteria": [], "primary_keywords": ["topic"]}',
		'[{"url": "https://ex.com/a", "include": true}]',
		'{"themes": [], "dominant_paradigm": "mixed"}',
		'{"contradictions": [], "consensus_areas": [], "contested_areas": []}',
		'{"knowledge_gaps": [], "priority_gaps": []}',
		'Synthesis.',
		'{"title": "Review", "abstract": "Abstract.", "academic_quality_score": 7}',
		'{"strengths": ["broad"], "limitations": ["limited sources"]}',
	]
	dr.ai_engine.generate_text.side_effect = json_responses

	result = dr.research('test topic', level='phd')
	assert 'limitations' in result
	assert 'self_critique' in result['phases']


# ── invalid level ─────────────────────────────────────────────────────────────

def test_invalid_level_returns_error():
	dr, ai, search = _make_deep_researcher()
	result = dr.research('test', level='turbo_ultra_mega')
	assert 'error' in result


# ── research_assistant integration with new levels ───────────────────────────

def test_research_assistant_quick_level_routes_to_deep_researcher():
	from capabilities.research_assistant import ResearchAssistant
	ai = _mock_ai('{"summary": "Quick answer.", "key_points": []}')
	search = _mock_search()
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)

	with patch('capabilities.deep_researcher.DeepResearcher.research') as mock_research:
		mock_research.return_value = {'summary': 'Quick answer.', 'level': 'quick', 'query': 'test', 'elapsed_seconds': 0.5}
		result = ra.perform_research('test', depth='quick')

	mock_research.assert_called_once_with('test', level='quick')
	assert isinstance(result, dict)


def test_research_assistant_academic_level_routes_to_deep_researcher():
	from capabilities.research_assistant import ResearchAssistant
	ai = _mock_ai()
	search = _mock_search()
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)

	with patch('capabilities.deep_researcher.DeepResearcher.research') as mock_research:
		mock_research.return_value = {
			'abstract': 'Academic abstract.',
			'phases': {'decomposition': ['q1', 'q2']},
			'level': 'academic',
			'query': 'AI governance',
			'elapsed_seconds': 12.3,
		}
		result = ra.perform_research('AI governance', depth='academic')

	mock_research.assert_called_once_with('AI governance', level='academic')
	assert result['level'] == 'academic'


def test_research_assistant_phd_level_routes_to_deep_researcher():
	from capabilities.research_assistant import ResearchAssistant
	ai = _mock_ai()
	search = _mock_search()
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)

	with patch('capabilities.deep_researcher.DeepResearcher.research') as mock_research:
		mock_research.return_value = {
			'title': 'Thesis Chapter',
			'abstract': 'PhD-level abstract.',
			'phases': {'research_question': {'research_question': 'RQ text'}},
			'level': 'phd',
			'query': 'quantum computing and cryptography',
			'elapsed_seconds': 45.0,
		}
		result = ra.perform_research('quantum computing and cryptography', depth='phd')

	mock_research.assert_called_once_with('quantum computing and cryptography', level='phd')
	assert result['level'] == 'phd'


def test_research_assistant_medium_still_uses_direct_agent_loop():
	"""medium/deep bypass DeepResearcher and use the direct agent loop path."""
	from capabilities.research_assistant import ResearchAssistant
	ai = _mock_ai()
	search = _mock_search()
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)

	mock_result = {'answer': 'Medium answer.', 'iterations': 5, 'tool_calls': [], 'status': 'success', 'elapsed_seconds': 3.0}
	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.return_value = mock_result
		mock_factory.return_value = mock_agent
		result = ra.perform_research('AI in medicine', depth='medium')

	mock_factory.assert_called_once_with(max_iterations=10)
	assert result['depth'] == 'medium'

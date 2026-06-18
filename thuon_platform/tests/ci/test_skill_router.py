# tests/ci/test_skill_router.py
"""
Unit tests for SkillRouter — BM25 routing and LLM disambiguation.
No network, LLM mocked.
"""

from __future__ import annotations

import pytest

from core.skill_registry import SkillManifest, SkillRegistry
from core.skill_router import SkillRouter, _score_gap


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_registry():
	SkillRegistry.reset()
	yield
	SkillRegistry.reset()


def _seed_registry() -> SkillRegistry:
	reg = SkillRegistry.get_instance()
	reg.bootstrap(
		{
			'research_assistant': {
				'description': 'Multi-depth web research on any topic',
				'method': 'perform_research',
				'params': [{'name': 'query', 'type': 'str', 'required': True}],
				'deps': ['ai_engine'],
				'module': 'capabilities.research_assistant',
				'class': 'ResearchAssistant',
			},
			'tender_scout': {
				'description': 'Search African government procurement tenders and RFPs',
				'method': 'search',
				'params': [{'name': 'sector', 'type': 'str', 'required': False}],
				'deps': ['search_engine'],
				'module': 'capabilities.tender_scout',
				'class': 'TenderScout',
			},
			'code_writer': {
				'description': 'Write, execute, and debug Python code with auto-install',
				'method': 'write_and_run',
				'params': [{'name': 'task_description', 'type': 'str', 'required': True}],
				'deps': ['ai_engine'],
				'module': 'capabilities.code_writer',
				'class': 'CodeWriter',
			},
			'daily_brief': {
				'description': 'Daily news and calendar digest',
				'method': 'generate',
				'params': [],
				'deps': ['ai_engine', 'search_engine'],
				'module': 'capabilities.daily_brief',
				'class': 'DailyBrief',
			},
		},
		{
			'research_assistant': 'research',
			'tender_scout': 'strategy',
			'code_writer': 'dev',
			'daily_brief': 'research',
		},
	)
	reg.augment_cli({
		'research_assistant': {
			'module': 'capabilities.research_assistant',
			'class': 'ResearchAssistant',
			'deps': ['ai_engine'],
			'method': 'perform_research',
			'description': 'Multi-depth web research',
			'keywords': ['research', 'investigate', 'find information', 'look up'],
			'example': 't.research_assistant(query="AI")',
		},
		'tender_scout': {
			'module': 'capabilities.tender_scout',
			'class': 'TenderScout',
			'deps': ['search_engine'],
			'method': 'search',
			'description': 'Search African procurement tenders',
			'keywords': ['tender', 'procurement', 'bid', 'government contract', 'RFP'],
			'example': 't.tender_scout(sector="ICT")',
		},
		'code_writer': {
			'module': 'capabilities.code_writer',
			'class': 'CodeWriter',
			'deps': ['ai_engine'],
			'method': 'write_and_run',
			'description': 'Write and run Python code',
			'keywords': ['code', 'script', 'python', 'program', 'automate'],
			'example': 't.code_writer(task="parse CSV")',
		},
	})
	return reg


class FakeAI:
	"""LLM that always picks the first option name it reads."""
	def generate_text(self, prompt: str) -> str:
		# Extract first "- name:" from the options block
		for line in prompt.splitlines():
			line = line.strip()
			if line.startswith('- '):
				return line.split(':')[0][2:].strip()
		return 'research_assistant'


class RejectingAI:
	"""LLM that returns garbage — router should fall back to BM25 winner."""
	def generate_text(self, prompt: str) -> str:
		return 'xxxxxxnotacapability'


# ── BM25 routing ──────────────────────────────────────────────────────────────

def test_route_tender_by_keyword():
	_seed_registry()
	router = SkillRouter()
	result = router.route('find government tenders in Kenya ICT sector')
	assert isinstance(result, SkillManifest)
	assert result.name == 'tender_scout'


def test_route_code_by_keyword():
	_seed_registry()
	router = SkillRouter()
	result = router.route('write a python script to parse CSV')
	assert isinstance(result, SkillManifest)
	assert result.name == 'code_writer'


def test_route_research_by_keyword():
	_seed_registry()
	router = SkillRouter()
	result = router.route('research AI trends in East Africa')
	assert isinstance(result, SkillManifest)
	assert result.name == 'research_assistant'


def test_route_top_k_returns_list():
	_seed_registry()
	router = SkillRouter()
	results = router.route('tender procurement bid government', top_k=3)
	assert isinstance(results, list)
	assert len(results) <= 3
	assert results[0].name == 'tender_scout'


def test_route_returns_fallback_on_no_match():
	_seed_registry()
	router = SkillRouter()
	result = router.route('xyzzy gibberish nonsense', fallback='research_assistant')
	assert result is not None
	assert result.name == 'research_assistant'


def test_route_empty_registry_returns_fallback():
	# No bootstrap — empty registry
	router = SkillRouter()
	result = router.route('find tenders', fallback='research_assistant')
	# Fallback not in registry either — should return None
	assert result is None


# ── LLM disambiguation ────────────────────────────────────────────────────────

def test_llm_disambiguate_invoked_on_close_scores():
	"""When BM25 top-2 are within 1 point, LLM should be consulted."""
	_seed_registry()
	# Add a second "research"-flavoured skill to create ambiguity
	SkillRegistry.get_instance()._manifests['deep_researcher'] = SkillManifest(
		name='deep_researcher',
		description='Deep research and investigation of any topic',
		module='capabilities.deep_researcher',
		class_name='DeepResearcher',
		method='research',
		keywords=['research', 'investigate', 'deep', 'comprehensive'],
		source='registry_cli',
	)

	fake_ai = FakeAI()
	router = SkillRouter(ai_engine=fake_ai)
	result = router.route('research investigate something deeply')
	# FakeAI picks the first option name; just verify routing completes
	assert isinstance(result, SkillManifest)
	assert result.name in ('research_assistant', 'deep_researcher')


def test_llm_disambiguation_failure_falls_back_to_bm25():
	"""If LLM returns garbage, BM25 winner is used."""
	_seed_registry()
	router = SkillRouter(ai_engine=RejectingAI())
	result = router.route('find government procurement tenders')
	assert result.name == 'tender_scout'


# ── route_with_params ─────────────────────────────────────────────────────────

def test_route_with_params_returns_tuple():
	_seed_registry()
	router = SkillRouter()
	cap_name, params = router.route_with_params('find ICT tenders in Kenya')
	assert isinstance(cap_name, str)
	assert isinstance(params, dict)
	assert cap_name == 'tender_scout'


def test_route_with_params_extracts_quoted():
	_seed_registry()
	router = SkillRouter()
	cap_name, params = router.route_with_params('research "AI trends in Africa"')
	assert cap_name == 'research_assistant'
	assert params.get('query') == 'AI trends in Africa'


def test_route_with_params_allowed_names_restriction():
	"""allowed_names must restrict routing to the given subset."""
	_seed_registry()
	router = SkillRouter()
	# Even though 'tender_scout' would win, it's excluded from allowed_names
	cap_name, _ = router.route_with_params(
		'find government procurement tenders',
		allowed_names={'research_assistant', 'code_writer'},
	)
	assert cap_name in ('research_assistant', 'code_writer')
	assert cap_name != 'tender_scout'


def test_route_with_params_allowed_names_picks_best_within_set():
	"""Within the allowed set, the best BM25 match wins."""
	_seed_registry()
	router = SkillRouter()
	cap_name, _ = router.route_with_params(
		'write a python script',
		allowed_names={'research_assistant', 'code_writer'},
	)
	assert cap_name == 'code_writer'


def test_route_with_params_llm_extracts_params(monkeypatch):
	"""When AI engine returns valid JSON, params are extracted from it."""
	_seed_registry()

	class JsonAI:
		def generate_text(self, prompt: str) -> str:
			return '{"capability": "tender_scout", "params": {"sector": "health", "countries": ["Kenya"]}}'

	router = SkillRouter(ai_engine=JsonAI())
	cap_name, params = router.route_with_params('find health tenders in Kenya')
	assert cap_name == 'tender_scout'
	assert params.get('sector') == 'health'


# ── _score_gap helper ─────────────────────────────────────────────────────────

def test_score_gap_identical_descriptions():
	a = SkillManifest(name='a', description='research web information', keywords=['research'])
	b = SkillManifest(name='b', description='research web information', keywords=['research'])
	gap = _score_gap('research web information', [a, b])
	assert gap == 0.0


def test_score_gap_clear_winner():
	a = SkillManifest(name='a', description='tender procurement bid government', keywords=['tender', 'bid'])
	b = SkillManifest(name='b', description='write python code script', keywords=['code'])
	gap = _score_gap('find government tender bids', [a, b])
	assert gap > 1

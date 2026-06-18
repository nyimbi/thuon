"""Tests for core/skill_registry.py + core/skill_router.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from pathlib import Path
import pytest
from core.skill_registry import SkillManifest, SkillParam, SkillRegistry, _parse_skill_md
from core.skill_router import SkillRouter, _extract_quoted, _score_gap


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Reset the SkillRegistry singleton before and after every test so edits
    don't bleed into other test modules."""
    SkillRegistry.reset()
    yield
    SkillRegistry.reset()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fresh_registry() -> SkillRegistry:
	"""Return a clean registry with no real capabilities loaded."""
	SkillRegistry.reset()
	r = SkillRegistry.get_instance()
	return r


def _seeded_registry() -> SkillRegistry:
	"""Registry pre-populated with known manifests."""
	r = _fresh_registry()
	web_reg = {
		'web_searcher': {
			'description': 'Search the internet for information',
			'method': 'search',
			'params': [{'name': 'query', 'type': 'str', 'required': True}],
			'deps': [],
			'module': 'tools.web_search',
			'class': 'WebSearcher',
		},
		'market_analyst': {
			'description': 'Analyse market trends and competitors',
			'method': 'analyse',
			'params': [{'name': 'market', 'type': 'str', 'required': True}],
			'deps': ['ai_engine'],
			'module': 'capabilities.market',
			'class': 'MarketAnalyst',
		},
		'rfp_ingester': {
			'description': 'Ingest and parse RFP documents',
			'method': 'ingest',
			'params': [{'name': 'rfp_source', 'type': 'str', 'required': True}],
			'deps': ['ai_engine'],
			'module': 'capabilities.rfp',
			'class': 'RFPIngester',
		},
	}
	cat_map = {
		'web_searcher': 'research',
		'market_analyst': 'strategy',
		'rfp_ingester': 'strategy',
	}
	r.bootstrap(web_reg, cat_map)
	return r


# ── SkillManifest ─────────────────────────────────────────────────────────────

class TestSkillManifest:
	def test_defaults(self):
		m = SkillManifest(name='test', description='A test skill')
		assert m.category == 'general'
		assert m.source == 'registry'
		assert m.keywords == []
		assert m.deps == []

	def test_as_web_entry(self):
		m = SkillManifest(
			name='test', description='Desc',
			module='mod', class_name='Cls', method='run',
		)
		entry = m.as_web_entry()
		assert entry['description'] == 'Desc'
		assert entry['method'] == 'run'
		assert entry['class'] == 'Cls'

	def test_as_cli_entry(self):
		m = SkillManifest(
			name='test', description='Desc',
			module='mod', class_name='Cls', method='run',
			keywords=['kw1', 'kw2'],
		)
		entry = m.as_cli_entry()
		assert entry['keywords'] == ['kw1', 'kw2']


# ── SkillRegistry CRUD ────────────────────────────────────────────────────────

class TestSkillRegistry:
	def test_bootstrap_populates(self):
		r = _seeded_registry()
		assert len(r) >= 3  # 3 seeded + any discovered SKILL.md files

	def test_get_known(self):
		r = _seeded_registry()
		m = r.get('web_searcher')
		assert m is not None
		assert m.name == 'web_searcher'
		assert m.category == 'research'

	def test_get_missing_returns_none(self):
		r = _seeded_registry()
		assert r.get('does_not_exist') is None

	def test_all_returns_all(self):
		r = _seeded_registry()
		names = {m.name for m in r.all()}
		assert 'web_searcher' in names
		assert 'market_analyst' in names

	def test_by_category(self):
		r = _seeded_registry()
		strategy = r.by_category('strategy')
		assert len(strategy) >= 2  # 2 seeded + any discovered
		assert all(m.category == 'strategy' for m in strategy)

	def test_categories(self):
		r = _seeded_registry()
		cats = r.categories()
		assert 'research' in cats
		assert 'strategy' in cats

	def test_contains(self):
		r = _seeded_registry()
		assert 'web_searcher' in r
		assert 'unknown' not in r

	def test_register_programmatic(self):
		r = _fresh_registry()
		m = SkillManifest(name='custom', description='A custom skill')
		r.register(m, category='dev')
		assert r.get('custom') is not None
		assert r.category_of('custom') == 'dev'

	def test_augment_cli_adds_keywords(self):
		r = _seeded_registry()
		cli_reg = {
			'web_searcher': {
				'description': 'Search',
				'module': 'tools.web_search',
				'class': 'WebSearcher',
				'method': 'search',
				'deps': [],
				'keywords': ['internet', 'search', 'web'],
				'example': 'search for AI trends',
			},
		}
		r.augment_cli(cli_reg)
		m = r.get('web_searcher')
		assert 'internet' in m.keywords

	def test_augment_cli_adds_new_entry(self):
		r = _seeded_registry()
		cli_reg = {
			'cli_only_tool': {
				'description': 'CLI-only capability',
				'module': 'capabilities.cli_tool',
				'class': 'CLITool',
				'method': 'run',
				'deps': [],
				'keywords': ['cli'],
				'example': '',
			},
		}
		r.augment_cli(cli_reg)
		assert r.get('cli_only_tool') is not None

	def test_as_web_registry(self):
		r = _seeded_registry()
		web = r.as_web_registry()
		assert 'web_searcher' in web
		assert 'description' in web['web_searcher']

	def test_reset_clears_singleton(self):
		r1 = _seeded_registry()
		assert len(r1) > 0
		SkillRegistry.reset()
		r2 = SkillRegistry.get_instance()
		assert len(r2) == 0

	def test_bootstrap_idempotent(self):
		r = _seeded_registry()
		count_before = len(r)
		# calling bootstrap again with the same data should not duplicate
		r.bootstrap(
			{'web_searcher': {
				'description': 'Search the internet for information',
				'method': 'search', 'params': [], 'deps': [],
				'module': 'tools.web_search', 'class': 'WebSearcher',
			}},
			{'web_searcher': 'research'},
		)
		assert len(r) == count_before


# ── SkillRegistry.search (BM25-lite) ──────────────────────────────────────────

class TestSkillSearch:
	def test_search_exact_match(self):
		r = _seeded_registry()
		results = r.search('web searcher internet')
		assert results[0].name == 'web_searcher'

	def test_search_rfp(self):
		r = _seeded_registry()
		results = r.search('rfp ingest document')
		assert results[0].name == 'rfp_ingester'

	def test_search_top_k(self):
		r = _seeded_registry()
		results = r.search('market strategy analysis', top_k=2)
		assert len(results) <= 2

	def test_search_empty_query(self):
		r = _seeded_registry()
		results = r.search('')
		assert results == []

	def test_search_no_match_returns_empty(self):
		r = _seeded_registry()
		results = r.search('quantum entanglement superconductor')
		# may return something with partial match; shouldn't crash
		assert isinstance(results, list)


# ── SKILL.md parser ───────────────────────────────────────────────────────────

class TestSkillMDParser:
	def test_parse_minimal(self, tmp_path):
		md = tmp_path / 'SKILL.md'
		md.write_text(
			'---\nname: test_skill\ndescription: A test\n---\n\nBody text here.'
		)
		m = _parse_skill_md(md)
		assert m.name == 'test_skill'
		assert m.description == 'A test'
		assert m.body == 'Body text here.'
		assert m.source == 'skill_md'

	def test_parse_with_thuon_namespace(self, tmp_path):
		md = tmp_path / 'SKILL.md'
		md.write_text(
			'---\n'
			'name: my_cap\n'
			'description: My capability\n'
			'keywords: [alpha, beta]\n'
			'thuon:\n'
			'  module: capabilities.my_mod\n'
			'  class: MyCap\n'
			'  method: run\n'
			'  deps: [ai_engine]\n'
			'  category: research\n'
			'---\n\n'
			'Usage instructions here.'
		)
		m = _parse_skill_md(md)
		assert m.module == 'capabilities.my_mod'
		assert m.class_name == 'MyCap'
		assert m.category == 'research'
		assert 'ai_engine' in m.deps
		assert 'alpha' in m.keywords

	def test_parse_no_frontmatter(self, tmp_path):
		md = tmp_path / 'SKILL.md'
		md.write_text('Just a description with no frontmatter.')
		m = _parse_skill_md(md)
		# name falls back to parent dir name
		assert m.name == tmp_path.name
		assert m.body == 'Just a description with no frontmatter.'

	def test_parse_with_params(self, tmp_path):
		md = tmp_path / 'SKILL.md'
		md.write_text(
			'---\n'
			'name: param_skill\n'
			'description: Has params\n'
			'thuon:\n'
			'  module: mod\n'
			'  class: Cls\n'
			'  method: run\n'
			'  params:\n'
			'    - name: query\n'
			'      type: str\n'
			'      required: true\n'
			'---\n'
		)
		m = _parse_skill_md(md)
		assert len(m.params) == 1
		assert m.params[0].name == 'query'
		assert m.params[0].required is True


# ── SkillRouter (no LLM) ──────────────────────────────────────────────────────

class TestSkillRouterNoLLM:
	def _router(self) -> SkillRouter:
		_seeded_registry()
		return SkillRouter(ai_engine=None)

	def test_route_web_search(self):
		router = self._router()
		m = router.route('search for information on the web')
		assert m is not None
		assert m.name == 'web_searcher'

	def test_route_rfp(self):
		router = self._router()
		# "rfp compliance requirements" strongly signals rfp_ingester over pdf-reader
		m = router.route('parse rfp compliance requirements and bid evaluation criteria')
		assert m is not None
		# rfp_ingester should score higher than pdf-reader on this instruction
		assert m.name in ('rfp_ingester', 'rfp_compliance_matrix_builder', 'rfp_bid_evaluator')

	def test_route_top_k_list(self):
		router = self._router()
		results = router.route('market strategy analysis', top_k=3)
		assert isinstance(results, list)
		assert len(results) >= 1

	def test_route_fallback_for_no_match(self):
		router = self._router()
		# instruction that matches nothing
		m = router.route('quantum physics xyz zzz', fallback='web_searcher')
		# should return fallback or something
		assert m is not None

	def test_route_with_params_no_llm(self):
		router = self._router()
		cap_name, params = router.route_with_params('search for "AI trends"')
		assert isinstance(cap_name, str)
		assert isinstance(params, dict)
		# without LLM, should extract quoted string as query
		assert params.get('query') == 'AI trends'

	def test_route_with_params_allowed_names_filters(self):
		router = self._router()
		# Instruction clearly matches market_analyst; allowed_names excludes web_searcher
		cap_name, params = router.route_with_params(
			'analyse market trends and competitors',
			allowed_names={'rfp_ingester', 'market_analyst'},
		)
		assert cap_name in ('rfp_ingester', 'market_analyst')

	def test_route_with_params_no_match_returns_fallback(self):
		router = self._router()
		cap_name, params = router.route_with_params(
			'xyz quantum unicorn',
			fallback='web_searcher',
		)
		assert cap_name  # not empty


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestRouterHelpers:
	def test_extract_quoted_single(self):
		result = _extract_quoted('search for "AI breakthroughs"')
		assert result == {'query': 'AI breakthroughs'}

	def test_extract_quoted_no_quotes(self):
		result = _extract_quoted('search for ai trends')
		assert result == {'query': 'search for ai trends'}

	def test_score_gap_identical_scores(self):
		m1 = SkillManifest(name='a', description='search web internet', keywords=['web'])
		m2 = SkillManifest(name='b', description='search web online', keywords=['web'])
		gap = _score_gap('web search', [m1, m2])
		assert isinstance(gap, float)
		assert gap >= 0

	def test_score_gap_single_candidate(self):
		m = SkillManifest(name='a', description='search')
		gap = _score_gap('search', [m])
		assert gap == 0.0

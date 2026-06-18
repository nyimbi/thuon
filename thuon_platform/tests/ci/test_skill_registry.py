# tests/ci/test_skill_registry.py
"""
Unit tests for SkillRegistry and SkillManifest.
No network, no LLM, no filesystem side-effects beyond tmp_path.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.skill_registry import (
	SkillManifest,
	SkillParam,
	SkillRegistry,
	_parse_skill_md,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
	"""Isolate every test — fresh singleton and no real skills-dir discovery."""
	import core.skill_registry as sr
	monkeypatch.setattr(sr, '_SKILL_DIRS', [])
	SkillRegistry.reset()
	yield
	SkillRegistry.reset()


_MINIMAL_WEB_REGISTRY = {
	'research_assistant': {
		'description': 'Multi-depth web research on any topic',
		'method': 'perform_research',
		'params': [{'name': 'research_query', 'type': 'str', 'required': True}],
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'module': 'capabilities.research_assistant',
		'class': 'ResearchAssistant',
	},
	'code_writer': {
		'description': 'Write, execute, and debug Python code',
		'method': 'write_and_run',
		'params': [{'name': 'task_description', 'type': 'str', 'required': True}],
		'deps': ['ai_engine'],
		'module': 'capabilities.code_writer',
		'class': 'CodeWriter',
	},
	'daily_brief': {
		'description': 'Generate a daily digest of news and calendar',
		'method': 'generate',
		'params': [],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.daily_brief',
		'class': 'DailyBrief',
	},
}

_MINIMAL_CATEGORY_MAP = {
	'research_assistant': 'research',
	'code_writer': 'dev',
	'daily_brief': 'research',
}

_MINIMAL_CLI_REGISTRY = {
	'research_assistant': {
		'module': 'capabilities.research_assistant',
		'class': 'ResearchAssistant',
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'method': 'perform_research',
		'description': 'Multi-depth web research on any topic',
		'keywords': ['research', 'investigate', 'find information'],
		'example': 't.research_assistant(query="AI trends")',
	},
	'tender_scout': {
		'module': 'capabilities.tender_scout',
		'class': 'TenderScout',
		'deps': ['search_engine'],
		'method': 'search',
		'description': 'Search African procurement tenders',
		'keywords': ['tender', 'procurement', 'bid', 'government contract'],
		'example': 't.tender_scout(sector="ICT")',
	},
}


# ── SkillManifest ─────────────────────────────────────────────────────────────

def test_skill_manifest_creation():
	m = SkillManifest(name='foo', description='Does foo things')
	assert m.name == 'foo'
	assert m.description == 'Does foo things'
	assert m.deps == []
	assert m.keywords == []
	assert m.source == 'registry'


def test_skill_manifest_as_web_entry():
	m = SkillManifest(
		name='foo',
		description='Does foo',
		module='capabilities.foo',
		class_name='Foo',
		method='run',
		deps=['ai_engine'],
		params=[SkillParam(name='topic', type='str', required=True)],
	)
	entry = m.as_web_entry()
	assert entry['class'] == 'Foo'
	assert entry['module'] == 'capabilities.foo'
	assert entry['method'] == 'run'
	assert entry['params'][0]['name'] == 'topic'
	assert 'class_name' not in entry


def test_skill_manifest_as_cli_entry():
	m = SkillManifest(
		name='tender_scout',
		description='Find tenders',
		module='capabilities.tender_scout',
		class_name='TenderScout',
		method='search',
		deps=['search_engine'],
		keywords=['tender', 'procurement'],
		example='t.tender_scout(sector="ICT")',
	)
	entry = m.as_cli_entry()
	assert entry['class'] == 'TenderScout'
	assert entry['keywords'] == ['tender', 'procurement']
	assert entry['example'] == 't.tender_scout(sector="ICT")'
	assert 'params' not in entry


# ── SkillRegistry — bootstrap ─────────────────────────────────────────────────

def test_bootstrap_loads_all_entries():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	assert len(reg) == 3
	assert 'research_assistant' in reg
	assert 'code_writer' in reg


def test_bootstrap_sets_category():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	assert reg.category_of('research_assistant') == 'research'
	assert reg.category_of('code_writer') == 'dev'
	assert reg.category_of('unknown') == 'general'


def test_bootstrap_params_parsed():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	m = reg.get('research_assistant')
	assert m is not None
	assert len(m.params) == 1
	assert m.params[0].name == 'research_query'
	assert m.params[0].required is True


def test_bootstrap_source_tag():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	assert reg.get('research_assistant').source == 'registry_web'


# ── SkillRegistry — augment_cli ───────────────────────────────────────────────

def test_augment_cli_adds_keywords_to_existing():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	reg.augment_cli(_MINIMAL_CLI_REGISTRY)

	m = reg.get('research_assistant')
	assert 'research' in m.keywords
	assert m.example == 't.research_assistant(query="AI trends")'


def test_augment_cli_adds_cli_only_cap():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	reg.augment_cli(_MINIMAL_CLI_REGISTRY)

	assert 'tender_scout' in reg
	m = reg.get('tender_scout')
	assert m.source == 'registry_cli'
	assert 'procurement' in m.keywords


def test_augment_cli_does_not_overwrite_existing_keywords():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)

	# Pre-seed keywords manually
	existing = reg.get('research_assistant')
	reg._manifests['research_assistant'] = existing.model_copy(
		update={'keywords': ['already', 'set']}
	)

	reg.augment_cli(_MINIMAL_CLI_REGISTRY)
	# Should not overwrite
	assert reg.get('research_assistant').keywords == ['already', 'set']


# ── SkillRegistry — search ────────────────────────────────────────────────────

def test_search_returns_relevant_results():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	reg.augment_cli(_MINIMAL_CLI_REGISTRY)

	results = reg.search('find government procurement tenders Kenya')
	names = [m.name for m in results]
	assert 'tender_scout' in names
	assert names.index('tender_scout') == 0  # should rank first


def test_search_returns_empty_for_no_match():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	results = reg.search('xyzzy unrelated gibberish')
	assert results == []


def test_search_respects_top_k():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	reg.augment_cli(_MINIMAL_CLI_REGISTRY)
	results = reg.search('research', top_k=1)
	assert len(results) == 1


def test_search_empty_query():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	results = reg.search('')
	assert results == []


# ── SkillRegistry — by_category ───────────────────────────────────────────────

def test_by_category():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	research_caps = reg.by_category('research')
	names = [m.name for m in research_caps]
	assert 'research_assistant' in names
	assert 'daily_brief' in names
	assert 'code_writer' not in names


# ── _parse_skill_md ───────────────────────────────────────────────────────────

def test_parse_skill_md_full(tmp_path):
	skill_dir = tmp_path / 'my_skill'
	skill_dir.mkdir()
	(skill_dir / 'SKILL.md').write_text(textwrap.dedent("""\
		---
		name: my_skill
		description: Does something great
		keywords: [great, something, useful]
		thuon:
		  module: capabilities.my_module
		  class: MyClass
		  method: run
		  deps: [ai_engine]
		  category: research
		  params:
		    - name: topic
		      type: str
		      required: true
		    - name: depth
		      type: str
		      required: false
		      default: medium
		---

		Use this skill when the user wants to do something great.
		Trigger phrases: "do something great", "run my skill".
	"""))

	manifest = _parse_skill_md(skill_dir / 'SKILL.md')
	assert manifest.name == 'my_skill'
	assert manifest.description == 'Does something great'
	assert manifest.module == 'capabilities.my_module'
	assert manifest.class_name == 'MyClass'
	assert manifest.method == 'run'
	assert manifest.deps == ['ai_engine']
	assert manifest.category == 'research'
	assert manifest.keywords == ['great', 'something', 'useful']
	assert len(manifest.params) == 2
	assert manifest.params[0].name == 'topic'
	assert manifest.params[0].required is True
	assert manifest.params[1].default == 'medium'
	assert manifest.source == 'skill_md'
	assert 'Trigger phrases' in manifest.body


def test_parse_skill_md_no_frontmatter(tmp_path):
	skill_dir = tmp_path / 'bare'
	skill_dir.mkdir()
	(skill_dir / 'SKILL.md').write_text('A skill without frontmatter.')
	manifest = _parse_skill_md(skill_dir / 'SKILL.md')
	# Falls back to directory name
	assert manifest.name == 'bare'
	assert manifest.body == 'A skill without frontmatter.'


def test_parse_skill_md_minimal_frontmatter(tmp_path):
	skill_dir = tmp_path / 'minimal'
	skill_dir.mkdir()
	(skill_dir / 'SKILL.md').write_text('---\nname: minimal\ndescription: Minimal skill\n---\nBody text.')
	manifest = _parse_skill_md(skill_dir / 'SKILL.md')
	assert manifest.name == 'minimal'
	assert manifest.description == 'Minimal skill'
	assert manifest.body == 'Body text.'


# ── SKILL.md filesystem discovery ────────────────────────────────────────────

def test_skill_md_discovery_overrides_registry(tmp_path, monkeypatch):
	"""A SKILL.md file should override the registry entry for the same name."""
	import core.skill_registry as sr

	skill_dir = tmp_path / 'skills'
	(skill_dir / 'research_assistant').mkdir(parents=True)
	(skill_dir / 'research_assistant' / 'SKILL.md').write_text(textwrap.dedent("""\
		---
		name: research_assistant
		description: Overridden by SKILL.md
		thuon:
		  module: capabilities.research_assistant
		  class: ResearchAssistant
		  method: perform_research
		  deps: [ai_engine]
		  category: research
		---
	"""))

	monkeypatch.setattr(sr, '_SKILL_DIRS', [skill_dir])

	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)

	m = reg.get('research_assistant')
	assert m.description == 'Overridden by SKILL.md'
	assert m.source == 'skill_md'


def test_skill_md_discovery_adds_new_skill(tmp_path, monkeypatch):
	"""A SKILL.md for an unknown name adds a new capability."""
	import core.skill_registry as sr

	skill_dir = tmp_path / 'skills'
	(skill_dir / 'email_composer').mkdir(parents=True)
	(skill_dir / 'email_composer' / 'SKILL.md').write_text(textwrap.dedent("""\
		---
		name: email_composer
		description: Compose professional emails
		keywords: [email, compose, draft, write email]
		thuon:
		  module: capabilities.email_composer
		  class: EmailComposer
		  method: compose
		  deps: [ai_engine]
		  category: content
		---
	"""))

	monkeypatch.setattr(sr, '_SKILL_DIRS', [skill_dir])

	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)

	assert 'email_composer' in reg
	m = reg.get('email_composer')
	assert m.source == 'skill_md'
	assert m.category == 'content'
	assert 'email' in m.keywords


def test_skill_md_bad_file_skipped(tmp_path, monkeypatch, caplog):
	"""Malformed SKILL.md should be logged and skipped, not crash bootstrap."""
	import core.skill_registry as sr
	import logging

	skill_dir = tmp_path / 'skills'
	(skill_dir / 'bad').mkdir(parents=True)
	# Properly fenced so frontmatter IS parsed — but the YAML inside is invalid
	(skill_dir / 'bad' / 'SKILL.md').write_text('---\nbad: [unclosed yaml\n---\nbody\n')

	monkeypatch.setattr(sr, '_SKILL_DIRS', [skill_dir])

	reg = SkillRegistry.get_instance()
	with caplog.at_level(logging.WARNING, logger='thuon.skill_registry'):
		reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)

	# Registry still loaded the valid entries
	assert len(reg) == 3
	assert any('bad' in r.message for r in caplog.records)


# ── Backward-compat views ─────────────────────────────────────────────────────

def test_as_web_registry_shape():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	web = reg.as_web_registry()
	assert 'research_assistant' in web
	entry = web['research_assistant']
	assert 'class' in entry
	assert 'module' in entry
	assert 'params' in entry
	assert isinstance(entry['params'], list)


def test_as_cli_registry_only_executable():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	# Add a SKILL.md-only skill with no module/class
	reg._manifests['prompt_only'] = SkillManifest(
		name='prompt_only',
		description='No Python class',
		source='skill_md',
	)
	cli = reg.as_cli_registry()
	assert 'research_assistant' in cli
	assert 'prompt_only' not in cli  # excluded — no module/class/method


def test_as_category_map():
	reg = SkillRegistry.get_instance()
	reg.bootstrap(_MINIMAL_WEB_REGISTRY, _MINIMAL_CATEGORY_MAP)
	cat_map = reg.as_category_map()
	assert cat_map['research_assistant'] == 'research'
	assert cat_map['code_writer'] == 'dev'

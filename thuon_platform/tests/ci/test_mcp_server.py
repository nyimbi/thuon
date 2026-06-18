# tests/ci/test_mcp_server.py
"""
Unit tests for ThuonMCPServer and build_mcp_blueprint.
Uses Flask test client — no real capability execution, no network.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from flask import Flask

from core.mcp_server import (
	ThuonMCPServer,
	_manifest_to_tool,
	_params_to_json_schema,
	build_mcp_blueprint,
)
from core.skill_registry import SkillManifest, SkillParam, SkillRegistry


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
	import core.skill_registry as sr
	monkeypatch.setattr(sr, '_SKILL_DIRS', [])
	SkillRegistry.reset()
	yield
	SkillRegistry.reset()


def _seed_registry() -> None:
	SkillRegistry.get_instance().bootstrap(
		{
			'research_assistant': {
				'description': 'Multi-depth research',
				'method': 'perform_research',
				'params': [
					{'name': 'query', 'type': 'str', 'required': True},
					{'name': 'depth', 'type': 'str', 'required': False, 'default': 'medium'},
				],
				'deps': ['ai_engine'],
				'module': 'capabilities.research_assistant',
				'class': 'ResearchAssistant',
			},
			'daily_brief': {
				'description': 'Daily news and calendar digest',
				'method': 'generate',
				'params': [],
				'deps': ['ai_engine'],
				'module': 'capabilities.daily_brief',
				'class': 'DailyBrief',
			},
		},
		{'research_assistant': 'research', 'daily_brief': 'research'},
	)


@pytest.fixture
def app():
	"""Flask test app with MCP blueprint registered."""
	_seed_registry()
	flask_app = Flask(__name__)
	flask_app.config['TESTING'] = True

	fake_instance = MagicMock()
	fake_instance.perform_research.return_value = {'summary': 'AI is evolving', 'sources': []}
	fake_instance.generate.return_value = {'brief': 'Today in brief...'}

	def factory(cap_name: str):
		return fake_instance

	flask_app.register_blueprint(build_mcp_blueprint(factory))
	return flask_app


@pytest.fixture
def client(app):
	return app.test_client()


def _rpc(method: str, params: dict | None = None, rpc_id: int = 1) -> dict:
	return {'jsonrpc': '2.0', 'id': rpc_id, 'method': method, 'params': params or {}}


# ── _params_to_json_schema ────────────────────────────────────────────────────

def test_params_to_schema_required():
	params = [SkillParam(name='topic', type='str', required=True)]
	schema = _params_to_json_schema(params)
	assert schema['required'] == ['topic']
	assert schema['properties']['topic']['type'] == 'string'


def test_params_to_schema_optional_with_default():
	params = [SkillParam(name='depth', type='str', required=False, default='medium')]
	schema = _params_to_json_schema(params)
	assert 'required' not in schema
	assert schema['properties']['depth']['default'] == 'medium'


def test_params_to_schema_type_mapping():
	params = [
		SkillParam(name='count', type='int', required=False),
		SkillParam(name='enabled', type='bool', required=False),
		SkillParam(name='items', type='list', required=False),
	]
	schema = _params_to_json_schema(params)
	assert schema['properties']['count']['type'] == 'integer'
	assert schema['properties']['enabled']['type'] == 'boolean'
	assert schema['properties']['items']['type'] == 'array'


def test_params_to_schema_choices_become_enum():
	params = [SkillParam(name='mode', type='str', required=False, choices=['quick', 'deep'])]
	schema = _params_to_json_schema(params)
	assert schema['properties']['mode']['enum'] == ['quick', 'deep']


def test_params_to_schema_empty():
	schema = _params_to_json_schema([])
	assert schema == {'type': 'object', 'properties': {}}


# ── _manifest_to_tool ─────────────────────────────────────────────────────────

def test_manifest_to_tool_name_prefix():
	m = SkillManifest(name='daily_brief', description='Daily digest',
	                  module='x', class_name='X', method='run')
	tool = _manifest_to_tool(m)
	assert tool['name'] == 'thuon__daily_brief'


def test_manifest_to_tool_has_input_schema():
	m = SkillManifest(
		name='foo', description='Foo',
		module='x', class_name='X', method='run',
		params=[SkillParam(name='topic', type='str', required=True)],
	)
	tool = _manifest_to_tool(m)
	assert 'inputSchema' in tool
	assert tool['inputSchema']['required'] == ['topic']


# ── GET /mcp ─────────────────────────────────────────────────────────────────

def test_get_mcp_returns_server_info(client):
	resp = client.get('/mcp')
	assert resp.status_code == 200
	data = resp.get_json()
	assert data['name'] == 'thuon'
	assert data['tools_count'] == 2


# ── POST /mcp — initialize ────────────────────────────────────────────────────

def test_initialize_returns_protocol_version(client):
	resp = client.post('/mcp', json=_rpc('initialize'))
	assert resp.status_code == 200
	data = resp.get_json()
	assert data['result']['protocolVersion'] == '2024-11-05'
	assert data['result']['serverInfo']['name'] == 'thuon'
	assert 'tools' in data['result']['capabilities']


def test_initialize_id_echoed(client):
	resp = client.post('/mcp', json=_rpc('initialize', rpc_id=42))
	assert resp.get_json()['id'] == 42


# ── POST /mcp — tools/list ────────────────────────────────────────────────────

def test_tools_list_returns_all_caps(client):
	resp = client.post('/mcp', json=_rpc('tools/list'))
	assert resp.status_code == 200
	tools = resp.get_json()['result']['tools']
	names = [t['name'] for t in tools]
	assert 'thuon__research_assistant' in names
	assert 'thuon__daily_brief' in names


def test_tools_list_tool_has_required_fields(client):
	resp = client.post('/mcp', json=_rpc('tools/list'))
	tool = next(
		t for t in resp.get_json()['result']['tools']
		if t['name'] == 'thuon__research_assistant'
	)
	assert 'description' in tool
	assert 'inputSchema' in tool
	assert tool['inputSchema']['required'] == ['query']


def test_tools_list_excludes_manifest_only_skills(client, monkeypatch):
	"""Skills without module/class (SKILL.md-only) must not appear as tools."""
	reg = SkillRegistry.get_instance()
	reg._manifests['prompt_only'] = SkillManifest(
		name='prompt_only', description='No Python class', source='skill_md'
	)
	resp = client.post('/mcp', json=_rpc('tools/list'))
	names = [t['name'] for t in resp.get_json()['result']['tools']]
	assert 'thuon__prompt_only' not in names


# ── POST /mcp — tools/call ────────────────────────────────────────────────────

def test_tools_call_executes_capability(client):
	resp = client.post('/mcp', json=_rpc('tools/call', {
		'name': 'thuon__research_assistant',
		'arguments': {'query': 'AI trends', 'depth': 'deep'},
	}))
	assert resp.status_code == 200
	content = resp.get_json()['result']['content']
	assert content[0]['type'] == 'text'
	assert 'AI is evolving' in content[0]['text']


def test_tools_call_unknown_tool_returns_error(client):
	resp = client.post('/mcp', json=_rpc('tools/call', {'name': 'unknown__tool'}))
	assert resp.status_code in (200, 500)
	data = resp.get_json()
	assert 'error' in data


def test_tools_call_missing_prefix_returns_error(client):
	resp = client.post('/mcp', json=_rpc('tools/call', {'name': 'research_assistant'}))
	data = resp.get_json()
	assert 'error' in data


def test_tools_call_result_is_json_text(client):
	resp = client.post('/mcp', json=_rpc('tools/call', {
		'name': 'thuon__daily_brief',
		'arguments': {},
	}))
	content = resp.get_json()['result']['content'][0]['text']
	parsed = json.loads(content)
	assert parsed['brief'] == 'Today in brief...'


# ── POST /mcp — unknown method ────────────────────────────────────────────────

def test_unknown_method_returns_method_not_found(client):
	resp = client.post('/mcp', json=_rpc('unknown/method'))
	data = resp.get_json()
	assert data['error']['code'] == -32601


def test_notifications_initialized_returns_204(client):
	resp = client.post('/mcp', json=_rpc('notifications/initialized'))
	assert resp.status_code == 204

# core/mcp_server.py
"""
MCP (Model Context Protocol) server — exposes all SkillRegistry capabilities
as tools callable by Claude or any MCP-compatible client.

Implements the JSON-RPC 2.0 / streamable-HTTP transport (MCP spec 2024-11-05).

Single endpoint: POST /mcp

Supported methods:
  initialize   — handshake, returns server capabilities
  tools/list   — returns all registered Thuon capabilities as MCP tool defs
  tools/call   — executes a capability and returns the result as text content

Tools are named  thuon__{capability_name}  (double-underscore namespace prefix).

Usage (wire into Flask app)::

  from core.mcp_server import build_mcp_blueprint
  app.register_blueprint(build_mcp_blueprint(instance_factory))

Where `instance_factory(cap_name) -> object` instantiates a capability class.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, request

from core.skill_registry import SkillManifest, SkillParam, SkillRegistry

logger = logging.getLogger('thuon.mcp_server')

_TOOL_PREFIX = 'thuon__'

# Sentinel returned by _dispatch() for notification methods (no response needed)
_NOTIFICATION = object()


class _MCPMethodNotFound(Exception):
    pass
_MCP_VERSION = '2024-11-05'


# ── JSON Schema helpers ────────────────────────────────────────────────────────

_TYPE_MAP: dict[str, str] = {
	'str':    'string',
	'string': 'string',
	'int':    'integer',
	'float':  'number',
	'bool':   'boolean',
	'list':   'array',
	'dict':   'object',
	'text':   'string',
	'select': 'string',
	'textarea': 'string',
	'number': 'number',
	'checkbox': 'boolean',
}


def _params_to_json_schema(params: list[SkillParam]) -> dict[str, Any]:
	"""Convert SkillParam list to a JSON Schema object."""
	properties: dict[str, Any] = {}
	required: list[str] = []

	for p in params:
		json_type = _TYPE_MAP.get(p.type, 'string')
		prop: dict[str, Any] = {'type': json_type}

		if p.choices:
			prop['enum'] = p.choices
		elif p.options:
			prop['enum'] = p.options

		if p.default is not None:
			prop['default'] = p.default

		properties[p.name] = prop
		if p.required:
			required.append(p.name)

	schema: dict[str, Any] = {'type': 'object', 'properties': properties}
	if required:
		schema['required'] = required
	return schema


def _manifest_to_tool(m: SkillManifest) -> dict[str, Any]:
	return {
		'name':        f'{_TOOL_PREFIX}{m.name}',
		'description': m.description,
		'inputSchema': _params_to_json_schema(m.params),
	}


# ── MCP server class ──────────────────────────────────────────────────────────

class ThuonMCPServer:
	"""
	Handles MCP JSON-RPC requests against the SkillRegistry.

	Args:
		instance_factory: Callable(cap_name: str) -> capability_instance.
		                  Reuses the web app's _build_instance() so no
		                  duplicate DI wiring is needed.
	"""

	def __init__(self, instance_factory: Callable[[str], Any]) -> None:
		self._factory  = instance_factory
		self._registry = SkillRegistry.get_instance()

	# ── JSON-RPC dispatch ─────────────────────────────────────────────────────

	def _dispatch(self, method: str, params: dict) -> Any:
		"""Route a JSON-RPC method. Returns result dict or _NOTIFICATION sentinel."""
		if method == 'initialize':
			return self._initialize(params)
		if method == 'tools/list':
			return self._tools_list(params)
		if method == 'tools/call':
			return self._tools_call(params)
		if method == 'notifications/initialized':
			return _NOTIFICATION
		raise _MCPMethodNotFound(method)

	def handle(self) -> Response:
		body   = request.get_json(force=True, silent=True) or {}
		method = body.get('method', '')
		rpc_id = body.get('id')
		params = body.get('params') or {}

		try:
			result = self._dispatch(method, params)
		except _MCPMethodNotFound:
			return jsonify({
				'jsonrpc': '2.0',
				'id':      rpc_id,
				'error':   {'code': -32601, 'message': f'Method not found: {method}'},
			})
		except Exception as exc:
			logger.error('MCP method %s failed: %s', method, exc)
			return jsonify({
				'jsonrpc': '2.0',
				'id':      rpc_id,
				'error':   {'code': -32603, 'message': str(exc)},
			}), 500

		if result is _NOTIFICATION:
			return Response(status=204)
		return jsonify({'jsonrpc': '2.0', 'id': rpc_id, 'result': result})

	# ── Method handlers ───────────────────────────────────────────────────────

	def _initialize(self, params: dict) -> dict[str, Any]:
		return {
			'protocolVersion': _MCP_VERSION,
			'capabilities': {'tools': {}},
			'serverInfo': {'name': 'thuon', 'version': '1.0'},
		}

	def _tools_list(self, params: dict) -> dict[str, Any]:
		tools = [
			_manifest_to_tool(m)
			for m in self._registry.all()
			if m.module and m.class_name and m.method
		]
		logger.debug('MCP tools/list: returning %d tools', len(tools))
		return {'tools': tools}

	def _tools_call(self, params: dict) -> dict[str, Any]:
		tool_name = params.get('name', '')
		arguments = params.get('arguments') or {}

		if not tool_name.startswith(_TOOL_PREFIX):
			raise ValueError(f'Unknown tool: {tool_name!r}')

		cap_name = tool_name[len(_TOOL_PREFIX):]
		manifest = self._registry.get(cap_name)
		if manifest is None:
			raise ValueError(f'Unknown capability: {cap_name!r}')

		instance = self._factory(cap_name)
		method   = getattr(instance, manifest.method)
		sig      = inspect.signature(method)
		kwargs   = {k: v for k, v in arguments.items() if k in sig.parameters}

		result = method(**kwargs)

		text = (
			json.dumps(result, default=str, indent=2)
			if isinstance(result, (dict, list))
			else str(result)
		)
		return {'content': [{'type': 'text', 'text': text}]}


# ── Flask blueprint factory ───────────────────────────────────────────────────

def build_mcp_blueprint(instance_factory: Callable[[str], Any]) -> Blueprint:
	"""
	Build and return the Flask blueprint for the MCP endpoint.

	Register with::

	  app.register_blueprint(build_mcp_blueprint(_build_instance))
	"""
	bp     = Blueprint('mcp', __name__)
	server = ThuonMCPServer(instance_factory)

	@bp.route('/mcp', methods=['POST'])
	def mcp_endpoint() -> Response:
		return server.handle()

	@bp.route('/mcp', methods=['GET'])
	def mcp_info() -> Response:
		"""Lightweight discovery endpoint — returns server info."""
		return jsonify({
			'name':    'thuon',
			'version': '1.0',
			'mcp_version': _MCP_VERSION,
			'tools_count': len([
				m for m in SkillRegistry.get_instance().all()
				if m.module and m.class_name and m.method
			]),
			'endpoint': '/mcp',
		})

	return bp


# ── Stdio transport ───────────────────────────────────────────────────────────

def run_mcp_stdio(instance_factory: Callable[[str], Any]) -> None:
	"""
	Run the MCP server over stdio (for Claude Desktop integration).

	Reads newline-delimited JSON-RPC requests from stdin, writes responses to stdout.
	All logging goes to stderr so it doesn't pollute the protocol stream.

	Claude Desktop config (~/.config/Claude/claude_desktop_config.json):
	  "mcpServers": {
	    "thuon": {
	      "command": "uv",
	      "args": ["run", "python", "thuon_platform/main.py", "mcp"]
	    }
	  }
	"""
	import sys

	server = ThuonMCPServer(instance_factory)
	logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
	logger.info('Thuon MCP stdio transport started')

	for raw_line in sys.stdin:
		raw_line = raw_line.strip()
		if not raw_line:
			continue
		rpc_id: Any = None
		method = ''
		try:
			body   = json.loads(raw_line)
			rpc_id = body.get('id') if isinstance(body, dict) else None
			method = body.get('method', '') if isinstance(body, dict) else ''
			params = (body.get('params') or {}) if isinstance(body, dict) else {}
			result = server._dispatch(method, params)
			if result is _NOTIFICATION:
				continue
			response = {'jsonrpc': '2.0', 'id': rpc_id, 'result': result}
		except json.JSONDecodeError as exc:
			response = {
				'jsonrpc': '2.0', 'id': None,
				'error': {'code': -32700, 'message': f'Parse error: {exc}'},
			}
		except _MCPMethodNotFound:
			response = {
				'jsonrpc': '2.0', 'id': rpc_id,
				'error': {'code': -32601, 'message': f'Method not found: {method}'},
			}
		except Exception as exc:
			logger.error('MCP stdio error: %s', exc)
			response = {
				'jsonrpc': '2.0', 'id': rpc_id,
				'error': {'code': -32603, 'message': str(exc)},
			}

		sys.stdout.write(json.dumps(response) + '\n')
		sys.stdout.flush()

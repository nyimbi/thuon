# core/fleet_inventory.py
"""
Config-driven server catalog.

Reads the `fleet` section of config.yaml (via SettingsManager) and exposes
ServerInfo objects for use by sysadmin capabilities.

Default fleet (hardcoded fallback) covers the 10 Contabo VPS nodes defined
in infra/docs.  Any server listed in config.yaml overrides these defaults.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.sysadmin_types import FleetConfigError, ServerInfo

logger = logging.getLogger('thuon.fleet_inventory')

# ── Default fleet (matches infra/docs; override via config.yaml fleet.servers) ─

_DEFAULT_SERVERS: list[dict[str, Any]] = [
	{'ip': '109.123.244.151', 'hostname': 'easf',      'role': 'production',   'tags': ['web', 'app', 'caddy']},
	{'ip': '144.91.122.29',   'hostname': 'db-main',   'role': 'database',     'tags': ['postgres', 'primary']},
	{'ip': '144.91.112.190',  'hostname': 'db-backup', 'role': 'database',     'tags': ['postgres', 'standby']},
	{'ip': '62.84.181.55',    'hostname': 'auth',       'role': 'auth',         'tags': ['keycloak', 'spicedb', 'minio', 'redis', 'temporal', 'decommission']},
	{'ip': '62.169.25.77',    'hostname': 'ml',         'role': 'gateway',      'tags': ['traefik', 'openbao', 'ollama', 'litellm', 'tts']},
	{'ip': '217.76.53.144',   'hostname': 'mail',       'role': 'observability','tags': ['stalwart', 'grafana', 'prometheus', 'loki']},
	{'ip': '84.247.181.100',  'hostname': 'search',     'role': 'connectors',   'tags': ['searxng', 'firecrawl', 'docling', 'soketi']},
	{'ip': '37.60.225.7',     'hostname': 'docfusion',  'role': 'app',          'tags': ['docfusion', 'datacraft']},
	{'ip': '84.247.166.219',  'hostname': 'meguard',    'role': 'app',          'tags': ['meguard']},
	{'ip': '84.46.253.178',   'hostname': 'uasl',       'role': 'empty',        'tags': ['reinstall']},
]


class FleetInventory:
	"""
	Loads and caches ServerInfo objects from config + defaults.

	Usage::

		inv = FleetInventory()
		servers = inv.all()
		prod    = inv.by_tag('web')
		db      = inv.by_role('database')
		srv     = inv.get('easf')   # by hostname or IP
	"""

	def __init__(self, config: dict[str, Any] | None = None) -> None:
		self._servers: list[ServerInfo] = []
		self._lock = threading.Lock()
		self._load(config)

	def _load(self, config: dict[str, Any] | None) -> None:
		fleet_cfg: dict[str, Any] = {}
		if config:
			fleet_cfg = config.get('fleet', {}) or {}
		else:
			try:
				from core.settings_manager import SettingsManager
				sm = SettingsManager()
				fleet_cfg = sm.get('fleet') or {}
			except Exception:
				fleet_cfg = {}

		default_user     = fleet_cfg.get('ssh_user', 'root')
		default_key_file = fleet_cfg.get('ssh_key_file', '~/.ssh/id_ed25519')
		default_port     = int(fleet_cfg.get('ssh_port', 22))

		raw_servers: list[dict] = fleet_cfg.get('servers', []) or _DEFAULT_SERVERS

		with self._lock:
			self._servers = []
			for entry in raw_servers:
				if not entry.get('ip'):
					logger.warning('Fleet entry missing ip: %s', entry)
					continue
				self._servers.append(ServerInfo(
					ip=entry['ip'],
					hostname=entry.get('hostname', entry['ip']),
					role=entry.get('role', 'unknown'),
					tags=list(entry.get('tags', [])),
					ssh_user=entry.get('ssh_user', default_user),
					ssh_key_file=entry.get('ssh_key_file', default_key_file),
					ssh_port=int(entry.get('ssh_port', default_port)),
				))
		logger.debug('FleetInventory loaded %d servers', len(self._servers))

	def all(self) -> list[ServerInfo]:
		with self._lock:
			return list(self._servers)

	def by_role(self, role: str) -> list[ServerInfo]:
		with self._lock:
			return [s for s in self._servers if s.role == role]

	def by_tag(self, tag: str) -> list[ServerInfo]:
		with self._lock:
			return [s for s in self._servers if tag in s.tags]

	def get(self, name: str) -> ServerInfo | None:
		"""Find by hostname (exact or prefix) or by IP."""
		with self._lock:
			for s in self._servers:
				if s.hostname == name or s.ip == name or s.hostname.startswith(name):
					return s
		return None

	def resolve(self, hosts: str | list[str] | None) -> list[ServerInfo]:
		"""
		Resolve a flexible host spec to a list of ServerInfo.

		- None / 'all'  → all servers
		- 'role:database' → servers by role
		- 'tag:postgres'  → servers by tag
		- 'easf'          → single server by hostname/IP
		- ['easf', 'ml']  → multiple by name
		"""
		if hosts is None or hosts == 'all':
			return self.all()
		if isinstance(hosts, list):
			results = []
			for h in hosts:
				s = self.get(h)
				if s:
					results.append(s)
				else:
					logger.warning('Unknown host: %s', h)
			return results
		if isinstance(hosts, str):
			if hosts.startswith('role:'):
				return self.by_role(hosts[5:])
			if hosts.startswith('tag:'):
				return self.by_tag(hosts[4:])
			s = self.get(hosts)
			return [s] if s else []
		return []


# ── Module-level singleton ────────────────────────────────────────────────────

_inventory: FleetInventory | None = None
_inv_lock = threading.Lock()


def get_fleet_inventory(config: dict[str, Any] | None = None) -> FleetInventory:
	global _inventory
	with _inv_lock:
		if _inventory is None:
			_inventory = FleetInventory(config)
	return _inventory

# capabilities/service_status_checker.py
"""
Check systemd service status across the fleet.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_on_fleet
from core.sysadmin_types import ServiceStatus

logger = logging.getLogger('thuon.service_status_checker')


def _make_status_cmd(service: str) -> str:
	return (
		f'systemctl show {service} '
		'--property=ActiveState,SubState,LoadState,Description '
		'--no-pager 2>/dev/null || '
		f'echo "LoadState=not-found ActiveState=inactive SubState=dead"'
	)


def _parse_status(srv_hostname: str, srv_ip: str, service: str, stdout: str) -> ServiceStatus:
	props: dict[str, str] = {}
	for line in stdout.splitlines():
		if '=' in line:
			k, _, v = line.partition('=')
			props[k.strip()] = v.strip()
	return ServiceStatus(
		hostname=srv_hostname,
		ip=srv_ip,
		service=service,
		active_state=props.get('ActiveState', ''),
		sub_state=props.get('SubState', ''),
		load_state=props.get('LoadState', ''),
		raw_output=stdout[:500],
	)


class ServiceStatusChecker:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def check(
		self,
		service: str,
		hosts: str | list[str] | None = 'all',
	) -> dict[str, Any]:
		"""
		Check the status of *service* across the fleet.

		Returns:
			{service, statuses: [ServiceStatus.dict()], running_count,
			 failed_count, not_found_count}
		"""
		inventory = get_fleet_inventory()
		servers = inventory.resolve(hosts)
		if not servers:
			return {'error': f'No servers matched: {hosts!r}', 'statuses': []}

		cmd = _make_status_cmd(service)
		results = run_on_fleet(servers, cmd, timeout=20)

		statuses: list[ServiceStatus] = []
		for srv, res in zip(servers, results):
			if not res.success and not res.stdout:
				statuses.append(ServiceStatus(
					hostname=srv.hostname, ip=srv.ip, service=service,
					reachable=False, error=res.stderr or 'SSH failed',
				))
			else:
				s = _parse_status(srv.hostname, srv.ip, service, res.stdout)
				statuses.append(s)

		return {
			'service':        service,
			'statuses':       [s.model_dump() for s in statuses],
			'running_count':  sum(1 for s in statuses if s.active_state == 'active'),
			'failed_count':   sum(1 for s in statuses if s.active_state == 'failed'),
			'not_found_count':sum(1 for s in statuses if s.load_state == 'not-found'),
			'inactive_count': sum(1 for s in statuses if s.active_state == 'inactive'),
		}

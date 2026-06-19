# capabilities/service_manager.py
"""
Manage systemd services on remote hosts.  All mutating operations default
to dry_run=True — pass dry_run=False explicitly to actually execute.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command, run_on_fleet
from core.sysadmin_types import CommandResult

logger = logging.getLogger('thuon.service_manager')

_ALLOWED_ACTIONS = {'start', 'stop', 'restart', 'reload', 'enable', 'disable',
					'status', 'is-active', 'is-enabled', 'journal'}

_READ_ONLY_ACTIONS = {'status', 'is-active', 'is-enabled', 'journal'}


class ServiceManager:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def manage(
		self,
		action: str,
		service: str,
		host: str | list[str] | None = None,
		dry_run: bool = True,
		journal_lines: int = 50,
	) -> dict[str, Any]:
		"""
		Run a systemctl action on *service* on the specified host(s).

		Args:
			action:       One of: start stop restart reload enable disable
			              status is-active is-enabled journal
			service:      systemd unit name (e.g. 'caddy', 'postgresql')
			host:         hostname, IP, role:X, tag:X, or list; None → all
			dry_run:      If True (default), return the command without running it
			journal_lines: Lines of journal output to fetch for 'journal' action

		Returns:
			{action, service, dry_run, results: [CommandResult.dict()]}
		"""
		action = action.lower().strip()
		if action not in _ALLOWED_ACTIONS:
			return {
				'error': f'Invalid action {action!r}. Allowed: {sorted(_ALLOWED_ACTIONS)}',
				'action': action, 'service': service,
			}

		is_read_only = action in _READ_ONLY_ACTIONS

		if action == 'journal':
			cmd = f'journalctl -u {service} -n {journal_lines} --no-pager 2>/dev/null'
		else:
			cmd = f'systemctl {action} {service} --no-pager 2>/dev/null'

		if dry_run and not is_read_only:
			inventory = get_fleet_inventory()
			servers = inventory.resolve(host)
			return {
				'action':    action,
				'service':   service,
				'dry_run':   True,
				'planned_command': cmd,
				'target_hosts': [s.hostname for s in servers],
				'results':   [],
			}

		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No servers matched: {host!r}', 'results': []}

		raw_results = run_on_fleet(servers, cmd, timeout=30)
		results = [r.model_dump() for r in raw_results]

		return {
			'action':  action,
			'service': service,
			'dry_run': False,
			'results': results,
			'success_count': sum(1 for r in raw_results if r.success),
			'fail_count':    sum(1 for r in raw_results if not r.success),
		}

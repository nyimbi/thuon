# capabilities/firewall_manager.py
"""
UFW firewall management.  Read-only by default; mutations require dry_run=False.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command, run_on_fleet

logger = logging.getLogger('thuon.firewall_manager')

_ALLOWED_ACTIONS = {'status', 'list_rules', 'audit', 'allow', 'deny', 'delete',
					'enable', 'disable', 'reset'}

_READ_ONLY_ACTIONS = {'status', 'list_rules', 'audit'}

# Ports that must never be blocked (SSH)
_PROTECTED_PORTS = {22, 2222}


class FirewallManager:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def manage(
		self,
		action: str,
		host: str | list[str] | None = None,
		port: int | str | None = None,
		proto: str = 'tcp',
		from_ip: str = 'any',
		comment: str = '',
		dry_run: bool = True,
	) -> dict[str, Any]:
		"""
		Manage UFW firewall rules on remote host(s).

		Actions:
		  status      — ufw status verbose
		  list_rules  — numbered rules list
		  audit       — status + open ports + AI analysis of exposure
		  allow       — allow port/proto (dry_run=True default)
		  deny        — deny port/proto (dry_run=True default)
		  delete      — delete a rule by rule number or spec
		  enable      — enable ufw (dry_run=True default)
		  disable     — disable ufw (dry_run=True default)

		Args:
			action:   firewall action
			host:     target server(s); None = all
			port:     port number or range (e.g. 443, '8000:8010', 'Nginx Full')
			proto:    tcp or udp (default tcp)
			from_ip:  source IP or CIDR for allow/deny (default 'any')
			dry_run:  True = show command only (default for mutating actions)

		Returns:
			{action, results: [...], analysis: str}
		"""
		action = action.lower().strip()
		if action not in _ALLOWED_ACTIONS:
			return {'error': f'Unknown action {action!r}. Allowed: {sorted(_ALLOWED_ACTIONS)}'}

		is_read_only = action in _READ_ONLY_ACTIONS

		# Safety: refuse to deny port 22
		if action == 'deny' and port in _PROTECTED_PORTS:
			return {'error': f'Refusing to block port {port} — this would lock you out of SSH'}

		# Build command
		if action == 'status':
			cmd = 'ufw status verbose 2>/dev/null'
		elif action == 'list_rules':
			cmd = 'ufw status numbered 2>/dev/null'
		elif action == 'audit':
			cmd = 'ufw status verbose 2>/dev/null; echo "---PORTS---"; ss -tlnp 2>/dev/null | head -30'
		elif action == 'allow':
			from_clause = f' from {from_ip}' if from_ip and from_ip != 'any' else ''
			cmd = f'ufw allow{from_clause} {port}/{proto} comment "{comment}" 2>/dev/null'
		elif action == 'deny':
			cmd = f'ufw deny {port}/{proto} comment "{comment}" 2>/dev/null'
		elif action == 'delete':
			cmd = f'ufw --force delete {port} 2>/dev/null'
		elif action == 'enable':
			cmd = 'ufw --force enable 2>/dev/null'
		elif action == 'disable':
			cmd = 'ufw disable 2>/dev/null'
		elif action == 'reset':
			return {'error': 'reset is not supported — too destructive. Manage rules individually.'}
		else:
			return {'error': f'Unhandled action: {action}'}

		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No servers matched: {host!r}'}

		if dry_run and not is_read_only:
			return {
				'action':          action,
				'dry_run':         True,
				'planned_command': cmd,
				'target_hosts':    [s.hostname for s in servers],
			}

		raw_results = run_on_fleet(servers, cmd, timeout=20)

		analysis = ''
		if action == 'audit' and raw_results:
			combined = '\n'.join(f'=== {srv.hostname} ===\n{res.stdout}'
								 for srv, res in zip(servers, raw_results) if res.stdout)
			if combined:
				prompt = (
					'You are a Linux security engineer reviewing firewall and open-port status.\n\n'
					+ combined[:4000] + '\n\n'
					'In 3 bullets: which ports are dangerously exposed, what should be restricted, '
					'and what looks appropriately protected?'
				)
				try:
					analysis = self.ai_engine.generate_text(prompt)
				except Exception:
					analysis = ''

		return {
			'action':        action,
			'dry_run':       False,
			'results':       [r.model_dump() for r in raw_results],
			'success_count': sum(1 for r in raw_results if r.success),
			'analysis':      analysis,
		}

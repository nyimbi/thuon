# capabilities/openbao_operator.py
"""
OpenBao (Vault fork) operator.

SECURITY NOTE: This capability NEVER stores, logs, or transmits unseal keys.
When unseal is needed it returns interactive instructions only.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command

logger = logging.getLogger('thuon.openbao_operator')

_ALLOWED_ACTIONS = {'status', 'seal_status', 'check_health', 'list_mounts',
					'list_policies', 'unseal_instructions', 'token_lookup'}

# Default OpenBao host
_OPENBAO_HOST = 'ml'
_OPENBAO_ADDR = 'http://127.0.0.1:8200'


class OpenBaoOperator:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def operate(
		self,
		action: str,
		host: str = _OPENBAO_HOST,
		vault_addr: str = _OPENBAO_ADDR,
	) -> dict[str, Any]:
		"""
		Inspect or get guidance for OpenBao operations.

		Actions:
		  status              — overall status (initialized, sealed, HA mode)
		  seal_status         — is the vault sealed?
		  check_health        — HTTP health endpoint
		  list_mounts         — list secret engines (requires unseal + token)
		  list_policies       — list ACL policies
		  unseal_instructions — if sealed, return step-by-step unseal guidance
		  token_lookup        — look up VAULT_TOKEN info (does not return secret data)

		NEVER passes unseal keys through this capability.  The unseal keys
		are the operator's responsibility and must be stored offline.

		Returns:
			{action, host, sealed: bool, data: {...}, instructions: str}
		"""
		action = action.lower().strip()
		if action not in _ALLOWED_ACTIONS:
			return {'error': f'Unknown action {action!r}. Allowed: {sorted(_ALLOWED_ACTIONS)}'}

		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}
		srv = servers[0]

		env = f'VAULT_ADDR={vault_addr}'

		if action in ('status', 'seal_status', 'check_health'):
			cmd = f'{env} bao status -format=json 2>/dev/null || {env} vault status -format=json 2>/dev/null'
		elif action == 'list_mounts':
			cmd = f'{env} bao secrets list -format=json 2>/dev/null'
		elif action == 'list_policies':
			cmd = f'{env} bao policy list -format=json 2>/dev/null'
		elif action == 'token_lookup':
			cmd = f'{env} bao token lookup -format=json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); d.get(\'data\',{{}}).pop(\'id\',None); print(json.dumps(d))"'
		elif action == 'unseal_instructions':
			# Always check actual seal status first
			cmd = f'{env} bao status -format=json 2>/dev/null || echo \'{{"sealed":true}}\''

		try:
			from core.sysadmin_types import SSHUnavailableError
			res = run_command(srv, cmd, timeout=15)
		except SSHUnavailableError:
			# Return instructions even when SSH is unavailable
			from core.sysadmin_types import CommandResult
			res = CommandResult(
				hostname=srv.hostname, ip=srv.ip, command=cmd,
				exit_code=1, stdout='', stderr='SSH unavailable',
				success=False, dry_run=False,
			)

		import json as _json
		data: dict = {}
		try:
			data = _json.loads(res.stdout) if res.stdout else {}
		except Exception:
			data = {'raw': res.stdout[:500]}

		sealed = bool(data.get('sealed', True))

		instructions = ''
		if action == 'unseal_instructions' or sealed:
			instructions = (
				'OpenBao is SEALED and requires manual unseal.\n\n'
				'Steps (requires 3 of 5 unseal keys — kept offline by the operator):\n'
				'  1. SSH to the OpenBao host: ssh root@62.169.25.77\n'
				'  2. Run: VAULT_ADDR=http://127.0.0.1:8200 bao operator unseal\n'
				'     Enter unseal key #1 when prompted.\n'
				'  3. Repeat step 2 two more times with keys #2 and #3.\n'
				'  4. Verify: bao status | grep Sealed  → should show "Sealed false"\n\n'
				'IMPORTANT: Never share unseal keys via email, chat, or this system.\n'
				'Store them in a password manager or hardware HSM.\n'
				'After 3 successful unseal operations the vault auto-joins HA if configured.'
			)

		return {
			'action':       action,
			'host':         srv.hostname,
			'ip':           srv.ip,
			'vault_addr':   vault_addr,
			'sealed':       sealed,
			'initialized':  data.get('initialized', False),
			'ha_enabled':   data.get('ha_enabled', False),
			'data':         data,
			'instructions': instructions,
			'ssh_reachable': res.success or bool(res.stdout),
		}

# capabilities/backup_operator.py
"""
Backup operations: trigger pg_dump, verify integrity, check rsync status.
All mutations require dry_run=False.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command

logger = logging.getLogger('thuon.backup_operator')

_ALLOWED_ACTIONS = {'dump_database', 'verify_dump', 'rsync_status',
					'list_dumps', 'check_disk_space', 'dump_and_verify'}


class BackupOperator:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def operate(
		self,
		action: str,
		host: str = 'db-main',
		database: str = '',
		dump_dir: str = '/var/backups/postgres',
		offsite_target: str = '',
		dry_run: bool = True,
	) -> dict[str, Any]:
		"""
		Backup operations on remote PostgreSQL hosts.

		Actions:
		  dump_database   — pg_dump -Fc to dump_dir (dry_run=True shows command)
		  verify_dump     — pg_restore --list on the latest dump in dump_dir
		  rsync_status    — check disk usage of dump_dir
		  list_dumps      — list dump files in dump_dir with sizes and ages
		  check_disk_space — report free space on dump host
		  dump_and_verify — dump then verify integrity (respects dry_run)

		Args:
			action:         which operation
			host:           database host
			database:       database name (required for dump actions)
			dump_dir:       directory for dump files on remote host
			offsite_target: rsync target (user@host:path) for offsite copy
			dry_run:        show planned commands without executing

		Returns:
			{action, host, success, output, analysis}
		"""
		action = action.lower().strip()
		if action not in _ALLOWED_ACTIONS:
			return {'error': f'Unknown action {action!r}. Allowed: {sorted(_ALLOWED_ACTIONS)}'}

		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}
		srv = servers[0]

		if action == 'check_disk_space':
			cmd = f'df -h {dump_dir} 2>/dev/null; df -h / 2>/dev/null | tail -1'
			res = run_command(srv, cmd, timeout=10)
			return {
				'action': action, 'host': srv.hostname, 'ip': srv.ip,
				'output': res.stdout, 'success': res.success,
			}

		if action == 'list_dumps':
			cmd = f'ls -lhtr {dump_dir}/*.dump {dump_dir}/*.sql.gz 2>/dev/null | tail -20 || echo "No dumps found in {dump_dir}"'
			res = run_command(srv, cmd, timeout=10)
			return {
				'action': action, 'host': srv.hostname, 'ip': srv.ip,
				'output': res.stdout, 'success': res.success,
				'dump_dir': dump_dir,
			}

		if action == 'rsync_status':
			cmd = f'du -sh {dump_dir} 2>/dev/null; ls -lhtr {dump_dir}/ 2>/dev/null | tail -5'
			res = run_command(srv, cmd, timeout=10)
			return {
				'action': action, 'host': srv.hostname, 'ip': srv.ip,
				'output': res.stdout, 'success': res.success,
			}

		if not database:
			return {'error': f'Action {action!r} requires the database parameter'}

		ts_cmd = '$(date +%Y%m%d_%H%M%S)'
		dump_file = f'{dump_dir}/{database}_{ts_cmd}.dump'

		if action in ('dump_database', 'dump_and_verify'):
			dump_cmd = (
				f'mkdir -p {dump_dir} && '
				f'pg_dump -U postgres -Fc {database} -f {dump_file} && '
				f'echo "DUMP_OK:{dump_file}"'
			)
			verify_cmd = (
				f'LATEST=$(ls -t {dump_dir}/{database}_*.dump 2>/dev/null | head -1) && '
				f'[ -n "$LATEST" ] && pg_restore --list "$LATEST" > /dev/null && '
				f'echo "VERIFY_OK:$LATEST" || echo "VERIFY_FAIL"'
			)

			if dry_run:
				planned = [dump_cmd]
				if action == 'dump_and_verify':
					planned.append(verify_cmd)
				return {
					'action': action, 'host': srv.hostname, 'dry_run': True,
					'planned_commands': planned,
					'note': 'Pass dry_run=False to execute',
				}

			res = run_command(srv, dump_cmd, timeout=600)
			result: dict[str, Any] = {
				'action': action, 'host': srv.hostname, 'ip': srv.ip,
				'dry_run': False, 'dump_output': res.stdout,
				'dump_success': res.success and 'DUMP_OK' in res.stdout,
			}

			if action == 'dump_and_verify' and result['dump_success']:
				vres = run_command(srv, verify_cmd, timeout=60)
				result['verify_output'] = vres.stdout
				result['verify_success'] = 'VERIFY_OK' in vres.stdout
				result['success'] = result['dump_success'] and result.get('verify_success', False)
			else:
				result['success'] = result['dump_success']

			if result.get('success'):
				result['analysis'] = f'Backup of {database} on {srv.hostname} completed successfully.'
			else:
				err = res.stderr or res.stdout
				prompt = (
					f'pg_dump of {database} on {srv.hostname} failed.\n'
					f'Output: {err[:1000]}\n'
					'What is the most likely cause and how to fix it?'
				)
				try:
					result['analysis'] = self.ai_engine.generate_text(prompt)
				except Exception:
					result['analysis'] = f'Backup failed: {err[:200]}'
			return result

		if action == 'verify_dump':
			cmd = (
				f'LATEST=$(ls -t {dump_dir}/{database}_*.dump 2>/dev/null | head -1) && '
				f'[ -n "$LATEST" ] && '
				f'pg_restore --list "$LATEST" > /dev/null && '
				f'ROW=$(pg_restore --list "$LATEST" | wc -l) && '
				f'echo "VERIFY_OK:$LATEST:$ROW items" || echo "VERIFY_FAIL:no dump found"'
			)
			res = run_command(srv, cmd, timeout=60)
			ok = 'VERIFY_OK' in res.stdout
			return {
				'action': action, 'host': srv.hostname, 'ip': srv.ip,
				'output': res.stdout, 'success': ok,
				'analysis': 'Dump integrity verified.' if ok else 'Verification failed — dump may be corrupt.',
			}

		return {'error': f'Unhandled action: {action}'}

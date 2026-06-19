# capabilities/postgres_operator.py
"""
PostgreSQL operations: health check, replication lag monitoring, dump triggers.
All remote operations go via SSH + psql/pg_dump.  Mutations default to dry_run=True.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command

logger = logging.getLogger('thuon.postgres_operator')

_ALLOWED_ACTIONS = {'health', 'replication_lag', 'list_databases', 'dump',
					'replication_status', 'pg_stat_activity', 'bloat_check'}


class PostgresOperator:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def operate(
		self,
		action: str,
		host: str = 'db-main',
		database: str = '',
		dump_dir: str = '/tmp',
		dry_run: bool = True,
	) -> dict[str, Any]:
		"""
		PostgreSQL operations on a remote host.

		Actions:
		  health            — can connect, pg_isready status
		  replication_lag   — bytes and seconds of replication lag (on primary)
		  list_databases    — list databases with sizes
		  dump              — pg_dump a database (dry_run=True shows command only)
		  pg_stat_activity  — active queries count and longest query
		  bloat_check       — tables with estimated bloat > 20%

		Args:
			action:   which operation to run
			host:     hostname/IP of the PostgreSQL server
			database: target database name (for dump, pg_stat_activity)
			dump_dir: remote directory to write dump file (for dump action)
			dry_run:  if True and action is mutating, return command only

		Returns:
			{action, host, data: {...}, analysis: str}
		"""
		action = action.lower().strip()
		if action not in _ALLOWED_ACTIONS:
			return {'error': f'Unknown action {action!r}. Allowed: {sorted(_ALLOWED_ACTIONS)}'}

		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}
		srv = servers[0]

		# Build command
		if action == 'health':
			cmd = "pg_isready -U postgres 2>&1; psql -U postgres -c 'SELECT version();' 2>&1 | head -3"

		elif action == 'replication_lag':
			cmd = (
				"psql -U postgres -t -A -c \""
				"SELECT client_addr, state, "
				"pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS sent_lag_bytes, "
				"pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes, "
				"EXTRACT(EPOCH FROM (now() - write_time))::int AS lag_seconds "
				"FROM pg_stat_replication;\" 2>&1"
			)

		elif action == 'list_databases':
			cmd = "psql -U postgres -c '\\l+' 2>&1"

		elif action == 'dump':
			if not database:
				return {'error': 'dump action requires database parameter'}
			fname = f'{dump_dir}/{database}_{{}}.dump'.format('$(date +%Y%m%d_%H%M%S)')
			cmd = f'pg_dump -U postgres -Fc {database} -f {fname} && echo "DUMP_OK:{fname}"'
			if dry_run:
				return {
					'action': action, 'host': srv.hostname, 'dry_run': True,
					'planned_command': cmd,
					'note': 'Pass dry_run=False to execute the dump',
				}

		elif action == 'pg_stat_activity':
			db_clause = f"AND datname='{database}'" if database else ''
			cmd = (
				f"psql -U postgres -t -A -c \""
				f"SELECT count(*), max(EXTRACT(EPOCH FROM (now()-query_start)))::int AS max_secs, "
				f"(SELECT query FROM pg_stat_activity WHERE state='active' {db_clause} "
				f"ORDER BY query_start LIMIT 1) AS longest "
				f"FROM pg_stat_activity WHERE state='active' {db_clause};\" 2>&1"
			)

		elif action == 'replication_status':
			cmd = (
				"psql -U postgres -c \"SELECT * FROM pg_stat_replication;\" 2>&1; "
				"psql -U postgres -c \"SELECT pg_is_in_recovery();\" 2>&1"
			)

		elif action == 'bloat_check':
			cmd = (
				"psql -U postgres -t -A -c \""
				"SELECT schemaname, tablename, "
				"pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size, "
				"n_dead_tup, n_live_tup, "
				"round(n_dead_tup::numeric/(n_live_tup+n_dead_tup+1)*100,1) AS bloat_pct "
				"FROM pg_stat_user_tables "
				"WHERE n_live_tup + n_dead_tup > 1000 "
				"ORDER BY bloat_pct DESC LIMIT 20;\" 2>&1"
			)
		else:
			return {'error': f'Unhandled action: {action}'}

		res = run_command(srv, cmd, timeout=60)

		analysis = ''
		if res.stdout and action in ('replication_lag', 'pg_stat_activity', 'bloat_check'):
			prompt = (
				f'You are a PostgreSQL DBA reviewing output from {srv.hostname}.\n\n'
				f'Action: {action}\nOutput:\n{res.stdout[:3000]}\n\n'
				'In 2 sentences: is this healthy? Any action needed?'
			)
			try:
				analysis = self.ai_engine.generate_text(prompt)
			except Exception:
				pass

		return {
			'action':    action,
			'host':      srv.hostname,
			'ip':        srv.ip,
			'dry_run':   False,
			'success':   res.success,
			'stdout':    res.stdout,
			'stderr':    res.stderr,
			'analysis':  analysis,
		}

# tests/ci/test_sysadmin_capabilities.py
"""
CI tests for the sysadmin capability cluster.

All SSH and LLM calls are mocked; no real servers are contacted.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _ai(response: str = '{"result": "ok"}') -> MagicMock:
	m = MagicMock()
	m.generate_text.return_value = response
	return m


def _cmd(stdout: str = '', exit_code: int = 0, success: bool = True) -> MagicMock:
	r = MagicMock()
	r.stdout = stdout
	r.stderr = ''
	r.exit_code = exit_code
	r.success = success
	r.dry_run = False
	r.model_dump.return_value = {
		'hostname': 'test-host', 'ip': '1.2.3.4', 'command': 'cmd',
		'exit_code': exit_code, 'stdout': stdout, 'stderr': '',
		'success': success, 'dry_run': False,
	}
	return r


def _srv(hostname: str = 'easf', ip: str = '1.2.3.4', role: str = 'app') -> MagicMock:
	s = MagicMock()
	s.hostname = hostname
	s.ip = ip
	s.role = role
	s.tags = [role]
	return s


# ── FleetInventory ────────────────────────────────────────────────────────────

class TestFleetInventory:
	def test_all_returns_servers(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		servers = inv.all()
		assert len(servers) >= 1

	def test_by_role_filters(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		dbs = inv.by_role('database')
		assert all(s.role == 'database' for s in dbs)

	def test_by_tag_filters(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		tagged = inv.by_tag('web')
		assert len(tagged) >= 1

	def test_resolve_all(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		result = inv.resolve('all')
		assert result == inv.all()

	def test_resolve_none(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		result = inv.resolve(None)
		assert result == inv.all()

	def test_resolve_role_prefix(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		result = inv.resolve('role:database')
		assert all(s.role == 'database' for s in result)

	def test_resolve_tag_prefix(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		result = inv.resolve('tag:postgres')
		assert len(result) >= 1

	def test_resolve_single_name(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		servers = inv.all()
		if servers:
			name = servers[0].hostname
			result = inv.resolve(name)
			assert len(result) == 1
			assert result[0].hostname == name

	def test_resolve_list(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		servers = inv.all()
		if len(servers) >= 2:
			names = [servers[0].hostname, servers[1].hostname]
			result = inv.resolve(names)
			assert len(result) == 2

	def test_resolve_unknown_returns_empty(self):
		from core.fleet_inventory import FleetInventory
		inv = FleetInventory()
		result = inv.resolve('no-such-server-xyz')
		assert result == []

	def test_get_fleet_inventory_singleton(self):
		from core.fleet_inventory import get_fleet_inventory
		a = get_fleet_inventory()
		b = get_fleet_inventory()
		assert a is b


# ── SSHExecutor ───────────────────────────────────────────────────────────────

class TestSSHExecutor:
	def test_run_command_dry_run_without_paramiko(self):
		"""run_command must raise SSHUnavailableError when paramiko absent."""
		import sys
		saved = sys.modules.get('paramiko')
		sys.modules['paramiko'] = None  # simulate absence
		try:
			import importlib
			import core.ssh_executor as mod
			importlib.reload(mod)
			# SSHUnavailableError should be raised when calling run_command
			with pytest.raises(Exception):
				mod.run_command(_srv(), 'echo hi')
		finally:
			if saved is None:
				sys.modules.pop('paramiko', None)
			else:
				sys.modules['paramiko'] = saved

	def test_commandresult_model(self):
		from core.sysadmin_types import CommandResult
		r = CommandResult(
			hostname='h', ip='1.1.1.1', command='ls', exit_code=0,
			stdout='ok', stderr='', success=True, dry_run=False,
		)
		assert r.success is True
		assert r.model_dump()['hostname'] == 'h'


# ── FleetHealthMonitor ────────────────────────────────────────────────────────

class TestFleetHealthMonitor:
	def _mock_inventory(self, servers):
		m = MagicMock()
		m.resolve.return_value = servers
		return m

	def test_check_returns_expected_keys(self):
		from capabilities.fleet_health_monitor import FleetHealthMonitor
		ai = _ai('{"summary": "all healthy"}')
		cap = FleetHealthMonitor(ai_engine=ai)

		srv = _srv()
		health_output = json.dumps({
			'hostname': 'easf', 'uptime_days': 10.0,
			'load_1': 0.5, 'load_5': 0.3, 'load_15': 0.2,
			'ram_total_mb': 8192, 'ram_used_mb': 2048,
			'disk_used_pct': 40, 'disk_free_gb': 60,
		})

		with patch('capabilities.fleet_health_monitor.get_fleet_inventory') as gi, \
			 patch('capabilities.fleet_health_monitor.run_on_fleet') as rf:
			gi.return_value = self._mock_inventory([srv])
			rf.return_value = [_cmd(health_output)]
			result = cap.check(hosts='all')

		assert 'servers' in result
		assert 'alerts' in result
		assert 'reachable_count' in result
		assert 'unreachable_count' in result

	def test_check_no_servers(self):
		from capabilities.fleet_health_monitor import FleetHealthMonitor
		cap = FleetHealthMonitor(ai_engine=_ai())
		with patch('capabilities.fleet_health_monitor.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = []
			gi.return_value = m
			result = cap.check(hosts='nonexistent')
		assert 'error' in result

	def test_alert_on_high_disk(self):
		from capabilities.fleet_health_monitor import FleetHealthMonitor
		ai = _ai('disk critical')
		cap = FleetHealthMonitor(ai_engine=ai)

		srv = _srv()
		# Format: hostname|uptime_d|load_1m|load_5m|load_15m|cpus|ram_used_mb|ram_total_mb|ram_pct|disk_used_gb|disk_total_gb|disk_pct
		health_output = 'easf|1.0|0.1|0.1|0.1|4|100|1024|10|95|100|95'

		with patch('capabilities.fleet_health_monitor.get_fleet_inventory') as gi, \
			 patch('capabilities.fleet_health_monitor.run_on_fleet') as rf:
			gi.return_value = self._mock_inventory([srv])
			rf.return_value = [_cmd(health_output)]
			result = cap.check(hosts='all', disk_warn=90)

		assert any('disk' in a.get('flags', []) for a in result['alerts'])


# ── SecurityAuditor ───────────────────────────────────────────────────────────

class TestSecurityAuditor:
	def test_audit_returns_expected_keys(self):
		from capabilities.security_auditor import SecurityAuditor
		ai = _ai('Clean — no threats detected.')
		cap = SecurityAuditor(ai_engine=ai)

		srv = _srv()
		scan_output = json.dumps({
			'hostname': 'easf', 'miners_found': [],
			'failed_ssh_attempts': 5, 'authorized_key_count': 1,
		})

		with patch('capabilities.security_auditor.get_fleet_inventory') as gi, \
			 patch('capabilities.security_auditor.run_on_fleet') as rf:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rf.return_value = [_cmd(scan_output)]
			result = cap.audit(hosts='all')

		assert 'servers' in result
		assert 'critical_findings' in result
		assert 'hosts_audited' in result

	def test_miner_detected_as_critical(self):
		from capabilities.security_auditor import SecurityAuditor
		cap = SecurityAuditor(ai_engine=_ai('miner found'))

		srv = _srv()
		scan_output = json.dumps({
			'hostname': 'easf', 'miners_found': ['xmrig'],
			'failed_ssh_attempts': 0, 'authorized_key_count': 1,
		})

		with patch('capabilities.security_auditor.get_fleet_inventory') as gi, \
			 patch('capabilities.security_auditor.run_on_fleet') as rf:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rf.return_value = [_cmd(scan_output)]
			result = cap.audit(hosts='all')

		assert len(result['critical_findings']) > 0
		assert any('xmrig' in str(f).lower() for f in result['critical_findings'])


# ── ServiceStatusChecker ──────────────────────────────────────────────────────

class TestServiceStatusChecker:
	def test_check_returns_counts(self):
		from capabilities.service_status_checker import ServiceStatusChecker
		cap = ServiceStatusChecker(ai_engine=_ai())

		srv = _srv()
		status_out = 'ActiveState=active\nSubState=running\nLoadState=loaded\n'

		with patch('capabilities.service_status_checker.get_fleet_inventory') as gi, \
			 patch('capabilities.service_status_checker.run_on_fleet') as rf:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rf.return_value = [_cmd(status_out)]
			result = cap.check(service='caddy', hosts='all')

		assert 'running_count' in result
		assert 'failed_count' in result
		assert 'statuses' in result

	def test_no_servers_returns_error(self):
		from capabilities.service_status_checker import ServiceStatusChecker
		cap = ServiceStatusChecker(ai_engine=_ai())
		with patch('capabilities.service_status_checker.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = []
			gi.return_value = m
			result = cap.check(service='caddy', hosts='nope')
		assert 'error' in result


# ── LogAnalyzer ───────────────────────────────────────────────────────────────

class TestLogAnalyzer:
	def test_analyze_journald(self):
		from capabilities.log_analyzer import LogAnalyzer
		ai = _ai('{"answer": "No critical errors found.", "error_lines": []}')
		cap = LogAnalyzer(ai_engine=ai)

		srv = _srv()
		log_output = 'Jun 19 10:00:00 caddy[123]: info: serving on :443\n' * 5

		with patch('capabilities.log_analyzer.get_fleet_inventory') as gi, \
			 patch('capabilities.log_analyzer.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd(log_output)
			result = cap.analyze(host='easf', source='journald:caddy')

		assert 'analysis' in result
		assert 'error_lines' in result

	def test_analyze_file_source(self):
		from capabilities.log_analyzer import LogAnalyzer
		ai = _ai('Some auth failures detected.')
		cap = LogAnalyzer(ai_engine=ai)

		srv = _srv()
		with patch('capabilities.log_analyzer.get_fleet_inventory') as gi, \
			 patch('capabilities.log_analyzer.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd('Failed password for root\nAccepted key for admin')
			result = cap.analyze(host='easf', source='file:/var/log/auth.log')

		assert 'analysis' in result

	def test_no_server_returns_error(self):
		from capabilities.log_analyzer import LogAnalyzer
		cap = LogAnalyzer(ai_engine=_ai())
		with patch('capabilities.log_analyzer.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = []
			gi.return_value = m
			result = cap.analyze(host='ghost')
		assert 'error' in result


# ── ServiceManager ────────────────────────────────────────────────────────────

class TestServiceManager:
	def test_dry_run_returns_planned_command(self):
		from capabilities.service_manager import ServiceManager
		cap = ServiceManager(ai_engine=_ai())

		srv = _srv()
		with patch('capabilities.service_manager.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.manage(action='restart', service='caddy', host='easf', dry_run=True)

		assert result['dry_run'] is True
		assert 'planned_command' in result
		assert 'restart' in result['planned_command']

	def test_invalid_action_returns_error(self):
		from capabilities.service_manager import ServiceManager
		cap = ServiceManager(ai_engine=_ai())
		result = cap.manage(action='explode', service='caddy', host='easf')
		assert 'error' in result

	def test_status_ignores_dry_run(self):
		from capabilities.service_manager import ServiceManager
		cap = ServiceManager(ai_engine=_ai())

		srv = _srv()
		with patch('capabilities.service_manager.get_fleet_inventory') as gi, \
			 patch('capabilities.service_manager.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd('● caddy.service - Web Server')
			# status is read-only: dry_run=True should still execute
			result = cap.manage(action='status', service='caddy', host='easf', dry_run=True)

		assert 'dry_run' not in result or result.get('dry_run') is False


# ── DeploymentRunner ──────────────────────────────────────────────────────────

class TestDeploymentRunner:
	def test_dry_run_returns_planned_steps(self):
		from capabilities.deployment_runner import DeploymentRunner
		cap = DeploymentRunner(ai_engine=_ai())

		srv = _srv()
		with patch('capabilities.deployment_runner.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.deploy(
				host='easf', repo_path='/opt/app', dry_run=True,
			)

		assert result['dry_run'] is True
		assert 'planned_steps' in result

	def test_no_server_returns_error(self):
		from capabilities.deployment_runner import DeploymentRunner
		cap = DeploymentRunner(ai_engine=_ai())
		with patch('capabilities.deployment_runner.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = []
			gi.return_value = m
			result = cap.deploy(host='ghost', repo_path='/opt/app')
		assert 'error' in result


# ── PostgresOperator ──────────────────────────────────────────────────────────

class TestPostgresOperator:
	def test_health_action(self):
		from capabilities.postgres_operator import PostgresOperator
		ai = _ai('{"summary": "postgres healthy"}')
		cap = PostgresOperator(ai_engine=ai)

		srv = _srv('db-main', role='database')
		pg_out = json.dumps({
			'version': 'PostgreSQL 17.2',
			'connections': {'max': 200, 'used': 15},
			'uptime': '10 days',
		})

		with patch('capabilities.postgres_operator.get_fleet_inventory') as gi, \
			 patch('capabilities.postgres_operator.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd(pg_out)
			result = cap.operate(action='health', host='db-main')

		assert 'action' in result
		assert result['action'] == 'health'

	def test_invalid_action_returns_error(self):
		from capabilities.postgres_operator import PostgresOperator
		cap = PostgresOperator(ai_engine=_ai())
		result = cap.operate(action='drop_all', host='db-main')
		assert 'error' in result

	def test_list_databases(self):
		from capabilities.postgres_operator import PostgresOperator
		cap = PostgresOperator(ai_engine=_ai())

		srv = _srv('db-main', role='database')
		with patch('capabilities.postgres_operator.get_fleet_inventory') as gi, \
			 patch('capabilities.postgres_operator.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd('postgres|0 MB\nthuon_db|120 MB\n')
			result = cap.operate(action='list_databases', host='db-main')

		assert 'action' in result


# ── OpenBaoOperator ───────────────────────────────────────────────────────────

class TestOpenBaoOperator:
	def test_unseal_instructions_never_executes(self):
		from capabilities.openbao_operator import OpenBaoOperator
		cap = OpenBaoOperator(ai_engine=_ai())

		srv = _srv('ml')
		with patch('capabilities.openbao_operator.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.operate(action='unseal_instructions', host='ml')

		# Must NOT contain any actual key material; must be guidance only
		assert 'instructions' in result or 'guidance' in result or 'note' in result
		assert result.get('executed') is not True

	def test_seal_status_runs(self):
		from capabilities.openbao_operator import OpenBaoOperator
		cap = OpenBaoOperator(ai_engine=_ai())

		srv = _srv('ml')
		with patch('capabilities.openbao_operator.get_fleet_inventory') as gi, \
			 patch('capabilities.openbao_operator.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd('Sealed: false\nInit: true\n')
			result = cap.operate(action='seal_status', host='ml')

		assert 'action' in result

	def test_invalid_action_returns_error(self):
		from capabilities.openbao_operator import OpenBaoOperator
		cap = OpenBaoOperator(ai_engine=_ai())
		result = cap.operate(action='delete_all_secrets', host='ml')
		assert 'error' in result


# ── BackupOperator ────────────────────────────────────────────────────────────

class TestBackupOperator:
	def test_list_dumps_dry_run(self):
		from capabilities.backup_operator import BackupOperator
		cap = BackupOperator(ai_engine=_ai())

		srv = _srv('db-backup')
		with patch('capabilities.backup_operator.get_fleet_inventory') as gi, \
			 patch('capabilities.backup_operator.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd('thuon_db_2026-06-19.dump\nthuon_db_2026-06-18.dump\n')
			result = cap.operate(action='list_dumps', host='db-backup')

		assert 'action' in result
		assert result['action'] == 'list_dumps'

	def test_dump_respects_dry_run(self):
		from capabilities.backup_operator import BackupOperator
		cap = BackupOperator(ai_engine=_ai())

		srv = _srv('db-backup')
		with patch('capabilities.backup_operator.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.operate(
				action='dump_database', host='db-backup',
				database='thuon_db', dry_run=True,
			)

		assert result.get('dry_run') is True

	def test_invalid_action_returns_error(self):
		from capabilities.backup_operator import BackupOperator
		cap = BackupOperator(ai_engine=_ai())
		result = cap.operate(action='wipe_all_backups', host='db-backup')
		assert 'error' in result


# ── FirewallManager ───────────────────────────────────────────────────────────

class TestFirewallManager:
	def test_deny_port_22_refused(self):
		from capabilities.firewall_manager import FirewallManager
		cap = FirewallManager(ai_engine=_ai())
		srv = _srv()
		with patch('capabilities.firewall_manager.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.manage(action='deny', host='easf', port=22, dry_run=False)
		assert 'error' in result
		assert '22' in result['error']

	def test_status_executes_read_only(self):
		from capabilities.firewall_manager import FirewallManager
		cap = FirewallManager(ai_engine=_ai())
		srv = _srv()
		with patch('capabilities.firewall_manager.get_fleet_inventory') as gi, \
			 patch('capabilities.firewall_manager.run_on_fleet') as rf:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rf.return_value = [_cmd('Status: active')]
			result = cap.manage(action='status', host='easf')
		assert 'results' in result

	def test_allow_dry_run_returns_planned_command(self):
		from capabilities.firewall_manager import FirewallManager
		cap = FirewallManager(ai_engine=_ai())
		srv = _srv()
		with patch('capabilities.firewall_manager.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.manage(action='allow', host='easf', port=8080, dry_run=True)
		assert result['dry_run'] is True
		assert '8080' in result['planned_command']

	def test_reset_is_always_rejected(self):
		from capabilities.firewall_manager import FirewallManager
		cap = FirewallManager(ai_engine=_ai())
		result = cap.manage(action='reset', host='easf', dry_run=False)
		assert 'error' in result

	def test_invalid_action_returns_error(self):
		from capabilities.firewall_manager import FirewallManager
		cap = FirewallManager(ai_engine=_ai())
		result = cap.manage(action='explode', host='easf')
		assert 'error' in result


# ── IncidentAnalyst ───────────────────────────────────────────────────────────

class TestIncidentAnalyst:
	def test_analyze_returns_root_cause(self):
		from capabilities.incident_analyst import IncidentAnalyst
		ai = _ai(json.dumps({
			'root_cause': 'OOM killed the caddy process',
			'severity': 'high',
			'remediation_steps': ['increase RAM', 'check memory leaks'],
		}))
		cap = IncidentAnalyst(ai_engine=ai)

		srv = _srv()
		diag = json.dumps({'hostname': 'easf', 'uptime': 'up 2 days', 'memory': '7.8G'})

		with patch('capabilities.incident_analyst.get_fleet_inventory') as gi, \
			 patch('capabilities.incident_analyst.run_command') as rc:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rc.return_value = _cmd(diag)
			result = cap.analyze(host='easf', symptom='site returning 502')

		assert 'root_cause' in result
		assert 'remediation_steps' in result
		assert 'severity' in result

	def test_unknown_host_returns_error(self):
		from capabilities.incident_analyst import IncidentAnalyst
		cap = IncidentAnalyst(ai_engine=_ai())
		with patch('capabilities.incident_analyst.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = []
			gi.return_value = m
			result = cap.analyze(host='ghost-server')
		assert 'error' in result


# ── LinuxAdminAssistant ───────────────────────────────────────────────────────

class TestLinuxAdminAssistant:
	def test_ask_without_execute_returns_analysis(self):
		from capabilities.linux_admin_assistant import LinuxAdminAssistant
		ai = _ai(json.dumps({
			'analysis': 'The load is high due to a runaway process.',
			'recommended_commands': ['top -bn1 | head -20', 'ps aux --sort=-%cpu | head -5'],
			'confidence': 'medium',
		}))
		cap = LinuxAdminAssistant(ai_engine=ai)

		srv = _srv()
		with patch('capabilities.linux_admin_assistant.get_fleet_inventory') as gi:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			result = cap.ask(question='Why is easf slow?', host='easf', execute_safe=False)

		assert 'analysis' in result
		assert 'recommended_commands' in result
		assert result['execute_safe'] is False

	def test_ask_with_execute_gathers_data(self):
		from capabilities.linux_admin_assistant import LinuxAdminAssistant
		ai = _ai(json.dumps({
			'analysis': 'High memory usage detected.',
			'recommended_commands': ['free -h'],
			'confidence': 'high',
		}))
		cap = LinuxAdminAssistant(ai_engine=ai)

		srv = _srv()
		with patch('capabilities.linux_admin_assistant.get_fleet_inventory') as gi, \
			 patch('capabilities.linux_admin_assistant.run_on_fleet') as rf:
			m = MagicMock(); m.resolve.return_value = [srv]
			gi.return_value = m
			rf.return_value = [_cmd('easf | uptime=2 days | mem=7.8G 3.1G | disk=40% 60G | load=1.2 0.9 0.8 | failed_units=0')]
			result = cap.ask(question='memory usage?', host='easf', execute_safe=True)

		assert 'analysis' in result
		assert result['execute_safe'] is True

	def test_safety_filter_blocks_mutating_commands(self):
		"""execute_safe=True must not run rm/dd/mkfs commands suggested by LLM."""
		from capabilities.linux_admin_assistant import LinuxAdminAssistant

		# LLM suggests a mutating command
		ai = _ai(json.dumps({
			'hosts': ['easf'],
			'diagnostic_commands': ['rm -rf /tmp/test', 'ls /tmp'],
			'reasoning': 'cleanup and list',
		}))
		# Second call (analysis)
		ai.generate_text.side_effect = [
			json.dumps({
				'hosts': ['easf'],
				'diagnostic_commands': ['rm -rf /tmp/test', 'ls /tmp'],
			}),
			json.dumps({
				'analysis': 'ok',
				'recommended_commands': [],
			}),
		]
		cap = LinuxAdminAssistant(ai_engine=ai)

		srv = _srv()
		collected_commands = []
		def track_fleet(servers, cmd, **kwargs):
			collected_commands.append(cmd)
			return [_cmd('output')]

		with patch('capabilities.linux_admin_assistant.get_fleet_inventory') as gi, \
			 patch('capabilities.linux_admin_assistant.run_on_fleet', side_effect=track_fleet):
			m = MagicMock(); m.resolve.return_value = [srv]; m.all.return_value = [srv]
			gi.return_value = m
			cap.ask(question='clean up?', execute_safe=True)

		# rm -rf must not appear in any executed command
		for cmd in collected_commands:
			assert 'rm -rf' not in cmd

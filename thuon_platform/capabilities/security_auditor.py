# capabilities/security_auditor.py
"""
Security auditor: detects cryptominers, counts failed SSH attempts,
audits authorized_keys, scans open ports.  Read-only; no mutations.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_on_fleet, run_command
from core.sysadmin_types import ServerInfo

logger = logging.getLogger('thuon.security_auditor')

# Known cryptominer process names from incident history
_MINER_NAMES = ['xmrig', 'moneroocean', 'kswapd0', 'ld-musl', 'kthreadd2',
				 'crypto-pool', 'minerd', 'cpuminer', 'ethminer', 'nbminer']

_AUDIT_SCRIPT = r"""
python3 -c "
import subprocess, re

def run(cmd):
    try: return subprocess.check_output(cmd,shell=True,stderr=subprocess.DEVNULL).decode().strip()
    except: return ''

miners = {names}
procs  = run('ps aux')
found_miners = [m for m in miners if m in procs]

# Failed SSH attempts (last 24h via auth.log or journald)
failed_ssh = 0
auth_log = run('tail -n 2000 /var/log/auth.log 2>/dev/null || journalctl -u ssh -n 2000 --no-pager 2>/dev/null')
for line in auth_log.splitlines():
    if 'Failed password' in line or 'Invalid user' in line:
        failed_ssh += 1

# Count authorized_keys entries
auth_keys = run('cat /root/.ssh/authorized_keys 2>/dev/null | grep -c ^ssh || echo 0')
try: auth_key_count = int(auth_keys)
except: auth_key_count = -1

# Listening ports
ports = run(\"ss -tlnp | awk 'NR>1{{print \$4}}' | sort -u\")

# Last login
last_login = run('last -n 5 | head -6')

# Check for suspicious crons
suspicious_cron = run('crontab -l 2>/dev/null; ls /etc/cron.d/ 2>/dev/null')

import json
print(json.dumps({{
    'miners_found': found_miners,
    'failed_ssh_24h': failed_ssh,
    'auth_key_count': auth_key_count,
    'listening_ports': ports,
    'last_logins': last_login,
    'cron_entries': suspicious_cron[:500],
}}))
" 2>/dev/null || echo '{{"error": "audit script failed"}}'
""".format(names=str(_MINER_NAMES))


class SecurityAuditor:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def audit(
		self,
		hosts: str | list[str] | None = 'all',
		include_ai_analysis: bool = True,
	) -> dict[str, Any]:
		"""
		Audit the fleet for security issues.

		Returns:
			{servers: [{hostname, findings, ...}], critical_findings: [...],
			 analysis: str}
		"""
		import json as _json

		inventory = get_fleet_inventory()
		servers = inventory.resolve(hosts)
		if not servers:
			return {'error': f'No servers matched: {hosts!r}', 'servers': []}

		results = run_on_fleet(servers, _AUDIT_SCRIPT, timeout=45)

		server_reports: list[dict] = []
		critical: list[dict] = []

		for srv, res in zip(servers, results):
			report: dict[str, Any] = {'hostname': srv.hostname, 'ip': srv.ip}

			if not res.success and not res.stdout:
				report['error'] = res.stderr or 'SSH failed'
				report['reachable'] = False
				server_reports.append(report)
				continue

			try:
				data = _json.loads(res.stdout)
			except Exception:
				report['error'] = f'parse error: {res.stdout[:200]}'
				server_reports.append(report)
				continue

			report.update({
				'reachable':       True,
				'miners_found':    data.get('miners_found', []),
				'failed_ssh_24h':  data.get('failed_ssh_24h', 0),
				'auth_key_count':  data.get('auth_key_count', -1),
				'listening_ports': data.get('listening_ports', ''),
				'last_logins':     data.get('last_logins', ''),
				'cron_entries':    data.get('cron_entries', ''),
			})

			if data.get('miners_found'):
				critical.append({'hostname': srv.hostname, 'ip': srv.ip,
								 'issue': 'CRYPTOMINER', 'detail': data['miners_found']})
			if data.get('failed_ssh_24h', 0) > 100:
				critical.append({'hostname': srv.hostname, 'ip': srv.ip,
								 'issue': 'HIGH_FAILED_SSH',
								 'detail': f"{data['failed_ssh_24h']} failures"})

			server_reports.append(report)

		analysis = ''
		if include_ai_analysis:
			summary_lines = []
			for r in server_reports:
				if not r.get('reachable'):
					continue
				flags = []
				if r.get('miners_found'):
					flags.append(f"MINER:{r['miners_found']}")
				if r.get('failed_ssh_24h', 0) > 50:
					flags.append(f"SSH_FAIL:{r['failed_ssh_24h']}")
				summary_lines.append(
					f"{r['hostname']} | keys={r.get('auth_key_count')} "
					f"| ssh_fails={r.get('failed_ssh_24h',0)} "
					f"| {'ALERTS: ' + ', '.join(flags) if flags else 'clean'}"
				)
			prompt = (
				'You are a Linux security analyst reviewing a fleet security audit.\n\n'
				+ '\n'.join(summary_lines) + '\n\n'
				'Summarise the security posture in 3 bullets: critical issues, '
				'warnings, and recommended immediate actions.'
			)
			try:
				analysis = self.ai_engine.generate_text(prompt)
			except Exception:
				analysis = ''

		return {
			'servers':           server_reports,
			'critical_findings': critical,
			'analysis':          analysis,
			'hosts_audited':     len(server_reports),
		}

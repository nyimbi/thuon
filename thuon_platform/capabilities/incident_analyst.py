# capabilities/incident_analyst.py
"""
Incident analyst: gathers logs, metrics, and service states from a host then
uses the LLM to produce a root-cause analysis and remediation plan.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command
from core.output_validator import validated_llm_call

logger = logging.getLogger('thuon.incident_analyst')

_GATHER_SCRIPT = r"""
python3 -c "
import subprocess, json

def run(cmd, timeout=10):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT,
                                       timeout=timeout).decode('utf-8', errors='replace').strip()
    except Exception as e:
        return f'ERROR: {e}'

data = {
    'hostname':        run('hostname -s'),
    'uptime':          run('uptime'),
    'load':            run('cat /proc/loadavg'),
    'memory':          run(\"free -h | head -2\"),
    'disk':            run(\"df -h / /var 2>/dev/null\"),
    'top_cpu':         run(\"ps aux --sort=-%cpu | head -10\"),
    'top_mem':         run(\"ps aux --sort=-%mem | head -10\"),
    'failed_services': run('systemctl --failed --no-pager 2>/dev/null | head -20'),
    'recent_errors':   run('journalctl -p err -n 30 --no-pager 2>/dev/null'),
    'network':         run('ss -s 2>/dev/null; ip route 2>/dev/null | head -5'),
    'dmesg_errors':    run('dmesg --level=err,crit 2>/dev/null | tail -10'),
    'oom_events':      run(\"dmesg 2>/dev/null | grep -i 'oom\\|out of memory' | tail -10\"),
    'disk_io':         run('iostat -x 1 1 2>/dev/null | tail -10'),
}
print(json.dumps(data))
" 2>/dev/null
"""


class IncidentAnalyst:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def analyze(
		self,
		host: str,
		symptom: str = '',
		affected_service: str = '',
		gather_extra_logs: list[str] | None = None,
	) -> dict[str, Any]:
		"""
		Gather diagnostics from *host* and produce an AI root-cause analysis.

		Args:
			host:              hostname or IP of the affected server
			symptom:           free-text description of the problem
			affected_service:  systemd unit name to pull extra journal entries for
			gather_extra_logs: list of extra files to tail (file:/path or unit names)

		Returns:
			{host, gathered_data, root_cause, remediation_steps, severity, analysis}
		"""
		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}
		srv = servers[0]

		# Gather base diagnostics
		res = run_command(srv, _GATHER_SCRIPT, timeout=60)

		import json as _json
		gathered: dict[str, Any] = {}
		try:
			gathered = _json.loads(res.stdout) if res.stdout else {}
		except Exception:
			gathered = {'raw': res.stdout[:2000]}

		# Optional: pull extra journal for specific service
		if affected_service:
			svc_res = run_command(
				srv,
				f'journalctl -u {affected_service} -n 50 --no-pager 2>/dev/null',
				timeout=15,
			)
			gathered[f'journal_{affected_service}'] = svc_res.stdout[:3000]

		# Optional extra log sources
		for log_source in (gather_extra_logs or []):
			if log_source.startswith('file:'):
				path = log_source[5:]
				lr = run_command(srv, f'tail -n 50 {path} 2>/dev/null', timeout=10)
				gathered[f'log_{path.replace("/","_")}'] = lr.stdout[:2000]

		# Build compact diagnostic summary for the LLM
		diag_text = '\n\n'.join(
			f'=== {k.upper()} ===\n{v[:500]}' for k, v in gathered.items()
			if v and 'ERROR' not in str(v)[:20]
		)

		symptom_clause = f'\nReported symptom: {symptom}' if symptom else ''
		service_clause = f'\nAffected service: {affected_service}' if affected_service else ''

		prompt = (
			f'You are a senior Linux sysadmin performing incident analysis on {srv.hostname} ({srv.ip}).'
			+ symptom_clause + service_clause + '\n\n'
			f'DIAGNOSTIC DATA:\n{diag_text[:6000]}\n\n'
			'Return a JSON object with these exact keys:\n'
			'- root_cause (str): most likely root cause in 1-2 sentences\n'
			'- severity (str): "critical" | "high" | "medium" | "low"\n'
			'- remediation_steps (list of str): ordered action items to resolve\n'
			'- monitoring_recommendations (list of str): what to watch after fix\n'
			'- escalate (bool): true if this requires immediate human escalation\n'
		)

		analysis = validated_llm_call(
			self.ai_engine, prompt,
			required_keys=['root_cause', 'severity', 'remediation_steps'],
			optional_keys=['monitoring_recommendations', 'escalate'],
		)

		if analysis.get('status') == 'parse_failed':
			analysis = {
				'root_cause': analysis.get('result', 'Analysis unavailable'),
				'severity': 'unknown',
				'remediation_steps': ['Review diagnostic data manually'],
				'escalate': True,
			}

		return {
			'host':            srv.hostname,
			'ip':              srv.ip,
			'symptom':         symptom,
			'affected_service': affected_service,
			'gathered_data':   gathered,
			**analysis,
		}

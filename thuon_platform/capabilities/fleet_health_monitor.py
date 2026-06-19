# capabilities/fleet_health_monitor.py
"""
Fleet health monitor: polls all configured servers in parallel via SSH and
returns a structured health snapshot with anomaly flags and an LLM summary.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_on_fleet
from core.sysadmin_types import HealthSnapshot, ServerInfo

logger = logging.getLogger('thuon.fleet_health_monitor')

# Single shell one-liner that emits pipe-delimited metrics
_HEALTH_CMD = (
	"echo \"$(hostname)|$(uptime | awk '{print $(NF-2)}' | tr -d ',')"
	"|$(uptime | awk '{print $(NF-2),$(NF-1),$NF}')"
	"|$(nproc)"
	"|$(free -g | awk '/Mem:/{print $3,$2}')"
	"|$(df -BG / | awk 'NR==2{print $3,$2,$5}')\"  "
	"|| true"
)

# More reliable multi-line approach
_HEALTH_SCRIPT = r"""
python3 -c "
import subprocess, re, os
def run(cmd):
    try: return subprocess.check_output(cmd,shell=True,stderr=subprocess.DEVNULL).decode().strip()
    except: return ''

uptime_s   = run('cat /proc/uptime').split()[0]
uptime_d   = round(float(uptime_s)/86400, 2)
load       = run('cat /proc/loadavg').split()[:3]
cpus       = run('nproc')
mem        = run(\"free -m | awk '/Mem:/{print \$2,\$3}'\").split()
disk       = run(\"df -BG / | awk 'NR==2{print \$2,\$3,\$5}'\").split()
hostname   = run('hostname -s')

mem_total  = int(mem[0]) if len(mem)>1 else 0
mem_used   = int(mem[1]) if len(mem)>1 else 0
mem_pct    = round(mem_used/mem_total*100,1) if mem_total else 0

disk_total = int(disk[0].rstrip('G')) if len(disk)>2 else 0
disk_used  = int(disk[1].rstrip('G')) if len(disk)>2 else 0
disk_pct   = int(disk[2].rstrip('%'))  if len(disk)>2 else 0

print(f'{hostname}|{uptime_d}|{load[0]}|{load[1]}|{load[2]}|{cpus}|{mem_used}|{mem_total}|{mem_pct}|{disk_used}|{disk_total}|{disk_pct}')
" 2>/dev/null || echo "ERROR"
"""


def _parse_health(server: ServerInfo, stdout: str) -> HealthSnapshot:
	if not stdout or stdout.strip() == 'ERROR' or '|' not in stdout:
		return HealthSnapshot(hostname=server.hostname, ip=server.ip, reachable=False,
							  error=stdout or 'no output')
	parts = stdout.strip().split('|')
	try:
		return HealthSnapshot(
			hostname=parts[0] if parts[0] else server.hostname,
			ip=server.ip,
			reachable=True,
			uptime_days=float(parts[1]),
			load_1m=float(parts[2]),
			load_5m=float(parts[3]),
			load_15m=float(parts[4]),
			cpu_count=int(parts[5]),
			ram_used_gb=round(int(parts[6]) / 1024, 2),
			ram_total_gb=round(int(parts[7]) / 1024, 2),
			ram_pct=float(parts[8]),
			disk_used_gb=int(parts[9]),
			disk_total_gb=int(parts[10]),
			disk_pct=int(parts[11]),
		)
	except (IndexError, ValueError) as exc:
		return HealthSnapshot(hostname=server.hostname, ip=server.ip, reachable=False,
							  error=f'parse error: {exc} — raw: {stdout!r}')


def _flag_anomalies(snap: HealthSnapshot, ram_warn=70, ram_crit=90,
					disk_warn=70, disk_crit=90) -> HealthSnapshot:
	if snap.reachable:
		snap.alert_ram  = snap.ram_pct >= ram_warn
		snap.alert_disk = snap.disk_pct >= disk_warn
		snap.alert_load = snap.load_1m >= snap.cpu_count * 2 if snap.cpu_count else False
	return snap


class FleetHealthMonitor:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def check(
		self,
		hosts: str | list[str] | None = 'all',
		ram_warn: int = 70,
		disk_warn: int = 70,
		include_ai_summary: bool = True,
	) -> dict[str, Any]:
		"""
		Poll all (or selected) servers and return health snapshots.

		Args:
			hosts:             'all', a hostname, role: or tag: prefix, or list
			ram_warn:          RAM % threshold for alert_ram flag (default 70)
			disk_warn:         Disk % threshold for alert_disk flag (default 70)
			include_ai_summary: ask the LLM to summarise anomalies

		Returns:
			{servers: [HealthSnapshot.dict()], alerts: [...], summary: str,
			 reachable_count: int, unreachable_count: int}
		"""
		inventory = get_fleet_inventory()
		servers = inventory.resolve(hosts)
		if not servers:
			return {'error': f'No servers matched: {hosts!r}', 'servers': []}

		results = run_on_fleet(servers, _HEALTH_SCRIPT, timeout=30)

		snapshots: list[HealthSnapshot] = []
		for srv, res in zip(servers, results):
			if not res.success and not res.stdout:
				snap = HealthSnapshot(hostname=srv.hostname, ip=srv.ip, reachable=False,
									  error=res.stderr or 'SSH failed')
			else:
				snap = _parse_health(srv, res.stdout)
			snap = _flag_anomalies(snap, ram_warn=ram_warn, disk_warn=disk_warn)
			snapshots.append(snap)

		alerts = [
			{'hostname': s.hostname, 'ip': s.ip,
			 'ram_pct': s.ram_pct, 'disk_pct': s.disk_pct, 'load_1m': s.load_1m,
			 'flags': [f for f in ('ram', 'disk', 'load')
					   if getattr(s, f'alert_{f}', False)]}
			for s in snapshots
			if s.reachable and (s.alert_ram or s.alert_disk or s.alert_load)
		]
		unreachable = [s for s in snapshots if not s.reachable]

		summary = ''
		if include_ai_summary:
			table_lines = ['hostname | ram% | disk% | load_1m | uptime_d | status']
			for s in snapshots:
				status = 'UNREACHABLE' if not s.reachable else (
					'ALERT' if (s.alert_ram or s.alert_disk or s.alert_load) else 'OK')
				table_lines.append(
					f'{s.hostname} | {s.ram_pct}% | {s.disk_pct}% | {s.load_1m} | {s.uptime_days}d | {status}')
			prompt = (
				'You are a Linux sysadmin reviewing a fleet health report.\n\n'
				+ '\n'.join(table_lines) + '\n\n'
				'In 2-3 sentences: what needs immediate attention, what can wait, '
				'and what looks healthy? Be specific about hostnames.'
			)
			try:
				summary = self.ai_engine.generate_text(prompt)
			except Exception:
				summary = ''

		return {
			'servers':           [s.model_dump() for s in snapshots],
			'alerts':            alerts,
			'unreachable':       [{'hostname': s.hostname, 'ip': s.ip, 'error': s.error}
								  for s in unreachable],
			'reachable_count':   sum(1 for s in snapshots if s.reachable),
			'unreachable_count': len(unreachable),
			'summary':           summary,
		}

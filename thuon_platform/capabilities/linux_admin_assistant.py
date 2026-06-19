# capabilities/linux_admin_assistant.py
"""
Linux Admin Assistant: natural-language interface for sysadmin operations.

Takes a question or instruction in plain English, determines what data to gather,
collects it from the appropriate hosts, then returns an analysis + recommended
commands. Never executes destructive commands without explicit dry_run=False.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command, run_on_fleet
from core.output_validator import validated_llm_call

logger = logging.getLogger('thuon.linux_admin_assistant')

_FLEET_SUMMARY_CMD = r"""
python3 -c "
import subprocess
def run(c):
    try: return subprocess.check_output(c,shell=True,stderr=subprocess.DEVNULL).decode().strip()
    except: return ''
hostname = run('hostname -s')
uptime   = run('uptime')
mem      = run(\"free -h | awk '/Mem/{print \$2,\$3}'\")
disk     = run(\"df -h / | awk 'NR==2{print \$5,\$4}'\")
load     = run('cat /proc/loadavg').split()[:3]
failed   = run('systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l')
print(f'{hostname} | uptime={uptime.split(\"up \")[-1][:30]} | mem={mem} | disk={disk} | load={\" \".join(load)} | failed_units={failed}')
" 2>/dev/null || echo "$(hostname)|unreachable"
"""


class LinuxAdminAssistant:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def ask(
		self,
		question: str,
		host: str | list[str] | None = None,
		execute_safe: bool = False,
	) -> dict[str, Any]:
		"""
		Answer a natural-language sysadmin question or instruction.

		The assistant:
		  1. Determines which hosts are relevant
		  2. Collects appropriate diagnostic data via SSH
		  3. Analyses data with the LLM
		  4. Returns analysis + recommended commands (never auto-executes mutating ops)

		Args:
			question:     natural language question or instruction
			host:         target host(s); None = auto-detect from question
			execute_safe: if True, run read-only diagnostic commands
			              (does NOT execute suggested mutating commands)

		Returns:
			{question, gathered_data, analysis, recommended_commands, hosts_queried}
		"""
		inventory = get_fleet_inventory()

		# Step 1: Determine target hosts
		servers = inventory.resolve(host) if host else []

		# If no explicit host, ask LLM to determine from question + fleet
		if not servers:
			server_list = '\n'.join(
				f'- {s.hostname} ({s.ip}): role={s.role}, tags={s.tags}'
				for s in inventory.all()
			)
			routing_prompt = (
				f'Given this fleet:\n{server_list}\n\n'
				f'The user asked: "{question}"\n\n'
				'Return a JSON object with:\n'
				'- hosts (list of hostnames or ["all"]): which servers to query\n'
				'- diagnostic_commands (list of str): safe read-only shell commands to run\n'
				'- reasoning (str): why these hosts and commands\n'
			)
			routing = validated_llm_call(
				self.ai_engine, routing_prompt,
				required_keys=['hosts', 'diagnostic_commands'],
				optional_keys=['reasoning'],
			)
			if routing.get('status') != 'parse_failed':
				servers = inventory.resolve(routing.get('hosts', ['all']))
				diag_commands = routing.get('diagnostic_commands', [])[:5]
			else:
				servers = inventory.all()
				diag_commands = []
		else:
			diag_commands = []

		# Step 2: Gather data
		gathered_data: dict[str, Any] = {}
		hosts_queried = [s.hostname for s in servers[:10]]  # cap at 10

		if execute_safe and servers:
			# Always gather basic status
			results = run_on_fleet(servers[:10], _FLEET_SUMMARY_CMD, timeout=20)
			gathered_data['fleet_summary'] = '\n'.join(
				f'{srv.hostname}: {res.stdout or res.stderr}'
				for srv, res in zip(servers[:10], results)
			)

			# Run any LLM-suggested diagnostic commands (safe only)
			for i, cmd in enumerate(diag_commands[:3]):
				# Safety filter: reject obviously mutating commands
				cmd_lower = cmd.lower()
				if any(kw in cmd_lower for kw in ('rm ', 'dd ', 'mkfs', 'fdisk', 'kill ',
												   'systemctl stop', 'systemctl disable',
												   'iptables -F', 'ufw disable', '>',
												   'chmod 000', 'chown')):
					gathered_data[f'cmd_{i}_skipped'] = f'Skipped unsafe command: {cmd}'
					continue
				cmd_results = run_on_fleet(servers[:5], cmd, timeout=15)
				gathered_data[f'cmd_{i}_{cmd[:30]}'] = '\n'.join(
					f'{srv.hostname}: {res.stdout[:300]}'
					for srv, res in zip(servers[:5], cmd_results)
				)

		# Step 3: Analyse
		fleet_context = '\n'.join(
			f'- {s.hostname} ({s.ip}): role={s.role}, tags={", ".join(s.tags)}'
			for s in servers
		)
		data_context = '\n\n'.join(
			f'=== {k} ===\n{str(v)[:800]}' for k, v in gathered_data.items()
		) if gathered_data else 'No diagnostic data gathered (execute_safe=False).'

		analysis_prompt = (
			f'You are a senior Linux sysadmin. The user asked:\n"{question}"\n\n'
			f'Target fleet:\n{fleet_context}\n\n'
			f'Gathered data:\n{data_context}\n\n'
			'Return a JSON object with:\n'
			'- analysis (str): answer to the question, citing specific data points\n'
			'- recommended_commands (list of str): exact shell commands the operator should run\n'
			'- safety_notes (list of str): any warnings about destructive commands\n'
			'- confidence (str): "high" | "medium" | "low" based on data available\n'
		)

		result = validated_llm_call(
			self.ai_engine, analysis_prompt,
			required_keys=['analysis', 'recommended_commands'],
			optional_keys=['safety_notes', 'confidence'],
		)

		if result.get('status') == 'parse_failed':
			result = {
				'analysis': result.get('result', 'Unable to analyse'),
				'recommended_commands': [],
				'safety_notes': [],
				'confidence': 'low',
			}

		return {
			'question':            question,
			'hosts_queried':       hosts_queried,
			'gathered_data':       gathered_data,
			'execute_safe':        execute_safe,
			**result,
		}

# capabilities/deployment_runner.py
"""
Run deployment operations on remote servers: git pull, systemctl reload,
and arbitrary deploy scripts.  dry_run=True by default.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command

logger = logging.getLogger('thuon.deployment_runner')


class DeploymentRunner:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def deploy(
		self,
		host: str,
		repo_path: str = '',
		deploy_script: str = '',
		services_to_reload: list[str] | None = None,
		branch: str = 'main',
		dry_run: bool = True,
	) -> dict[str, Any]:
		"""
		Deploy to a remote host.

		Steps (each is skipped if its param is empty):
		  1. git pull --ff-only in repo_path
		  2. run deploy_script (absolute path on remote)
		  3. systemctl reload each service in services_to_reload

		Args:
			host:               hostname, IP, or inventory key
			repo_path:          absolute path to git repo on remote (optional)
			deploy_script:      absolute path to deploy.sh on remote (optional)
			services_to_reload: list of systemd units to reload after deploy
			branch:             branch to pull (default 'main')
			dry_run:            if True, return planned commands only

		Returns:
			{host, dry_run, steps: [{step, command, result}], success: bool}
		"""
		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}

		srv = servers[0]
		services_to_reload = services_to_reload or []

		# Build step list
		steps: list[dict[str, str]] = []
		if repo_path:
			steps.append({
				'step': 'git_pull',
				'command': f'cd {repo_path} && git fetch origin && git checkout {branch} && git pull --ff-only origin {branch}',
			})
		if deploy_script:
			steps.append({
				'step': 'deploy_script',
				'command': f'bash {deploy_script}',
			})
		for svc in services_to_reload:
			steps.append({
				'step': f'reload_{svc}',
				'command': f'systemctl reload-or-restart {svc}',
			})

		if not steps:
			return {'error': 'No deployment steps specified (provide repo_path, deploy_script, or services_to_reload)'}

		if dry_run:
			return {
				'host':    srv.hostname,
				'ip':      srv.ip,
				'dry_run': True,
				'planned_steps': steps,
				'success': None,
			}

		results = []
		overall_success = True
		for step in steps:
			res = run_command(srv, step['command'], timeout=120)
			step_result = {
				'step':      step['step'],
				'command':   step['command'],
				'exit_code': res.exit_code,
				'stdout':    res.stdout[:2000],
				'stderr':    res.stderr[:500],
				'success':   res.success,
			}
			results.append(step_result)
			if not res.success:
				overall_success = False
				logger.error('Deploy step %s failed on %s: %s', step['step'], srv.hostname, res.stderr)
				break  # Stop on first failure

		analysis = ''
		if results:
			steps_summary = '\n'.join(
				f"[{'OK' if r['success'] else 'FAIL'}] {r['step']}: {r['stderr'] or r['stdout'][:200]}"
				for r in results
			)
			prompt = (
				f'Deployment to {srv.hostname} {"succeeded" if overall_success else "FAILED"}.\n\n'
				f'{steps_summary}\n\nIn one sentence, summarise what happened and any action needed.'
			)
			try:
				analysis = self.ai_engine.generate_text(prompt)
			except Exception:
				analysis = ''

		return {
			'host':    srv.hostname,
			'ip':      srv.ip,
			'dry_run': False,
			'steps':   results,
			'success': overall_success,
			'analysis': analysis,
		}

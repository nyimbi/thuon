# capabilities/log_analyzer.py
"""
Tail and analyse logs from remote servers via SSH + LLM pattern detection.
"""

from __future__ import annotations

import logging
from typing import Any

from core.ai_engine import AIModel
from core.fleet_inventory import get_fleet_inventory
from core.ssh_executor import run_command

logger = logging.getLogger('thuon.log_analyzer')

_MAX_LINES = 200
_MAX_BYTES = 40960  # 40 KB


def _build_log_cmd(source: str, lines: int, pattern: str | None) -> str:
	"""Build a shell command to tail a log.

	source may be:
	  - 'journald:<unit>'    → journalctl -u <unit>
	  - 'file:/var/log/...'  → tail of that file
	  - bare service name    → journalctl -u <name>
	"""
	lines = min(lines, _MAX_LINES)
	grep_part = f' | grep -i {pattern!r}' if pattern else ''

	if source.startswith('file:'):
		path = source[5:]
		return f'tail -n {lines} {path} 2>/dev/null{grep_part} || echo "FILE_NOT_FOUND"'
	elif source.startswith('journald:'):
		unit = source[9:]
		return f'journalctl -u {unit} -n {lines} --no-pager 2>/dev/null{grep_part} || journalctl -n {lines} --no-pager 2>/dev/null{grep_part}'
	else:
		# Treat as unit name
		return f'journalctl -u {source} -n {lines} --no-pager 2>/dev/null{grep_part}'


class LogAnalyzer:
	def __init__(self, ai_engine: AIModel) -> None:
		self.ai_engine = ai_engine

	def analyze(
		self,
		host: str,
		source: str = 'journald:caddy',
		lines: int = 100,
		pattern: str | None = None,
		question: str = 'Are there any errors or anomalies?',
	) -> dict[str, Any]:
		"""
		Tail a log from *host* and ask the LLM *question* about it.

		Args:
			host:    hostname, IP, or role: / tag: spec (picks first match)
			source:  'journald:<unit>', 'file:/path', or bare service name
			lines:   number of log lines to fetch (max 200)
			pattern: optional grep filter applied on the remote side
			question: what to ask the LLM about the log

		Returns:
			{host, source, raw_log, analysis, error_lines: [...]}
		"""
		inventory = get_fleet_inventory()
		servers = inventory.resolve(host)
		if not servers:
			return {'error': f'No server matched: {host!r}'}

		srv = servers[0]
		cmd = _build_log_cmd(source, lines, pattern)
		res = run_command(srv, cmd, timeout=30, max_output_bytes=_MAX_BYTES)

		raw_log = res.stdout or res.stderr or ''

		# Simple error-line extraction
		error_lines = [l for l in raw_log.splitlines()
					   if any(kw in l.lower() for kw in ('error', 'crit', 'fatal', 'panic',
														   'exception', 'traceback', 'fail'))]

		analysis = ''
		if raw_log and raw_log != 'FILE_NOT_FOUND':
			prompt = (
				f'You are a Linux sysadmin analysing logs from {srv.hostname} ({source}).\n\n'
				f'LOG (last {lines} lines):\n{raw_log[-8000:]}\n\n'
				f'Question: {question}\n'
				'Answer concisely, citing specific log lines where relevant.'
			)
			try:
				analysis = self.ai_engine.generate_text(prompt)
			except Exception:
				analysis = ''

		return {
			'host':        srv.hostname,
			'ip':          srv.ip,
			'source':      source,
			'raw_log':     raw_log,
			'error_lines': error_lines[:20],
			'analysis':    analysis,
			'reachable':   res.success or bool(res.stdout),
		}

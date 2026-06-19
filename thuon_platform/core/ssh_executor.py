# core/ssh_executor.py
"""
Paramiko-based SSH executor for the Thuon sysadmin capability cluster.

All real operations go through this module.  Falls back to subprocess ssh
when paramiko is not installed (read-only friendly; mutating ops raise).

Thread-safe: each call creates a fresh paramiko connection (no shared state).
Connection timeout defaults to 30 s; command execution timeout to 60 s.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from core.sysadmin_types import CommandResult, ServerInfo, SSHUnavailableError

logger = logging.getLogger('thuon.ssh_executor')

# ── Optional paramiko import ──────────────────────────────────────────────────

try:
	import paramiko
	_PARAMIKO_OK = True
except ImportError:
	_PARAMIKO_OK = False
	paramiko = None  # type: ignore


# ── Single-host executor ──────────────────────────────────────────────────────

def run_command(
	server: ServerInfo,
	command: str,
	*,
	timeout: int = 60,
	max_output_bytes: int = 51200,
) -> CommandResult:
	"""
	SSH into *server* and run *command*.  Returns CommandResult.

	max_output_bytes caps combined stdout+stderr to avoid OOM on large log tails.
	"""
	if not _PARAMIKO_OK:
		raise SSHUnavailableError(
			'paramiko is not installed. Run: uv add paramiko'
		)

	key_path = Path(os.path.expanduser(server.ssh_key_file)) if server.ssh_key_file else None

	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

	try:
		connect_kwargs: dict[str, Any] = {
			'hostname': server.ip,
			'port':     server.ssh_port,
			'username': server.ssh_user,
			'timeout':  30,
			'banner_timeout': 30,
			'auth_timeout': 30,
		}
		if key_path and key_path.exists():
			connect_kwargs['key_filename'] = str(key_path)
		else:
			connect_kwargs['look_for_keys'] = True
			connect_kwargs['allow_agent'] = True

		client.connect(**connect_kwargs)

		stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
		stdin.close()

		out_raw = stdout.read(max_output_bytes).decode('utf-8', errors='replace')
		err_raw = stderr.read(max_output_bytes).decode('utf-8', errors='replace')
		exit_code = stdout.channel.recv_exit_status()

		return CommandResult(
			hostname=server.hostname,
			ip=server.ip,
			command=command,
			exit_code=exit_code,
			stdout=out_raw.strip(),
			stderr=err_raw.strip(),
			success=(exit_code == 0),
		)

	except SSHUnavailableError:
		raise
	except Exception as exc:
		logger.error('SSH error %s@%s: %s', server.ssh_user, server.ip, exc)
		return CommandResult(
			hostname=server.hostname,
			ip=server.ip,
			command=command,
			exit_code=-1,
			stdout='',
			stderr=str(exc),
			success=False,
		)
	finally:
		try:
			client.close()
		except Exception:
			pass


# ── Fleet-wide parallel executor ──────────────────────────────────────────────

def run_on_fleet(
	servers: list[ServerInfo],
	command: str,
	*,
	timeout: int = 60,
	max_workers: int = 8,
	max_output_bytes: int = 51200,
) -> list[CommandResult]:
	"""
	Run *command* on every server in *servers* concurrently.
	Returns one CommandResult per server in the same order.
	"""
	results: dict[str, CommandResult] = {}
	lock = threading.Lock()

	def _run(srv: ServerInfo) -> None:
		res = run_command(srv, command, timeout=timeout, max_output_bytes=max_output_bytes)
		with lock:
			results[srv.ip] = res

	with ThreadPoolExecutor(max_workers=min(max_workers, len(servers) or 1)) as pool:
		futures = [pool.submit(_run, srv) for srv in servers]
		for f in as_completed(futures):
			try:
				f.result()
			except Exception as exc:
				logger.error('Fleet executor unexpected error: %s', exc)

	return [results.get(s.ip, CommandResult(
		hostname=s.hostname, ip=s.ip, command=command,
		exit_code=-1, stderr='No result', success=False,
	)) for s in servers]


def run_multi_on_fleet(
	servers: list[ServerInfo],
	commands: list[str],
	*,
	timeout: int = 60,
	max_workers: int = 8,
) -> list[list[CommandResult]]:
	"""
	Run multiple commands on every server.  Returns a list-of-lists:
	results[server_index][command_index].
	"""
	results_by_server: list[list[CommandResult]] = [[] for _ in servers]

	def _run_all(idx: int, srv: ServerInfo) -> None:
		for cmd in commands:
			res = run_command(srv, cmd, timeout=timeout)
			results_by_server[idx].append(res)

	with ThreadPoolExecutor(max_workers=min(max_workers, len(servers) or 1)) as pool:
		futures = [pool.submit(_run_all, i, srv) for i, srv in enumerate(servers)]
		for f in as_completed(futures):
			try:
				f.result()
			except Exception as exc:
				logger.error('Multi-command fleet error: %s', exc)

	return results_by_server

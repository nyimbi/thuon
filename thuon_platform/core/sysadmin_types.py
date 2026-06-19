# core/sysadmin_types.py
"""Shared Pydantic models for the sysadmin capability cluster."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ServerInfo(BaseModel):
	model_config = ConfigDict(extra='allow')

	ip: str
	hostname: str
	role: str = 'unknown'
	tags: list[str] = Field(default_factory=list)
	ssh_user: str = 'root'
	ssh_key_file: str = ''
	ssh_port: int = 22


class HealthSnapshot(BaseModel):
	model_config = ConfigDict(extra='allow')

	hostname: str
	ip: str
	reachable: bool = True
	error: str = ''
	uptime_days: float = 0.0
	load_1m: float = 0.0
	load_5m: float = 0.0
	load_15m: float = 0.0
	cpu_count: int = 0
	ram_used_gb: float = 0.0
	ram_total_gb: float = 0.0
	ram_pct: float = 0.0
	disk_used_gb: float = 0.0
	disk_total_gb: float = 0.0
	disk_pct: float = 0.0
	# Anomaly flags (set by fleet_health_monitor)
	alert_ram: bool = False
	alert_disk: bool = False
	alert_load: bool = False


class ServiceStatus(BaseModel):
	model_config = ConfigDict(extra='allow')

	hostname: str
	ip: str
	service: str
	active_state: str = ''   # active / inactive / failed / unknown
	sub_state: str = ''      # running / dead / exited / etc.
	load_state: str = ''     # loaded / not-found / masked
	reachable: bool = True
	error: str = ''
	raw_output: str = ''


class CommandResult(BaseModel):
	model_config = ConfigDict(extra='allow')

	hostname: str
	ip: str
	command: str
	exit_code: int = 0
	stdout: str = ''
	stderr: str = ''
	success: bool = True
	dry_run: bool = False


class SSHUnavailableError(RuntimeError):
	"""Raised when paramiko is not installed."""


class FleetConfigError(ValueError):
	"""Raised when fleet configuration is missing or invalid."""

# core/settings_manager.py

from __future__ import annotations

from typing import Any, TypeVar, overload

import yaml
import os
from core.bundle import config_dir

_CONFIG_PATH = config_dir() / 'config.yaml'


class SettingsManager:
	def __init__(self, settings_file_path: str = str(_CONFIG_PATH)):
		self.settings_file_path = settings_file_path
		self.settings: dict = {}
		self.load_settings()

	def load_settings(self) -> dict:
		if os.path.exists(self.settings_file_path):
			with open(self.settings_file_path, 'r') as f:
				self.settings = yaml.safe_load(f) or {}
		return self.settings

	_T = TypeVar('_T')

	@overload
	def get_setting(self, key_path: str, default: None = None) -> Any: ...

	@overload
	def get_setting(self, key_path: str, default: _T) -> _T: ...

	def get_setting(self, key_path: str, default: Any = None) -> Any:
		"""
		Read a dotted config path.

		Returns *default* when the path is absent, when an intermediate node
		is not a mapping, or when the stored value is an unedited 'YOUR_…'
		placeholder. The overloads exist so a typed default narrows the
		result: callers pass strings and lists and otherwise get `Any`.
		"""
		keys = key_path.split('.')
		val = self.settings
		for k in keys:
			if not isinstance(val, dict):
				return default
			val = val.get(k)
			if val is None:
				return default
		if isinstance(val, str) and val.startswith('YOUR_'):
			return default
		return val

	def set_setting(self, key_path: str, value) -> bool:
		keys = key_path.split('.')
		d = self.settings
		for k in keys[:-1]:
			d = d.setdefault(k, {})
		d[keys[-1]] = value
		return self.save_settings()

	def get_user_preference(self, key: str, default=None):
		return self.get_setting(f'user_preferences.{key}', default)

	def set_user_preference(self, key: str, value) -> bool:
		return self.set_setting(f'user_preferences.{key}', value)

	def save_settings(self) -> bool:
		try:
			with open(self.settings_file_path, 'w') as f:
				yaml.dump(self.settings, f, default_flow_style=False)
			return True
		except Exception:
			return False


_settings: SettingsManager | None = None


def get_settings() -> SettingsManager:
	global _settings
	if _settings is None:
		_settings = SettingsManager()
	return _settings

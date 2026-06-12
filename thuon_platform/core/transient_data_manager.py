# core/transient_data_manager.py

import os
import json
import shutil
import tempfile
from pathlib import Path


class TransientDataManager:
	def __init__(self, base_dir: str = '/tmp/thuon_transient'):
		self.base_dir = base_dir
		os.makedirs(self.base_dir, exist_ok=True)

	def create_temp_directory(self, prefix: str = 'temp_dir_') -> str:
		return tempfile.mkdtemp(dir=self.base_dir, prefix=prefix)

	def create_temp_file(self, prefix: str = 'temp_file_', suffix: str = '.tmp', directory: str | None = None) -> str:
		fd, path = tempfile.mkstemp(dir=directory or self.base_dir, prefix=prefix, suffix=suffix)
		os.close(fd)
		return path

	def save_data_to_temp_file(self, data: dict | list | str, file_path: str) -> bool:
		try:
			Path(file_path).parent.mkdir(parents=True, exist_ok=True)
			with open(file_path, 'w', encoding='utf-8') as f:
				if isinstance(data, (dict, list)):
					json.dump(data, f, indent=2)
				else:
					f.write(str(data))
			return True
		except Exception:
			return False

	def load_data_from_temp_file(self, file_path: str) -> dict | str:
		with open(file_path, 'r', encoding='utf-8') as f:
			content = f.read()
		try:
			return json.loads(content)
		except json.JSONDecodeError:
			return content

	def cleanup_temp_directory(self, directory_path: str) -> bool:
		try:
			shutil.rmtree(directory_path, ignore_errors=True)
			return True
		except Exception:
			return False

	def cleanup_temp_file(self, file_path: str) -> bool:
		try:
			os.remove(file_path)
			return True
		except Exception:
			return False

	def cleanup_all(self) -> bool:
		try:
			shutil.rmtree(self.base_dir, ignore_errors=True)
			os.makedirs(self.base_dir, exist_ok=True)
			return True
		except Exception:
			return False

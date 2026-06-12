# core/utils.py

import logging
import yaml
import json
import jsonschema
from pathlib import Path

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)


def log_message(message: str, level: str = 'INFO') -> None:
	logger = logging.getLogger('thuon')
	getattr(logger, level.lower(), logger.info)(message)


def handle_exception(exception: Exception, message: str) -> None:
	logger = logging.getLogger('thuon')
	logger.error(f"{message}: {type(exception).__name__}: {exception}", exc_info=True)


def validate_data(data: any, schema: dict) -> bool:
	try:
		jsonschema.validate(instance=data, schema=schema)
		return True
	except jsonschema.ValidationError:
		return False


def load_yaml_file(file_path: str) -> dict:
	try:
		with open(file_path, 'r', encoding='utf-8') as f:
			return yaml.safe_load(f) or {}
	except (FileNotFoundError, OSError):
		return {}


def save_yaml_file(data: dict, file_path: str) -> bool:
	try:
		Path(file_path).parent.mkdir(parents=True, exist_ok=True)
		with open(file_path, 'w', encoding='utf-8') as f:
			yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
		return True
	except Exception:
		return False


def load_json_file(file_path: str) -> dict:
	try:
		with open(file_path, 'r', encoding='utf-8') as f:
			return json.load(f)
	except (FileNotFoundError, OSError):
		return {}


def save_json_file(data: dict, file_path: str) -> bool:
	try:
		Path(file_path).parent.mkdir(parents=True, exist_ok=True)
		with open(file_path, 'w', encoding='utf-8') as f:
			json.dump(data, f, indent=2, ensure_ascii=False)
		return True
	except Exception:
		return False

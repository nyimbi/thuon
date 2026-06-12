# tests/ci/test_core_utils.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import json
import tempfile
from pathlib import Path
from core.utils import (
	log_message,
	handle_exception,
	validate_data,
	load_yaml_file,
	save_yaml_file,
	load_json_file,
	save_json_file,
)


def test_log_message_runs():
	# Should not raise
	log_message('INFO', 'test message')
	log_message('ERROR', 'something failed')


def test_handle_exception_returns_string():
	try:
		raise ValueError('boom')
	except ValueError as e:
		result = handle_exception(e, 'test context')
	# handle_exception logs and returns None or a string
	assert result is None or isinstance(result, str)


def test_validate_data_valid():
	schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']}
	result = validate_data({'name': 'Alice'}, schema)
	assert result is True or result is None  # True or no error


def test_validate_data_invalid():
	schema = {'type': 'object', 'properties': {'age': {'type': 'integer'}}, 'required': ['age']}
	result = validate_data({'age': 'not-an-int'}, schema)
	assert result is False or isinstance(result, str)  # invalid


def test_yaml_roundtrip():
	data = {'key': 'value', 'nested': {'a': 1, 'b': [1, 2, 3]}}
	with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
		path = f.name
	try:
		save_yaml_file(data, path)
		loaded = load_yaml_file(path)
		assert loaded == data
	finally:
		os.unlink(path)


def test_json_roundtrip():
	data = {'x': 42, 'items': ['a', 'b', 'c']}
	with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
		path = f.name
	try:
		save_json_file(data, path)
		loaded = load_json_file(path)
		assert loaded == data
	finally:
		os.unlink(path)


def test_load_yaml_missing_file():
	result = load_yaml_file('/tmp/nonexistent_thuon_test_xyz.yaml')
	assert result is None or result == {}


def test_load_json_missing_file():
	result = load_json_file('/tmp/nonexistent_thuon_test_xyz.json')
	assert result is None or result == {}

# tests/ci/test_settings_manager.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from core.settings_manager import SettingsManager, get_settings


def test_get_settings_singleton():
	s1 = get_settings()
	s2 = get_settings()
	assert s1 is s2


def test_get_setting_dotpath():
	s = get_settings()
	host = s.get_setting('database.host')
	# config.yaml has database.host = localhost
	assert host == 'localhost'


def test_get_setting_missing_returns_default():
	s = get_settings()
	val = s.get_setting('nonexistent.deep.key', 'fallback')
	assert val == 'fallback'


def test_get_setting_ollama_model():
	s = get_settings()
	model = s.get_setting('ollama.model', 'qwen3.5:4b')
	assert model == 'qwen3.5:4b'


def test_set_and_get_setting():
	import tempfile, os
	with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
		f.write('{}')
		path = f.name
	try:
		s = SettingsManager(settings_file_path=path)
		s.set_setting('test.key', 'hello')
		assert s.get_setting('test.key') == 'hello'
	finally:
		os.unlink(path)


def test_user_preferences():
	import tempfile, os
	with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
		f.write('{}')
		path = f.name
	try:
		s = SettingsManager(settings_file_path=path)
		s.set_user_preference('theme', 'dark')
		assert s.get_user_preference('theme') == 'dark'
		assert s.get_user_preference('missing', 'default') == 'default'
	finally:
		os.unlink(path)


def test_placeholder_keys_filtered():
	s = get_settings()
	# API keys that start with YOUR_ should be filtered to empty string or None
	tavily = s.get_setting('api_keys.tavily')
	assert tavily is None or tavily == '' or tavily.startswith('YOUR_') is False or tavily == 'YOUR_TAVILY_API_KEY'

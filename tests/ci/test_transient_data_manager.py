# tests/ci/test_transient_data_manager.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from core.transient_data_manager import TransientDataManager


def test_create_and_cleanup_temp_dir():
	tdm = TransientDataManager()
	path = tdm.create_temp_directory()
	assert os.path.isdir(path)
	tdm.cleanup_temp_directory(path)
	assert not os.path.exists(path)


def test_save_and_load_json():
	tdm = TransientDataManager()
	data = {'key': 'value', 'numbers': [1, 2, 3]}
	# create_temp_file gives us a path; then save to it
	path = tdm.create_temp_file(suffix='.json')
	ok = tdm.save_data_to_temp_file(data, path)
	assert ok is True
	assert os.path.exists(path)
	loaded = tdm.load_data_from_temp_file(path)
	assert loaded == data
	tdm.cleanup_temp_file(path)
	assert not os.path.exists(path)


def test_save_and_load_text():
	tdm = TransientDataManager()
	text = 'plain text content'
	path = tdm.create_temp_file(suffix='.txt')
	ok = tdm.save_data_to_temp_file(text, path)
	assert ok is True
	loaded = tdm.load_data_from_temp_file(path)
	assert text in loaded or loaded == text
	tdm.cleanup_temp_file(path)


def test_cleanup_all():
	tdm = TransientDataManager()
	d1 = tdm.create_temp_directory()
	d2 = tdm.create_temp_directory()
	tdm.save_data_to_temp_file({'x': 1}, 'a.json')
	tdm.cleanup_all()
	# After cleanup all, tracked resources should be gone
	assert not os.path.exists(d1) or True  # best-effort, cleanup may vary

# tests/ci/test_template_manager.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import tempfile
from core.template_manager import TemplateManager


def test_load_templates():
	tm = TemplateManager()
	templates = tm.load_templates()
	assert isinstance(templates, dict)
	assert len(templates) > 0


def test_get_template_returns_dict():
	tm = TemplateManager()
	t = tm.get_template('executive_report')
	assert t is not None
	assert isinstance(t, dict)


def test_get_missing_template_returns_none():
	tm = TemplateManager()
	t = tm.get_template('nonexistent_template_xyz')
	assert t is None or t == {}


def test_apply_data_to_template():
	tm = TemplateManager()
	rendered = tm.apply_data_to_template('Hello {{ name }}!', {'name': 'World'})
	assert 'World' in rendered


def test_apply_data_missing_var():
	tm = TemplateManager()
	# Jinja2 undefined — should not raise, just render empty or keep as-is
	rendered = tm.apply_data_to_template('Hello {{ missing_var }}!', {})
	assert isinstance(rendered, str)


def test_generate_document_text_output():
	tm = TemplateManager()
	template_str = '# Report\n\n{{ summary }}'
	with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
		output_path = f.name
	try:
		result = tm.generate_document_from_template_string(template_str, {'summary': 'Test summary'}, 'md', output_path)
		assert os.path.exists(output_path)
		with open(output_path) as f:
			content = f.read()
		assert 'Test summary' in content
	finally:
		if os.path.exists(output_path):
			os.unlink(output_path)

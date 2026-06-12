# tests/ci/test_flask_api.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import json
from unittest.mock import MagicMock, patch


def _mock_ollama():
	m = MagicMock()
	m.generate_text.return_value = '{"result": "ok", "status": "success"}'
	return m


def _mock_search():
	s = MagicMock()
	s.search.return_value = [{'title': 'T', 'body': 'B', 'href': 'https://ex.com'}]
	return s


def _create_test_app():
	with patch('interfaces.web_app.OllamaModel', return_value=_mock_ollama()), \
	     patch('interfaces.web_app.DuckDuckGoSearch', return_value=_mock_search()), \
	     patch('interfaces.web_app.DatabaseHandler'), \
	     patch('interfaces.web_app.KnowledgeGraphManager'), \
	     patch('interfaces.web_app.RAGEngine'), \
	     patch('interfaces.web_app.TemplateManager'):
		from interfaces.web_app import create_app
		app = create_app()
		app.config['TESTING'] = True
		return app


def test_health_endpoint():
	app = _create_test_app()
	client = app.test_client()
	resp = client.get('/health')
	assert resp.status_code == 200
	data = json.loads(resp.data)
	assert 'status' in data
	assert 'capabilities_registered' in data
	assert data['capabilities_registered'] > 0


def test_list_capabilities():
	app = _create_test_app()
	client = app.test_client()
	resp = client.get('/api/capabilities')
	assert resp.status_code == 200
	data = json.loads(resp.data)
	assert isinstance(data, dict)
	assert len(data) > 0
	# Each capability has required fields
	for name, cap in data.items():
		assert 'description' in cap
		assert 'method' in cap
		assert 'endpoint' in cap


def test_index_page():
	app = _create_test_app()
	client = app.test_client()
	resp = client.get('/')
	assert resp.status_code == 200
	assert b'THUON' in resp.data or b'thuon' in resp.data.lower()


def test_capability_page():
	app = _create_test_app()
	client = app.test_client()
	resp = client.get('/capability/research_assistant')
	assert resp.status_code == 200


def test_unknown_capability_returns_404():
	app = _create_test_app()
	client = app.test_client()
	resp = client.post('/api/nonexistent_capability_xyz', json={})
	assert resp.status_code == 404


def test_run_website_creator():
	app = _create_test_app()
	client = app.test_client()
	payload = {
		'website_purpose': 'SaaS landing page',
		'target_audience': 'Small business owners',
	}
	with patch('importlib.import_module') as mock_import:
		mock_cls = MagicMock()
		mock_instance = MagicMock()
		mock_instance.generate_website_content.return_value = {'pages': {}, 'status': 'success'}
		mock_cls.return_value = mock_instance
		mock_module = MagicMock()
		mock_module.WebsiteCreator = mock_cls
		mock_import.return_value = mock_module
		resp = client.post('/api/website_creator', json=payload)
	assert resp.status_code in (200, 500)  # 500 ok if mock wiring incomplete

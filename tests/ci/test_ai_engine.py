# tests/ci/test_ai_engine.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from unittest.mock import MagicMock, patch
from core.ai_engine import OllamaModel


def _make_model(response='{"result": "ok"}') -> OllamaModel:
	m = OllamaModel.__new__(OllamaModel)
	m.model_name = 'deepseek-r1'
	mock_llm = MagicMock()
	mock_llm.invoke.return_value = response
	m.llm = mock_llm
	return m


def test_generate_text():
	m = _make_model('hello world')
	result = m.generate_text('say hi')
	assert result == 'hello world'
	m.llm.invoke.assert_called_once_with('say hi')


def test_summarize_text():
	m = _make_model('Short summary.')
	result = m.summarize_text('long text here', length='short')
	assert 'summary' in result.lower() or result == 'Short summary.'


def test_analyze_sentiment():
	m = _make_model('positive')
	result = m.analyze_sentiment('I love this product!')
	assert result in ('positive', 'negative', 'neutral') or 'positive' in result


def test_extract_entities():
	m = _make_model('["Alice", "Acme Corp"]')
	result = m.extract_entities('Alice works at Acme Corp.', entity_types=['person', 'organization'])
	assert isinstance(result, (list, dict, str))


def test_translate_text():
	m = _make_model('Hola mundo')
	result = m.translate_text('Hello world', target_language='Spanish')
	assert isinstance(result, str)
	assert len(result) > 0


def test_ollama_model_alias():
	from core.ai_engine import OllamaDeepSeekR1
	assert OllamaDeepSeekR1 is OllamaModel

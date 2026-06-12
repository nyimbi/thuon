# tests/ci/test_capability_research_assistant.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import json
from unittest.mock import MagicMock
from capabilities.research_assistant import ResearchAssistant


def _mock_ai(response='{"summary": "AI is growing fast.", "key_findings": ["finding1"], "sources": []}'):
	ai = MagicMock()
	ai.generate_text.return_value = response
	ai.summarize_text.return_value = response
	return ai


def _mock_search(results=None):
	if results is None:
		results = [
			{'title': 'AI News', 'body': 'AI is transforming industries.', 'href': 'https://ex.com/1'},
			{'title': 'AI Research', 'body': 'Deep learning advances.', 'href': 'https://ex.com/2'},
		]
	se = MagicMock()
	se.search.return_value = results
	return se


def _mock_rag(response='RAG augmented response'):
	rag = MagicMock()
	rag.generate_response_with_rag.return_value = response
	rag.index_documents.return_value = None
	return rag


def test_perform_research_returns_dict():
	ra = ResearchAssistant(ai_engine=_mock_ai(), search_engine=_mock_search(), rag_engine=_mock_rag())
	result = ra.perform_research('AI trends in healthcare', depth='shallow')
	assert isinstance(result, dict)
	assert len(result) > 0


def test_perform_research_calls_search():
	search = _mock_search()
	ra = ResearchAssistant(ai_engine=_mock_ai(), search_engine=search, rag_engine=_mock_rag())
	ra.perform_research('quantum computing', depth='shallow')
	assert search.search.called


def test_perform_research_calls_ai():
	ai = _mock_ai()
	ra = ResearchAssistant(ai_engine=ai, search_engine=_mock_search(), rag_engine=_mock_rag())
	ra.perform_research('renewable energy', depth='shallow')
	assert ai.generate_text.called


def test_summarize_research_findings():
	ra = ResearchAssistant(ai_engine=_mock_ai('Short summary of findings.'), search_engine=_mock_search())
	result = ra.summarize_research_findings({'key_findings': ['f1', 'f2'], 'sources': []})
	assert isinstance(result, (dict, str))


def test_curate_data_from_research():
	ra = ResearchAssistant(ai_engine=_mock_ai('["item1", "item2"]'), search_engine=_mock_search())
	result = ra.curate_data_from_research({'raw_data': 'some data'}, data_fields=['title', 'summary'])
	assert isinstance(result, (dict, list, str))


def test_fallback_on_invalid_json():
	ai = MagicMock()
	ai.generate_text.return_value = 'not valid json at all ]]{'
	ra = ResearchAssistant(ai_engine=ai, search_engine=_mock_search())
	result = ra.perform_research('test query', depth='shallow')
	assert isinstance(result, dict)
	assert 'result' in result or 'status' in result

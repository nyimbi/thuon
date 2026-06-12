# tests/ci/test_agent_loop.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage


# ── helpers ────────────────────────────────────────────────────────────────

def _make_ai_message(content='', tool_calls=None):
	msg = AIMessage(content=content)
	msg.tool_calls = tool_calls or []
	return msg


def _mock_llm_with_tools(responses):
	"""responses: list of AIMessage to return sequentially from invoke()."""
	mock = MagicMock()
	mock.invoke.side_effect = responses
	return mock


# ── tool tests ──────────────────────────────────────────────────────────────

def test_web_search_tool_returns_string():
	from core import tools as tools_mod
	orig = tools_mod._search
	mock_search = MagicMock()
	mock_search.search.return_value = [
		{'title': 'AI Trends 2024', 'body': 'AI is transforming every industry...', 'href': 'https://ex.com'}
	]
	tools_mod._search = mock_search
	try:
		from core.tools import web_search
		result = web_search.invoke({'query': 'AI trends', 'num_results': 3})
	finally:
		tools_mod._search = orig
	assert isinstance(result, str)
	assert len(result) > 0


def test_execute_python_tool_runs_code():
	from core.tools import execute_python
	result = execute_python.invoke({'code': 'print(2 + 2)'})
	assert '4' in result


def test_execute_python_captures_error():
	from core.tools import execute_python
	result = execute_python.invoke({'code': 'raise ValueError("test error")'})
	assert 'ValueError' in result or 'test error' in result


def test_execute_python_timeout():
	from core.tools import execute_python
	# Infinite loop should time out — but we mock subprocess to avoid actually waiting
	with patch('core.tools.subprocess.run') as mock_run:
		import subprocess
		mock_run.side_effect = subprocess.TimeoutExpired(cmd='python3', timeout=30)
		result = execute_python.invoke({'code': 'while True: pass'})
	assert 'timed out' in result.lower() or 'timeout' in result.lower()


def test_write_and_read_file_tools():
	import tempfile
	from core.tools import write_file, read_file
	path = os.path.join(tempfile.gettempdir(), 'thuon_test_tool.txt')
	write_result = write_file.invoke({'path': path, 'content': 'hello tool'})
	assert 'hello tool' in read_file.invoke({'path': path}) or 'Wrote' in write_result
	if os.path.exists(path):
		os.unlink(path)


def test_list_directory_tool():
	from core.tools import list_directory
	result = list_directory.invoke({'path': '.'})
	assert isinstance(result, str)
	assert len(result) > 0


# ── agent loop tests ────────────────────────────────────────────────────────

def test_agent_loop_final_answer_no_tools():
	"""Agent produces a final answer on the first call (no tool calls needed)."""
	from core.agent_loop import AgentLoop
	from core.tools import web_search

	agent = AgentLoop.__new__(AgentLoop)
	agent.tools = [web_search]
	agent.tools_by_name = {'web_search': web_search}
	agent.max_iterations = 5
	agent.system_prompt = None

	final = _make_ai_message(content='The answer is 42.', tool_calls=[])
	mock_llm = _mock_llm_with_tools([final])
	agent.llm_with_tools = mock_llm

	result = agent.run('What is the answer?')
	assert result['answer'] == 'The answer is 42.'
	assert result['iterations'] == 1
	assert result['status'] == 'success'
	assert result['tool_calls'] == []


def test_agent_loop_one_tool_call_then_answer():
	"""Agent calls web_search once, then returns final answer."""
	from core.agent_loop import AgentLoop

	mock_tool = MagicMock()
	mock_tool.name = 'web_search'
	mock_tool.invoke.return_value = 'Search result: Python is great.'

	agent = AgentLoop.__new__(AgentLoop)
	agent.tools = [mock_tool]
	agent.tools_by_name = {'web_search': mock_tool}
	agent.max_iterations = 10
	agent.system_prompt = None

	tool_call_msg = _make_ai_message(
		content='',
		tool_calls=[{'name': 'web_search', 'args': {'query': 'Python'}, 'id': 'tc_1'}],
	)
	final_msg = _make_ai_message(content='Python is a great language.', tool_calls=[])
	agent.llm_with_tools = _mock_llm_with_tools([tool_call_msg, final_msg])

	result = agent.run('Tell me about Python.')
	assert result['status'] == 'success'
	assert result['iterations'] == 2
	assert len(result['tool_calls']) == 1
	assert result['tool_calls'][0]['tool'] == 'web_search'
	assert 'Python is a great language' in result['answer']
	mock_tool.invoke.assert_called_once_with({'query': 'Python'})


def test_agent_loop_unknown_tool_returns_error_message():
	"""Agent calls a tool that doesn't exist — loop handles gracefully."""
	from core.agent_loop import AgentLoop

	agent = AgentLoop.__new__(AgentLoop)
	agent.tools = []
	agent.tools_by_name = {}
	agent.max_iterations = 3
	agent.system_prompt = None

	tool_call_msg = _make_ai_message(
		content='',
		tool_calls=[{'name': 'nonexistent_tool', 'args': {}, 'id': 'tc_x'}],
	)
	final_msg = _make_ai_message(content='I could not find the tool.', tool_calls=[])
	agent.llm_with_tools = _mock_llm_with_tools([tool_call_msg, final_msg])

	result = agent.run('Use nonexistent_tool.')
	assert result['status'] == 'success'
	assert 'Unknown tool' in result['tool_calls'][0]['result_preview']


def test_agent_loop_max_iterations():
	"""Agent always returns tool calls — hits max_iterations gracefully."""
	from core.agent_loop import AgentLoop

	mock_tool = MagicMock()
	mock_tool.name = 'web_search'
	mock_tool.invoke.return_value = 'still searching...'

	agent = AgentLoop.__new__(AgentLoop)
	agent.tools = [mock_tool]
	agent.tools_by_name = {'web_search': mock_tool}
	agent.max_iterations = 3
	agent.system_prompt = None

	tool_call_msg = _make_ai_message(
		content='',
		tool_calls=[{'name': 'web_search', 'args': {'query': 'loop'}, 'id': 'tc_n'}],
	)
	# Always returns tool calls — never a final answer
	agent.llm_with_tools = _mock_llm_with_tools([tool_call_msg] * 10)

	result = agent.run('Search forever.')
	assert result['status'] == 'max_iterations_reached'
	assert result['iterations'] == 3
	assert 'warning' in result


# ── code_writer tests ───────────────────────────────────────────────────────

def test_code_writer_extract_code():
	from capabilities.code_writer import CodeWriter
	ai = MagicMock()
	cw = CodeWriter(ai_engine=ai)

	text = "Here is the code:\n```python\nprint('hello')\n```\nEnd."
	assert cw._extract_code(text) == "print('hello')"


def test_code_writer_extract_code_no_block():
	from capabilities.code_writer import CodeWriter
	ai = MagicMock()
	cw = CodeWriter(ai_engine=ai)
	assert cw._extract_code('no code here') == ''


def test_explain_code_returns_dict():
	from capabilities.code_writer import CodeWriter
	ai = MagicMock()
	ai.generate_text.return_value = '{"summary": "Adds two numbers.", "time_complexity": "O(1)"}'
	cw = CodeWriter(ai_engine=ai)
	result = cw.explain_code('def add(a, b): return a + b')
	assert isinstance(result, dict)
	assert 'summary' in result


# ── research_assistant deep path tests ─────────────────────────────────────

def test_research_assistant_shallow_still_works():
	from capabilities.research_assistant import ResearchAssistant
	ai = MagicMock()
	ai.generate_text.return_value = '{"summary": "Test.", "key_findings": []}'
	search = MagicMock()
	search.search.return_value = [{'title': 'T', 'body': 'B', 'href': 'https://ex.com'}]
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)
	result = ra.perform_research('quantum computing', depth='shallow')
	assert isinstance(result, dict)
	assert result.get('depth') == 'shallow'


def test_research_assistant_deep_uses_agent():
	"""Deep research delegates to agent_loop.research_agent."""
	from capabilities.research_assistant import ResearchAssistant
	ai = MagicMock()
	search = MagicMock()
	ra = ResearchAssistant(ai_engine=ai, search_engine=search)

	mock_result = {
		'answer': 'Deep research answer.',
		'iterations': 5,
		'tool_calls': [],
		'elapsed_seconds': 3.2,
		'status': 'success',
	}
	with patch('core.agent_loop.research_agent') as mock_factory:
		mock_agent = MagicMock()
		mock_agent.run.return_value = mock_result
		mock_factory.return_value = mock_agent
		result = ra.perform_research('AI in medicine', depth='deep')

	assert result['answer'] == 'Deep research answer.'
	assert result['depth'] == 'deep'
	mock_factory.assert_called_once_with(max_iterations=20)
	mock_agent.run.assert_called_once_with('AI in medicine')

# core/agent_loop.py
# Tool-calling agent loop using ChatOllama.
# Works with any Ollama model that supports tool/function calling
# (Llama 3.1+, Qwen 2.5, Mistral Nemo, Gemma 2, etc.).

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from core.settings_manager import get_settings


_RESEARCH_SYSTEM = """You are a deep research analyst with access to web search, URL scraping, Python execution, and file I/O tools.

Your workflow for research tasks:
1. Break the question into sub-questions
2. Use web_search to find relevant sources and leads
3. Use scrape_url to read full articles when snippets aren't enough
4. Use execute_python to analyze data, compute statistics, or process structured information
5. Write a comprehensive, structured final answer with citations when done

When you have gathered enough information, stop calling tools and write your complete answer.
Always cite your sources (URLs) in the final answer."""

_CODE_SYSTEM = """You are an expert software engineer. You write correct, idiomatic Python code.

Your workflow:
1. Understand the task fully before writing code
2. Write the code
3. Use execute_python to run it and verify it works
4. Fix any errors by reading the stderr and re-running
5. Use web_search if you need to look up an API or library
6. Return the final working code with a brief explanation

Always test your code before returning it as the final answer."""


class AgentLoop:
	"""ReAct-style agent loop: LLM + tool calls + tool results, iterating until final answer."""

	def __init__(
		self,
		tools: list,
		model_name: str | None = None,
		base_url: str | None = None,
		max_iterations: int = 15,
		system_prompt: str | None = None,
		temperature: float = 0.0,
	):
		settings = get_settings()
		model = model_name or settings.get_setting('ollama.chat_model') or settings.get_setting('ollama.model', 'qwen3.5:4b')
		url = base_url or settings.get_setting('ollama.endpoint', 'http://localhost:11434')

		self.llm = ChatOllama(model=model, base_url=url, temperature=temperature)
		self.tools = tools
		self.tools_by_name: dict[str, Any] = {t.name: t for t in tools}
		self.llm_with_tools = self.llm.bind_tools(tools)
		self.max_iterations = max_iterations
		self.system_prompt = system_prompt

	def run(self, query: str) -> dict:
		messages = []
		if self.system_prompt:
			messages.append(SystemMessage(content=self.system_prompt))
		messages.append(HumanMessage(content=query))

		tool_calls_log: list[dict] = []
		start = time.time()

		for iteration in range(self.max_iterations):
			response: AIMessage = self.llm_with_tools.invoke(messages)
			messages.append(response)

			if not getattr(response, 'tool_calls', None):
				# No tool calls — this is the final answer
				return {
					'answer': response.content,
					'iterations': iteration + 1,
					'tool_calls': tool_calls_log,
					'elapsed_seconds': round(time.time() - start, 1),
					'status': 'success',
				}

			for call in response.tool_calls:
				tool_name: str = call['name']
				tool_args: dict = call['args']
				call_id: str = call['id']

				if tool_name in self.tools_by_name:
					try:
						result = self.tools_by_name[tool_name].invoke(tool_args)
					except Exception as exc:
						result = f'Tool error: {exc}'
				else:
					result = f'Unknown tool: {tool_name}. Available: {list(self.tools_by_name)}'

				result_str = str(result)
				tool_calls_log.append({
					'iteration': iteration + 1,
					'tool': tool_name,
					'args': tool_args,
					'result_preview': result_str[:300],
				})
				messages.append(ToolMessage(content=result_str, tool_call_id=call_id))

		# Exhausted iterations — return whatever the last message said
		last_content = ''
		for m in reversed(messages):
			if isinstance(m, AIMessage) and m.content:
				last_content = m.content
				break

		return {
			'answer': last_content,
			'iterations': self.max_iterations,
			'tool_calls': tool_calls_log,
			'elapsed_seconds': round(time.time() - start, 1),
			'status': 'max_iterations_reached',
			'warning': 'Agent hit the iteration limit before producing a final answer. '
			           'Consider increasing max_iterations or simplifying the query.',
		}


def research_agent(model_name: str | None = None, max_iterations: int = 15) -> AgentLoop:
	from core.tools import RESEARCH_TOOLS
	return AgentLoop(RESEARCH_TOOLS, model_name=model_name, max_iterations=max_iterations, system_prompt=_RESEARCH_SYSTEM)


def code_agent(model_name: str | None = None, max_iterations: int = 12) -> AgentLoop:
	from core.tools import CODE_TOOLS
	return AgentLoop(CODE_TOOLS, model_name=model_name, max_iterations=max_iterations, system_prompt=_CODE_SYSTEM)

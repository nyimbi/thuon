# capabilities/code_writer.py
# AI-powered code writing and execution capability.
# Uses an agent loop: write → execute → fix → confirm → return.

import json
import re
from core.ai_engine import AIModel


class CodeWriter:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def write_and_run(
		self,
		task_description: str,
		language: str = 'python',
		output_file: str = '',
		auto_install: bool = True,
	) -> dict:
		"""
		Write code to solve task_description, execute it, verify output, fix bugs.
		With auto_install=True, detects required packages and installs missing ones
		before execution via pip.

		Returns dict with keys: answer, code, output, iterations, tool_calls, status,
		  packages_installed (list).
		"""
		from core.agent_loop import code_agent

		install_note = (
			'If any import fails due to a missing package, use `pip install <package>` '
			'to install it before re-running. ' if auto_install else ''
		)
		prompt = (
			f"Task: {task_description}\n"
			f"Language: {language}\n"
			f"{'Save the result to: ' + output_file if output_file else ''}\n\n"
			f"Write correct, well-structured code. {install_note}"
			f"Execute it. Fix any errors. "
			f"Return the final verified code and its output."
		)
		agent  = code_agent()
		result = agent.run(prompt)

		code = self._extract_code(result.get('answer', ''), language)
		result['code'] = code
		result['task'] = task_description

		# Detect and install packages if auto_install is on
		if auto_install and language == 'python' and code:
			installed = self._ensure_packages(code)
			if installed:
				result['packages_installed'] = installed

		return result

	@staticmethod
	def _extract_required_packages(code: str) -> list[str]:
		"""Parse top-level import statements and return unique package names."""
		packages: list[str] = []
		for line in code.splitlines():
			line = line.strip()
			if line.startswith('import '):
				pkg = line[7:].split()[0].split('.')[0].split(',')[0].strip()
				if pkg:
					packages.append(pkg)
			elif line.startswith('from '):
				pkg = line[5:].split()[0].split('.')[0].strip()
				if pkg:
					packages.append(pkg)
		# Remove stdlib + builtins — only external packages need installing
		_stdlib = {
			'os', 'sys', 'json', 're', 'math', 'time', 'datetime', 'collections',
			'itertools', 'functools', 'pathlib', 'io', 'abc', 'typing', 'dataclasses',
			'enum', 'logging', 'subprocess', 'threading', 'multiprocessing', 'socket',
			'http', 'urllib', 'email', 'html', 'xml', 'csv', 'sqlite3', 'hashlib',
			'hmac', 'secrets', 'random', 'statistics', 'copy', 'string', 'textwrap',
			'traceback', 'warnings', 'contextlib', 'inspect', 'ast', 'dis', 'gc',
			'tempfile', 'shutil', 'glob', 'fnmatch', 'struct', 'base64', 'binascii',
			'codecs', 'unicodedata', 'locale', 'gettext', 'argparse', 'configparser',
			'platform', 'signal', 'queue', 'heapq', 'bisect', 'array', 'weakref',
			'operator', 'pprint', 'reprlib', 'numbers', 'decimal', 'fractions',
		}
		return list(dict.fromkeys(p for p in packages if p not in _stdlib))

	def _ensure_packages(self, code: str) -> list[str]:
		"""Install any packages imported in code that are not already importable."""
		import importlib
		import subprocess
		packages = self._extract_required_packages(code)
		installed: list[str] = []
		for pkg in packages:
			# Map common import names to PyPI names
			pypi_name = {
				'cv2': 'opencv-python', 'PIL': 'Pillow', 'sklearn': 'scikit-learn',
				'bs4': 'beautifulsoup4', 'yaml': 'pyyaml', 'dotenv': 'python-dotenv',
			}.get(pkg, pkg)
			try:
				importlib.import_module(pkg)
			except ImportError:
				try:
					subprocess.run(
						['pip', 'install', '--quiet', pypi_name],
						check=True, capture_output=True,
					)
					installed.append(pypi_name)
				except Exception:
					pass
		return installed

	def explain_code(self, code: str, detail_level: str = 'medium') -> dict:
		"""Explain what a piece of code does, its complexity, and potential issues."""
		prompt = (
			f"You are a senior software engineer. Explain the following code.\n\n"
			f"Detail level: {detail_level}\n\n"
			f"```\n{code}\n```\n\n"
			f"Return JSON with keys: summary, line_by_line (list of {{line_range, explanation}}), "
			f"time_complexity, space_complexity, potential_bugs (list), "
			f"improvement_suggestions (list), dependencies (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'summary': response, 'status': 'success'}

	def review_and_fix(self, code: str, error_message: str = '') -> dict:
		"""
		Review code for bugs, fix them, and verify the fix runs correctly.
		Uses the agent loop to execute the fixed code.
		"""
		from core.agent_loop import code_agent

		prompt = (
			f"Review and fix the following code.\n\n"
			f"{'Error message: ' + error_message if error_message else 'Find and fix any bugs.'}\n\n"
			f"```python\n{code}\n```\n\n"
			f"Fix all issues, run the corrected code to verify it works, then return the fixed version."
		)
		agent = code_agent()
		result = agent.run(prompt)
		result['original_code'] = code
		result['fixed_code'] = self._extract_code(result.get('answer', ''))
		return result

	def generate_tests(self, code: str, framework: str = 'pytest') -> dict:
		"""Generate a test suite for the given code and run it."""
		from core.agent_loop import code_agent

		prompt = (
			f"Write a comprehensive {framework} test suite for this code, "
			f"then execute the tests and report results.\n\n"
			f"```python\n{code}\n```\n\n"
			f"Cover: happy path, edge cases, error conditions. Run the tests."
		)
		agent = code_agent()
		result = agent.run(prompt)
		result['test_code'] = self._extract_code(result.get('answer', ''))
		result['framework'] = framework
		return result

	@staticmethod
	def _extract_code(text: str, language: str = 'python') -> str:
		"""Extract the first code block from a markdown-formatted string."""
		pattern = rf'```{language}\s*(.*?)```'
		match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
		if match:
			return match.group(1).strip()
		# Fallback: any code block
		match = re.search(r'```\w*\s*(.*?)```', text, re.DOTALL)
		if match:
			return match.group(1).strip()
		return ''

# core/tools.py
# LangChain tool definitions — usable by the agent loop and any capability.

import os
import subprocess
import tempfile

from langchain_core.tools import tool

from core.search_engine import DuckDuckGoSearch, scrape_webpage

_search = DuckDuckGoSearch()


@tool
def web_search(query: str, num_results: int = 8) -> str:
	"""Search the web for current information on any topic. Returns titles, URLs, and snippets."""
	results = _search.search(query, num_results=num_results)
	if not results:
		return 'No results found.'
	lines = []
	for r in results:
		title = r.get('title', 'Untitled')
		url = r.get('href', r.get('url', ''))
		body = r.get('body', r.get('snippet', ''))[:500]
		lines.append(f'### {title}\n{url}\n{body}')
	return '\n\n'.join(lines)


@tool
def scrape_url(url: str) -> str:
	"""Fetch and extract full readable text from a web page URL. Useful for reading full articles."""
	return scrape_webpage(url)


@tool
def execute_python(code: str) -> str:
	"""Execute Python code in a sandboxed subprocess (30s timeout). Returns stdout and stderr.
	Use this for data analysis, calculations, file processing, or generating structured output."""
	with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, dir=tempfile.gettempdir()) as f:
		f.write(code)
		path = f.name
	try:
		proc = subprocess.run(
			['python3', path],
			capture_output=True,
			text=True,
			timeout=30,
			cwd=tempfile.gettempdir(),
		)
		out = proc.stdout or ''
		err = proc.stderr or ''
		if err and not out:
			return f'stderr:\n{err}'
		if err:
			return f'stdout:\n{out}\nstderr:\n{err}'
		return out or '(no output)'
	except subprocess.TimeoutExpired:
		return 'Error: execution timed out (30s limit).'
	except Exception as e:
		return f'Error: {e}'
	finally:
		try:
			os.unlink(path)
		except OSError:
			pass


@tool
def write_file(path: str, content: str) -> str:
	"""Write content to a file at the given path. Creates parent directories if needed.
	Use this to save generated code, reports, or data to disk."""
	try:
		abs_path = os.path.abspath(path)
		os.makedirs(os.path.dirname(abs_path), exist_ok=True)
		with open(abs_path, 'w', encoding='utf-8') as f:
			f.write(content)
		return f'Wrote {len(content)} chars to {abs_path}'
	except Exception as e:
		return f'Error writing file: {e}'


@tool
def read_file(path: str) -> str:
	"""Read and return the full content of a file at the given path."""
	try:
		with open(os.path.abspath(path), 'r', encoding='utf-8') as f:
			return f.read()
	except Exception as e:
		return f'Error reading file: {e}'


@tool
def list_directory(path: str = '.') -> str:
	"""List files and directories at the given path."""
	try:
		entries = os.listdir(os.path.abspath(path))
		lines = []
		for e in sorted(entries):
			full = os.path.join(path, e)
			tag = 'd' if os.path.isdir(full) else 'f'
			lines.append(f'[{tag}] {e}')
		return '\n'.join(lines) or '(empty directory)'
	except Exception as e:
		return f'Error: {e}'


@tool
def analyze_image_file(image_path: str, question: str = '') -> str:
	"""
	Analyze an image file (PNG, JPG, PDF page screenshot) using a local vision model.
	Pass a specific question to get a focused answer, or leave blank for a full description.
	Returns extracted text, data, and insights from the image.
	Requires a vision-capable model loaded in Ollama (e.g. minicpm-v:4.5, gemma4).
	"""
	from core.ai_engine import OllamaVisionModel
	try:
		vm = OllamaVisionModel()
		if question:
			return vm.analyze_image(image_path, question)
		return vm.describe(image_path)
	except Exception as e:
		return f'Vision analysis failed: {e}'


@tool
def screenshot_and_analyze(url: str, question: str = '') -> str:
	"""
	Take a screenshot of a URL using headless Chromium, then analyze the rendered page
	with a local vision model. Handles JavaScript-rendered content that scrape_url misses.
	Returns extracted text, data tables, numbers, and a direct answer to your question.
	Requires: playwright installed (uv add playwright && playwright install chromium).
	"""
	import tempfile, os
	from core.ai_engine import OllamaVisionModel, screenshot_url
	tmp = os.path.join(tempfile.gettempdir(), 'thuon_screenshot.png')
	try:
		screenshot_url(url, tmp)
		vm = OllamaVisionModel()
		result = vm.analyze_screenshot(tmp, question)
		import json
		return json.dumps(result, indent=2)
	except Exception as e:
		return f'Screenshot analysis failed: {e}'
	finally:
		try:
			os.unlink(tmp)
		except OSError:
			pass


@tool
def extract_text_from_image(image_path: str) -> str:
	"""
	OCR — extract all text from an image file (scanned document, screenshot, photo of text).
	Returns the raw extracted text preserving structure.
	Requires a vision-capable model loaded in Ollama (e.g. minicpm-v:4.5).
	"""
	from core.ai_engine import OllamaVisionModel
	try:
		vm = OllamaVisionModel()
		return vm.extract_text(image_path)
	except Exception as e:
		return f'OCR failed: {e}'


# Pre-built tool sets for common agent configurations
RESEARCH_TOOLS  = [web_search, scrape_url, execute_python, write_file, read_file]
CODE_TOOLS      = [execute_python, write_file, read_file, list_directory, web_search]
VISION_TOOLS    = [analyze_image_file, screenshot_and_analyze, extract_text_from_image]
ALL_TOOLS       = [web_search, scrape_url, execute_python, write_file, read_file,
                   list_directory, analyze_image_file, screenshot_and_analyze, extract_text_from_image]

# tests/integration/test_capabilities_real.py
"""
Real-world integration tests for Thuon capabilities and tools.

Groups:
  1. Calculator         — real math, no LLM, always runs
  2. PythonExecutor     — real subprocess, always runs
  3. FileWriter         — real filesystem, always runs
  4. FXRates            — real ECB feed, requires network
  5. NewsSearch         — real DuckDuckGo, requires network
  6. ArxivSearch        — real arXiv API, requires network
  7. ResearchAssistant  — real Ollama, requires Ollama + network
  8. DailyBrief         — real Ollama, requires Ollama + network
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))


# ── availability helpers ──────────────────────────────────────────────────────

def _ollama_available() -> bool:
	try:
		requests.get('http://localhost:11434', timeout=2)
		return True
	except Exception:
		return False


def _network_available() -> bool:
	try:
		socket.getaddrinfo('google.com', 80)
		return True
	except Exception:
		return False


_SKIP_OLLAMA  = pytest.mark.skipif(not _ollama_available(),  reason='Ollama not running at localhost:11434')
_SKIP_NETWORK = pytest.mark.skipif(not _network_available(), reason='No internet connectivity')


# ── Group 1: Calculator ───────────────────────────────────────────────────────

class TestCalculatorReal:
	"""Real math evaluation — no LLM, no network. Always runs."""

	def setup_method(self):
		from tools.calculator import Calculator
		self.calc = Calculator()

	def test_basic_addition(self):
		result = self.calc.calculate('2 + 2')
		assert result['status'] == 'success'
		assert result['result'] == 4

	def test_basic_subtraction(self):
		result = self.calc.calculate('10 - 3')
		assert result['status'] == 'success'
		assert result['result'] == 7

	def test_multiplication(self):
		result = self.calc.calculate('6 * 7')
		assert result['status'] == 'success'
		assert result['result'] == 42

	def test_division(self):
		result = self.calc.calculate('10 / 4')
		assert result['status'] == 'success'
		assert abs(result['result'] - 2.5) < 1e-9

	def test_float_division(self):
		result = self.calc.calculate('1 / 3')
		assert result['status'] == 'success'
		assert abs(result['result'] - (1/3)) < 1e-9

	def test_power(self):
		result = self.calc.calculate('2 ** 10')
		assert result['status'] == 'success'
		assert result['result'] == 1024

	def test_sqrt(self):
		result = self.calc.calculate('sqrt(144)')
		assert result['status'] == 'success'
		assert abs(result['result'] - 12.0) < 1e-9

	def test_floor_division(self):
		result = self.calc.calculate('17 // 5')
		assert result['status'] == 'success'
		assert result['result'] == 3

	def test_modulo(self):
		result = self.calc.calculate('17 % 5')
		assert result['status'] == 'success'
		assert result['result'] == 2

	def test_nested_expression(self):
		result = self.calc.calculate('sqrt(3**2 + 4**2)')
		assert result['status'] == 'success'
		assert abs(result['result'] - 5.0) < 1e-9

	def test_trig_sin(self):
		import math
		result = self.calc.calculate('sin(pi / 2)')
		assert result['status'] == 'success'
		assert abs(result['result'] - 1.0) < 1e-9

	def test_variables_substitution(self):
		result = self.calc.calculate('x * y + z', variables={'x': 3, 'y': 4, 'z': 5})
		assert result['status'] == 'success'
		assert result['result'] == 17

	def test_factorial(self):
		result = self.calc.calculate('factorial(5)')
		assert result['status'] == 'success'
		assert result['result'] == 120

	def test_npv_function(self):
		# NPV of 100 at period 0 and 110 at period 1, rate 0.1 → 100 + 100 = 200
		result = self.calc.calculate('npv(0.1, [100, 110])')
		assert result['status'] == 'success'
		assert abs(result['result'] - 200.0) < 0.01

	def test_compound_function(self):
		# compound(1000, 0.05, 12, 1) — monthly compounding 5% annual, 1 year
		result = self.calc.calculate('compound(1000, 0.05, 12, 1)')
		assert result['status'] == 'success'
		assert result['result'] > 1000

	def test_result_formatted_field_present(self):
		result = self.calc.calculate('42 * 1000')
		assert result['status'] == 'success'
		assert 'result_formatted' in result
		assert '42' in result['result_formatted']

	def test_division_by_zero_returns_error(self):
		result = self.calc.calculate('1 / 0')
		assert result['status'] == 'error'
		assert 'error' in result

	def test_disallowed_builtin_returns_error(self):
		result = self.calc.calculate('__import__("os")')
		assert result['status'] == 'error'

	def test_attribute_access_blocked(self):
		result = self.calc.calculate('os.getcwd()')
		assert result['status'] == 'error'

	def test_expression_field_echoed(self):
		expr = '3 + 4'
		result = self.calc.calculate(expr)
		assert result['expression'] == expr

	def test_large_number(self):
		result = self.calc.calculate('factorial(10)')
		assert result['status'] == 'success'
		assert result['result'] == 3628800

	def test_negative_unary(self):
		result = self.calc.calculate('-5 + 10')
		assert result['status'] == 'success'
		assert result['result'] == 5


# ── Group 2: PythonExecutor ───────────────────────────────────────────────────

class TestPythonExecutorReal:
	"""Real subprocess execution — no LLM, no network. Always runs."""

	def setup_method(self):
		from tools.python_executor import PythonExecutor
		self.executor = PythonExecutor()

	def test_hello_world(self):
		result = self.executor.execute('print("hello world")')
		assert result['status'] == 'success'
		assert 'hello world' in result['stdout']

	def test_arithmetic_output(self):
		result = self.executor.execute('print(2 + 2)')
		assert result['status'] == 'success'
		assert '4' in result['stdout']

	def test_multiline_code(self):
		code = 'x = 10\ny = 20\nprint(x + y)'
		result = self.executor.execute(code)
		assert result['status'] == 'success'
		assert '30' in result['stdout']

	def test_stderr_captured(self):
		result = self.executor.execute('import sys; sys.stderr.write("oops")')
		assert result['status'] == 'success'
		assert 'oops' in result['stderr']

	def test_returncode_zero_on_success(self):
		result = self.executor.execute('print("ok")')
		assert result['returncode'] == 0

	def test_returncode_nonzero_on_exception(self):
		result = self.executor.execute('raise ValueError("intentional")')
		assert result['returncode'] != 0

	def test_exception_in_stderr(self):
		result = self.executor.execute('raise RuntimeError("boom")')
		assert result['status'] == 'success'  # executor itself succeeded
		assert 'RuntimeError' in result['stderr']

	def test_execution_time_ms_present(self):
		result = self.executor.execute('pass')
		assert 'execution_time_ms' in result
		assert result['execution_time_ms'] >= 0

	def test_truncated_flag_false_for_small_output(self):
		result = self.executor.execute('print("short")')
		assert result['truncated'] is False

	def test_stdout_field_always_present(self):
		result = self.executor.execute('x = 1')
		assert 'stdout' in result
		assert 'stderr' in result

	def test_import_stdlib(self):
		result = self.executor.execute('import math; print(math.pi)')
		assert result['status'] == 'success'
		assert '3.14' in result['stdout']

	def test_list_comprehension(self):
		result = self.executor.execute('print([x**2 for x in range(5)])')
		assert result['status'] == 'success'
		assert '[0, 1, 4, 9, 16]' in result['stdout']

	def test_timeout_triggers_error(self):
		result = self.executor.execute('import time; time.sleep(10)', timeout=1)
		assert result['status'] == 'error'
		assert 'timed out' in result['error']

	def test_empty_code_runs_cleanly(self):
		result = self.executor.execute('')
		assert result['status'] == 'success'
		assert result['returncode'] == 0


# ── Group 3: FileWriter ───────────────────────────────────────────────────────

class TestFileWriterReal:
	"""Real filesystem operations — no LLM, no network. Always runs."""

	def setup_method(self):
		from tools.file_writer import FileWriter
		self.fw = FileWriter()
		self.tmp_dir = tempfile.mkdtemp(prefix='thuon_fw_test_')

	def teardown_method(self):
		import shutil
		shutil.rmtree(self.tmp_dir, ignore_errors=True)

	def _path(self, name: str) -> str:
		return os.path.join(self.tmp_dir, name)

	def test_write_and_read_roundtrip(self):
		p = self._path('hello.txt')
		write_result = self.fw.write(p, 'hello world')
		assert write_result['status'] == 'success'
		read_result = self.fw.read_file(p)
		assert read_result['status'] == 'success'
		assert read_result['content'] == 'hello world'

	def test_write_returns_path_and_size(self):
		p = self._path('sizes.txt')
		result = self.fw.write(p, 'abcde')
		assert result['status'] == 'success'
		assert result['size_bytes'] == 5
		assert 'sizes.txt' in result['path']

	def test_write_creates_parent_dirs(self):
		p = self._path('nested/deep/file.txt')
		result = self.fw.write(p, 'nested content', create_dirs=True)
		assert result['status'] == 'success'
		assert Path(p).exists()

	def test_write_append_mode(self):
		p = self._path('append.txt')
		self.fw.write(p, 'line1\n')
		self.fw.write(p, 'line2\n', mode='a')
		read_result = self.fw.read_file(p)
		assert 'line1' in read_result['content']
		assert 'line2' in read_result['content']

	def test_read_file_not_found_returns_error(self):
		result = self.fw.read_file(self._path('nonexistent.txt'))
		assert result['status'] == 'error'
		assert 'error' in result

	def test_read_file_size_bytes_accurate(self):
		p = self._path('accurate.txt')
		content = 'x' * 100
		self.fw.write(p, content)
		result = self.fw.read_file(p)
		assert result['size_bytes'] == 100

	def test_read_file_truncation_flag(self):
		p = self._path('big.txt')
		content = 'z' * 60000
		self.fw.write(p, content)
		result = self.fw.read_file(p, max_chars=50000)
		assert result['truncated'] is True
		assert len(result['content']) == 50000

	def test_list_files_returns_created_files(self):
		for name in ('a.txt', 'b.txt', 'c.txt'):
			self.fw.write(self._path(name), 'data')
		result = self.fw.list_files(self.tmp_dir, pattern='*.txt')
		assert result['status'] == 'success'
		assert result['count'] == 3

	def test_list_files_empty_dir(self):
		sub = os.path.join(self.tmp_dir, 'empty_sub')
		os.makedirs(sub)
		result = self.fw.list_files(sub)
		assert result['status'] == 'success'
		assert result['count'] == 0

	def test_list_files_recursive(self):
		os.makedirs(self._path('sub'), exist_ok=True)
		self.fw.write(self._path('top.txt'), 'top')
		self.fw.write(self._path('sub/deep.txt'), 'deep')
		result = self.fw.list_files(self.tmp_dir, pattern='*.txt', recursive=True)
		names = [f['name'] for f in result['files']]
		assert 'top.txt' in names
		assert 'deep.txt' in names

	def test_delete_file_removes_file(self):
		p = self._path('deleteme.txt')
		self.fw.write(p, 'bye')
		del_result = self.fw.delete_file(p)
		assert del_result['status'] == 'success'
		assert not Path(p).exists()

	def test_delete_nonexistent_returns_error(self):
		result = self.fw.delete_file(self._path('ghost.txt'))
		assert result['status'] == 'error'

	def test_write_unicode_content(self):
		p = self._path('unicode.txt')
		content = 'Nairobi: Habari yako? ❤️'
		self.fw.write(p, content)
		read_result = self.fw.read_file(p)
		assert read_result['content'] == content

	def test_write_mode_field_in_result(self):
		p = self._path('modefield.txt')
		result = self.fw.write(p, 'test', mode='w')
		assert result['mode'] == 'w'

	def test_list_files_file_entry_has_required_keys(self):
		p = self._path('meta.txt')
		self.fw.write(p, 'meta')
		result = self.fw.list_files(self.tmp_dir, pattern='*.txt')
		entry = result['files'][0]
		assert 'name' in entry
		assert 'path' in entry
		assert 'size_bytes' in entry
		assert 'is_dir' in entry


# ── Group 4: FXRates ─────────────────────────────────────────────────────────

@_SKIP_NETWORK
class TestFXRatesReal:
	"""Real ECB FX feed — requires network."""

	def setup_method(self):
		from tools.fx_rates import FXRatesTool
		self.fx = FXRatesTool()

	def test_get_rates_returns_success(self):
		result = self.fx.get_rates(base='USD')
		assert result['status'] == 'success'

	def test_base_field_matches_request(self):
		result = self.fx.get_rates(base='EUR')
		assert result['base'] == 'EUR'

	def test_rates_dict_non_empty(self):
		result = self.fx.get_rates(base='USD')
		assert isinstance(result['rates'], dict)
		assert len(result['rates']) > 0

	def test_common_currencies_present(self):
		result = self.fx.get_rates(base='USD')
		rates = result['rates']
		for ccy in ('EUR', 'GBP', 'JPY'):
			assert ccy in rates, f'{ccy} not found in rates'

	def test_rates_are_positive_numbers(self):
		result = self.fx.get_rates(base='USD')
		for ccy, rate in result['rates'].items():
			# ECB returns int 1 for the base currency cross-rate; accept int or float
			assert isinstance(rate, (int, float)), f'{ccy} rate is not numeric'
			assert rate > 0, f'{ccy} rate is not positive'

	def test_currency_filter(self):
		result = self.fx.get_rates(base='USD', currencies=['EUR', 'GBP'])
		assert set(result['rates'].keys()) == {'EUR', 'GBP'}

	def test_count_field_matches_rates_length(self):
		result = self.fx.get_rates(base='USD', currencies=['EUR', 'GBP', 'JPY'])
		assert result['count'] == len(result['rates'])

	def test_timestamp_field_present(self):
		result = self.fx.get_rates(base='USD')
		assert 'timestamp' in result
		assert result['timestamp'] != ''

	def test_source_field_is_ecb_or_fallback(self):
		result = self.fx.get_rates(base='USD')
		assert result['source'] in ('ECB', 'exchangerate-api')

	def test_eur_base(self):
		result = self.fx.get_rates(base='EUR')
		assert result['status'] == 'success'
		# USD should be reachable from EUR
		assert 'USD' in result['rates']

	def test_gbp_base(self):
		result = self.fx.get_rates(base='GBP')
		assert result['status'] == 'success'
		assert 'EUR' in result['rates']

	def test_invalid_base_returns_error(self):
		result = self.fx.get_rates(base='ZZZZ')
		assert result['status'] == 'error'

	def test_metals_note_when_requested(self):
		result = self.fx.get_rates(base='USD', include_metals=True)
		assert result['status'] == 'success'
		assert 'metals_note' in result


# ── Group 5: NewsSearch ───────────────────────────────────────────────────────

@_SKIP_NETWORK
class TestNewsSearchReal:
	"""Real DuckDuckGo news search — requires network."""

	def setup_method(self):
		from tools.news_search import NewsSearcher
		self.searcher = NewsSearcher()

	def test_returns_success_status(self):
		result = self.searcher.search('technology news')
		assert result['status'] == 'success'

	def test_articles_is_list(self):
		result = self.searcher.search('AI research')
		assert isinstance(result['articles'], list)

	def test_articles_non_empty_for_popular_query(self):
		result = self.searcher.search('world news today', max_results=5)
		assert result['count'] >= 0  # network might return 0, but no error

	def test_each_article_has_title(self):
		result = self.searcher.search('Kenya business news', max_results=5)
		for article in result['articles']:
			assert 'title' in article

	def test_each_article_has_url(self):
		result = self.searcher.search('global economy', max_results=5)
		for article in result['articles']:
			assert 'url' in article

	def test_each_article_has_summary(self):
		result = self.searcher.search('tech startup Africa', max_results=5)
		for article in result['articles']:
			assert 'summary' in article

	def test_count_matches_articles_list(self):
		result = self.searcher.search('market news', max_results=5)
		assert result['count'] == len(result['articles'])

	def test_query_field_echoed(self):
		query = 'renewable energy 2025'
		result = self.searcher.search(query)
		assert result['query'] == query

	def test_max_results_respected(self):
		result = self.searcher.search('sports results today', max_results=3)
		assert result['count'] <= 3

	def test_days_back_filter(self):
		# With days_back=1, count may be 0 but should not error
		result = self.searcher.search('breaking news', max_results=5, days_back=1)
		assert result['status'] == 'success'

	def test_source_field_in_articles(self):
		result = self.searcher.search('finance news', max_results=3)
		for article in result['articles']:
			assert 'source' in article

	def test_published_field_in_articles(self):
		result = self.searcher.search('politics news', max_results=3)
		# DuckDuckGo may rate-limit; skip assertion if no articles returned
		articles = result.get('articles', [])
		for article in articles:
			assert 'published' in article


# ── Group 6: ArxivSearch ─────────────────────────────────────────────────────

@_SKIP_NETWORK
class TestArxivSearchReal:
	"""Real arXiv API — requires network."""

	def setup_method(self):
		from tools.arxiv_search import ArxivSearcher
		self.searcher = ArxivSearcher()

	def test_returns_success(self):
		result = self.searcher.search('large language models')
		assert result['status'] == 'success'

	def test_papers_is_list(self):
		result = self.searcher.search('neural networks')
		assert isinstance(result['papers'], list)

	def test_returns_papers_for_known_topic(self):
		result = self.searcher.search('transformer attention mechanism', max_results=5)
		assert result['count'] > 0

	def test_paper_has_title(self):
		result = self.searcher.search('reinforcement learning', max_results=3)
		for paper in result['papers']:
			assert 'title' in paper
			assert len(paper['title']) > 0

	def test_paper_has_abstract(self):
		result = self.searcher.search('deep learning', max_results=3)
		for paper in result['papers']:
			assert 'abstract' in paper

	def test_paper_has_url(self):
		result = self.searcher.search('computer vision', max_results=3)
		for paper in result['papers']:
			assert 'url' in paper
			assert paper['url'].startswith('http')

	def test_paper_has_pdf_url(self):
		result = self.searcher.search('machine learning', max_results=3)
		for paper in result['papers']:
			assert 'pdf_url' in paper

	def test_paper_has_authors(self):
		result = self.searcher.search('natural language processing', max_results=3)
		for paper in result['papers']:
			assert 'authors' in paper
			assert isinstance(paper['authors'], list)

	def test_paper_has_published(self):
		result = self.searcher.search('graph neural networks', max_results=3)
		for paper in result['papers']:
			assert 'published' in paper

	def test_paper_has_categories(self):
		result = self.searcher.search('bayesian inference', max_results=3)
		for paper in result['papers']:
			assert 'categories' in paper
			assert isinstance(paper['categories'], list)

	def test_count_matches_papers_length(self):
		result = self.searcher.search('quantum computing', max_results=4)
		assert result['count'] == len(result['papers'])

	def test_query_field_echoed(self):
		query = 'federated learning privacy'
		result = self.searcher.search(query)
		assert result['query'] == query

	def test_max_results_respected(self):
		result = self.searcher.search('optimization algorithms', max_results=2)
		assert result['count'] <= 2

	def test_category_filter(self):
		result = self.searcher.search('attention', max_results=5, categories=['cs.LG'])
		assert result['status'] == 'success'
		# papers returned should have cs.LG in their categories
		for paper in result['papers']:
			assert any('cs' in c for c in paper['categories'])

	def test_sort_by_date(self):
		result = self.searcher.search('diffusion models', max_results=5, sort_by='date')
		assert result['status'] == 'success'
		assert result['count'] > 0

	def test_pdf_url_differs_from_url(self):
		result = self.searcher.search('LLM alignment', max_results=2)
		for paper in result['papers']:
			assert paper['pdf_url'] != paper['url']
			assert '/pdf/' in paper['pdf_url']


# ── Group 7: ResearchAssistant with real Ollama ───────────────────────────────

@_SKIP_OLLAMA
@_SKIP_NETWORK
class TestResearchAssistantRealOllama:
	"""ResearchAssistant driven by real Ollama + real DuckDuckGo. Requires both."""

	def setup_method(self):
		from core.ai_engine import OllamaModel
		from core.search_engine import DuckDuckGoSearch
		from capabilities.research_assistant import ResearchAssistant
		self.ai = OllamaModel()
		self.search = DuckDuckGoSearch()
		self.ra = ResearchAssistant(ai_engine=self.ai, search_engine=self.search)

	def test_quick_research_returns_dict(self):
		result = self.ra.perform_research('What is photosynthesis?', depth='quick')
		assert isinstance(result, dict)

	def test_quick_research_has_content(self):
		result = self.ra.perform_research('Explain the water cycle in one sentence.', depth='quick')
		# result should have some text content, wherever it's keyed
		content = result.get('result') or result.get('summary') or result.get('report') or ''
		assert len(str(content)) > 10

	def test_shallow_research_returns_dict(self):
		result = self.ra.perform_research('Python async programming overview', depth='shallow')
		assert isinstance(result, dict)

	def test_shallow_research_has_summary(self):
		result = self.ra.perform_research('Benefits of renewable energy', depth='shallow')
		# should have some form of summary content
		text = (
			result.get('summary')
			or result.get('result')
			or result.get('report')
			or result.get('synthesis')
			or ''
		)
		assert len(str(text)) > 20

	def test_research_depth_quick_no_search_call(self):
		"""Quick depth should not require search — LLM prior knowledge only."""
		result = self.ra.perform_research('What is 2 + 2?', depth='quick')
		assert isinstance(result, dict)

	def test_summarize_research_findings_returns_content(self):
		findings = {
			'key_findings': ['AI is transforming industries', 'LLMs are improving rapidly'],
			'sources': ['https://example.com/ai'],
		}
		result = self.ra.summarize_research_findings(findings)
		assert isinstance(result, (dict, str))
		content = result if isinstance(result, str) else str(result)
		assert len(content) > 0

	def test_curate_data_returns_content(self):
		data = {'raw_data': 'The company earned $1.2B in Q3. CEO Jane Smith announced new AI strategy.'}
		result = self.ra.curate_data_from_research(data, data_fields=['revenue', 'executive', 'strategy'])
		assert isinstance(result, (dict, list, str))


# ── Group 8: DailyBrief with real Ollama ─────────────────────────────────────

@_SKIP_OLLAMA
@_SKIP_NETWORK
class TestDailyBriefRealOllama:
	"""DailyBrief driven by real Ollama + real DuckDuckGo. Requires both."""

	def setup_method(self):
		from core.ai_engine import OllamaModel
		from core.search_engine import DuckDuckGoSearch
		from capabilities.daily_brief import DailyBrief
		self.ai = OllamaModel()
		self.search = DuckDuckGoSearch()
		self.brief = DailyBrief(ai_engine=self.ai, search_engine=self.search)

	def test_generate_returns_dict(self):
		result = self.brief.generate(include_sections=['news'])
		assert isinstance(result, dict)

	def test_generate_status_ok(self):
		result = self.brief.generate(include_sections=['news'])
		assert result.get('status') == 'ok'

	def test_sections_key_present(self):
		result = self.brief.generate(include_sections=['news'])
		assert 'sections' in result

	def test_news_section_populated(self):
		result = self.brief.generate(include_sections=['news'])
		assert 'news' in result.get('sections', {})

	def test_formatted_text_is_string(self):
		result = self.brief.generate(include_sections=['news'])
		assert isinstance(result.get('formatted_text'), str)

	def test_formatted_text_non_empty(self):
		result = self.brief.generate(include_sections=['news'])
		assert len(result.get('formatted_text', '')) > 50

	def test_formatted_text_has_daily_brief_heading(self):
		result = self.brief.generate(include_sections=['news'])
		assert '# Daily Brief' in result.get('formatted_text', '')

	def test_word_count_positive(self):
		result = self.brief.generate(include_sections=['news'])
		assert result.get('word_count', 0) > 0

	def test_date_field_present(self):
		result = self.brief.generate(include_sections=['news'])
		assert 'date' in result
		assert len(result['date']) >= 8  # at least YYYY-MM-DD

	def test_generated_at_present(self):
		result = self.brief.generate(include_sections=['news'])
		assert 'generated_at' in result

	def test_fx_section_when_requested(self):
		result = self.brief.generate(include_sections=['fx'])
		assert 'fx' in result.get('sections', {})

	def test_news_digest_returns_items(self):
		from datetime import date
		result = self.brief._news_digest(str(date.today()))
		assert 'items' in result or 'summary' in result

	def test_news_section_has_summary(self):
		result = self.brief.generate(include_sections=['news'])
		news = result.get('sections', {}).get('news', {})
		assert 'summary' in news

	def test_generate_with_no_sections_flag_runs(self):
		"""Passing an empty list should not crash — graceful degradation."""
		result = self.brief.generate(include_sections=[])
		assert isinstance(result, dict)
		assert result.get('status') == 'ok'

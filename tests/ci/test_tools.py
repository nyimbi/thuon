"""Tests for thuon_platform/tools/ — network-free tools only."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

import math
from pathlib import Path


# ── Calculator ────────────────────────────────────────────────────────────────

class TestCalculator:
	def _calc(self):
		from tools.calculator import Calculator
		return Calculator()

	def test_simple_arithmetic(self):
		c = self._calc()
		r = c.calculate('2 + 2')
		assert r['status'] == 'success'
		assert r['result'] == 4

	def test_multiplication(self):
		r = self._calc().calculate('7 * 6')
		assert r['result'] == 42

	def test_exponentiation(self):
		r = self._calc().calculate('2 ** 10')
		assert r['result'] == 1024

	def test_math_functions(self):
		r = self._calc().calculate('sqrt(16)')
		assert r['status'] == 'success'
		assert abs(r['result'] - 4.0) < 1e-9

	def test_variables(self):
		r = self._calc().calculate('rate * principal', variables={'rate': 0.05, 'principal': 1000})
		assert r['result'] == 50.0

	def test_npv(self):
		# NPV(0%, [-100, 110]) = 10
		r = self._calc().calculate('npv(0.0, [-100, 110])')
		assert r['status'] == 'success'
		assert abs(r['result'] - 10.0) < 1e-6

	def test_pmt(self):
		# monthly payment on 0% rate loan; PMT returns negative (payment out)
		r = self._calc().calculate('pmt(0, 12, 1200)')
		assert r['status'] == 'success'
		assert abs(r['result'] - (-100.0)) < 1e-6

	def test_compound(self):
		# compound(1000, 0.1, 1, 1) = 1100
		r = self._calc().calculate('compound(1000, 0.1, 1, 1)')
		assert r['status'] == 'success'
		assert abs(r['result'] - 1100.0) < 1e-6

	def test_result_formatted(self):
		r = self._calc().calculate('1 / 3')
		assert 'result_formatted' in r

	def test_disallowed_name_raises(self):
		r = self._calc().calculate('__import__("os")')
		assert r['status'] == 'error'

	def test_attribute_access_blocked(self):
		r = self._calc().calculate('math.sqrt(4)')
		assert r['status'] == 'error'

	def test_invalid_expression(self):
		r = self._calc().calculate('definitely not math')
		assert r['status'] == 'error'

	def test_irr_returns_float(self):
		# IRR of [-100, 60, 60] ≈ 13.1%
		r = self._calc().calculate('irr([-100, 60, 60])')
		assert r['status'] == 'success'
		assert 0.1 < r['result'] < 0.2


# ── PythonExecutor ────────────────────────────────────────────────────────────

class TestPythonExecutor:
	def _exec(self):
		from tools.python_executor import PythonExecutor
		return PythonExecutor()

	def test_hello_world(self):
		r = self._exec().execute('print("hello")')
		assert r['status'] == 'success'
		assert 'hello' in r['stdout']
		assert r['returncode'] == 0

	def test_stderr_captured(self):
		r = self._exec().execute('import sys; sys.stderr.write("err")')
		assert 'err' in r['stderr']

	def test_nonzero_exit(self):
		r = self._exec().execute('raise ValueError("oops")')
		assert r['returncode'] != 0
		assert 'oops' in r['stderr']

	def test_timeout_enforced(self):
		r = self._exec().execute('import time; time.sleep(10)', timeout=1)
		assert r['status'] == 'error'
		assert 'timed out' in r['error']

	def test_execution_time_measured(self):
		r = self._exec().execute('x = 1 + 1')
		assert isinstance(r['execution_time_ms'], int)
		assert r['execution_time_ms'] >= 0

	def test_arithmetic_result_via_print(self):
		r = self._exec().execute('print(2 ** 8)')
		assert '256' in r['stdout']

	def test_multiline_code(self):
		code = 'x = [i**2 for i in range(5)]\nprint(sum(x))'
		r = self._exec().execute(code)
		assert '30' in r['stdout']  # 0+1+4+9+16

	def test_no_tmp_file_left_behind(self):
		import glob
		before = set(glob.glob(tempfile.gettempdir() + '/*.py'))
		self._exec().execute('pass')
		after = set(glob.glob(tempfile.gettempdir() + '/*.py'))
		# Any new .py files from our run should be cleaned up
		new_files = after - before
		assert new_files == set()


# ── FileWriter ────────────────────────────────────────────────────────────────

class TestFileWriter:
	def _fw(self):
		from tools.file_writer import FileWriter
		return FileWriter()

	def test_write_and_read(self, tmp_path):
		fw = self._fw()
		p = str(tmp_path / 'test.txt')
		r = fw.write(p, 'hello world')
		assert r['status'] == 'success'
		assert r['size_bytes'] == 11

		r2 = fw.read_file(p)
		assert r2['status'] == 'success'
		assert r2['content'] == 'hello world'

	def test_creates_parent_dirs(self, tmp_path):
		fw = self._fw()
		p = str(tmp_path / 'a' / 'b' / 'c.txt')
		r = fw.write(p, 'nested')
		assert r['status'] == 'success'
		assert Path(p).exists()

	def test_append_mode(self, tmp_path):
		fw = self._fw()
		p = str(tmp_path / 'append.txt')
		fw.write(p, 'line1\n')
		fw.write(p, 'line2\n', mode='a')
		r = fw.read_file(p)
		assert 'line1' in r['content']
		assert 'line2' in r['content']

	def test_read_truncation(self, tmp_path):
		fw = self._fw()
		p = str(tmp_path / 'big.txt')
		fw.write(p, 'x' * 200)
		r = fw.read_file(p, max_chars=100)
		assert len(r['content']) == 100
		assert r['truncated'] is True

	def test_list_files(self, tmp_path):
		fw = self._fw()
		(tmp_path / 'a.txt').write_text('A')
		(tmp_path / 'b.txt').write_text('B')
		r = fw.list_files(str(tmp_path), pattern='*.txt')
		assert r['status'] == 'success'
		assert r['count'] == 2
		names = {f['name'] for f in r['files']}
		assert names == {'a.txt', 'b.txt'}

	def test_list_recursive(self, tmp_path):
		fw = self._fw()
		sub = tmp_path / 'sub'
		sub.mkdir()
		(tmp_path / 'root.txt').write_text('r')
		(sub / 'deep.txt').write_text('d')
		r = fw.list_files(str(tmp_path), pattern='*.txt', recursive=True)
		assert r['count'] == 2

	def test_delete_file(self, tmp_path):
		fw = self._fw()
		p = tmp_path / 'del.txt'
		p.write_text('bye')
		r = fw.delete_file(str(p))
		assert r['status'] == 'success'
		assert not p.exists()

	def test_read_missing_file(self):
		fw = self._fw()
		r = fw.read_file('/nonexistent/path/file.txt')
		assert r['status'] == 'error'

	def test_delete_missing_file(self):
		fw = self._fw()
		r = fw.delete_file('/nonexistent/path/file.txt')
		assert r['status'] == 'error'


# ── SQLExecutor (no-db path) ──────────────────────────────────────────────────

class TestSQLExecutorNoDB:
	def _sql(self):
		from tools.sql_executor import SQLExecutor
		return SQLExecutor()

	def test_readonly_blocks_insert(self):
		sql = self._sql()
		r = sql.query('INSERT INTO foo VALUES (1)', readonly=True)
		assert r['status'] == 'error'
		assert 'readonly' in r['error'].lower() or 'Only SELECT' in r['error']

	def test_no_db_configured_returns_error(self):
		sql = self._sql()
		# Even a valid SELECT should fail when no DB URL is configured
		r = sql.query('SELECT 1', readonly=True)
		# Either "Database not configured" or a connection error — either way error
		assert r['status'] == 'error'


# ── ExcelReader ───────────────────────────────────────────────────────────────

class TestExcelReader:
	def _reader(self):
		from tools.excel_reader import ExcelReader
		return ExcelReader()

	def test_missing_file_returns_error(self):
		r = self._reader().read('/tmp/nonexistent_12345.xlsx')
		assert r['status'] == 'error'

	def test_csv_read(self, tmp_path):
		p = tmp_path / 'data.csv'
		p.write_text('name,age\nAlice,30\nBob,25\n')
		r = self._reader().read(str(p))
		assert r['status'] == 'success'
		assert len(r['sheets']) == 1
		sheet = r['sheets'][0]
		assert sheet['headers'] == ['name', 'age']
		assert sheet['rows'][0] == {'name': 'Alice', 'age': '30'}
		assert sheet['row_count'] == 2


# ── PDFExtractor (missing file) ───────────────────────────────────────────────

class TestPDFExtractorEdge:
	def _extractor(self):
		from tools.pdf_extractor import PDFExtractor
		return PDFExtractor()

	def test_missing_file_returns_error(self):
		r = self._extractor().extract('/tmp/no_such_file_99999.pdf')
		assert r['status'] == 'error'


# ── CalendarTool ──────────────────────────────────────────────────────────────

class TestCalendarTool:
	def _cal(self):
		from tools.calendar_tool import CalendarTool
		return CalendarTool()

	def test_create_event(self, tmp_path):
		cal = self._cal()
		p = str(tmp_path / 'test.ics')
		r = cal.create_event(
			calendar_path=p,
			title='Team Meeting',
			start='2026-07-01T10:00:00',
			end='2026-07-01T11:00:00',
		)
		assert r['status'] == 'success'
		assert Path(p).exists()
		assert r['title'] == 'Team Meeting'

	def test_get_events_missing_file_returns_error(self):
		cal = self._cal()
		r = cal.get_events(calendar_path='/tmp/no_such_calendar_99999.ics')
		assert r['status'] == 'error'

	def test_get_events_after_create(self, tmp_path):
		cal = self._cal()
		p = str(tmp_path / 'cal.ics')
		cal.create_event(
			calendar_path=p,
			title='Stand-up',
			start='2026-07-01T09:00:00',
			end='2026-07-01T09:15:00',
		)
		r = cal.get_events(days_ahead=30, calendar_path=p)
		assert r['status'] == 'success'
		assert any('Stand-up' in e.get('title', '') for e in r['events'])


# ── ChartGenerator ────────────────────────────────────────────────────────────

class TestChartGenerator:
	def _chart(self):
		from tools.chart_generator import ChartGenerator
		return ChartGenerator()

	def test_bar_chart(self):
		r = self._chart().generate(
			chart_type='bar',
			data={'labels': ['A', 'B', 'C'], 'values': [10, 20, 15]},
			title='Test Bar',
		)
		# matplotlib may or may not be installed; either way a dict is returned
		assert isinstance(r, dict)
		if r.get('status') == 'success':
			assert 'image_base64' in r
			# base64 PNG should start with iVBOR
			assert r['image_base64'][:4] == 'iVBO'

	def test_unknown_chart_type(self):
		r = self._chart().generate(
			chart_type='unknown_type_xyz',
			data={'labels': ['A'], 'values': [1]},
		)
		# either error (unsupported type) or success with empty figure — either is a dict
		assert isinstance(r, dict)
		assert 'status' in r


# ── ArxivSearch (offline) ─────────────────────────────────────────────────────

class TestArxivSearchOffline:
	def test_instantiates(self):
		from tools.arxiv_search import ArxivSearcher
		s = ArxivSearcher()
		assert hasattr(s, 'search')

	def test_missing_requests_returns_error(self):
		import tools.arxiv_search as mod
		original = mod.requests
		mod.requests = None
		try:
			r = mod.ArxivSearcher().search('LLM')
			assert r['status'] == 'error'
			assert 'requests' in r['error']
		finally:
			mod.requests = original

"""
Tests for OllamaVisionModel and vision tools.
All external calls (ChatOllama, Playwright, requests, file I/O) are mocked.
"""
import sys, os, base64, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import patch, MagicMock, mock_open


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_llm_response(text: str):
	m = MagicMock()
	m.content = text
	return m


def _vision_model(model_name='minicpm-v:4.5'):
	"""Build OllamaVisionModel with ChatOllama mocked out."""
	with patch('langchain_ollama.ChatOllama') as MockChat:
		MockChat.return_value = MagicMock()
		from core.ai_engine import OllamaVisionModel
		vm = OllamaVisionModel(model_name=model_name)
	return vm


# ── OllamaVisionModel unit tests ─────────────────────────────────────────────

class TestOllamaVisionModelInit:
	def test_default_model_name(self):
		with patch('langchain_ollama.ChatOllama'):
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()
		assert vm.model_name == 'minicpm-v:4.5'

	def test_custom_model(self):
		with patch('langchain_ollama.ChatOllama'):
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel(model_name='gemma4')
		assert vm.model_name == 'gemma4'

	def test_uses_chat_ollama(self):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			from core.ai_engine import OllamaVisionModel
			OllamaVisionModel()
		MockChat.assert_called_once()


class TestAnalyzeBytes:
	def test_returns_content_string(self):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			mock_llm = MagicMock()
			mock_llm.invoke.return_value = _make_llm_response('A red circle on white background.')
			MockChat.return_value = mock_llm
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()

		result = vm.analyze_bytes(b'\x89PNG\r\n', 'What is this?', 'image/png')
		assert result == 'A red circle on white background.'

	def test_passes_base64_in_message(self):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			mock_llm = MagicMock()
			mock_llm.invoke.return_value = _make_llm_response('desc')
			MockChat.return_value = mock_llm
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()

		image_bytes = b'fake image bytes'
		vm.analyze_bytes(image_bytes, 'describe', 'image/jpeg')
		call_args = mock_llm.invoke.call_args[0][0]
		msg_content = call_args[0].content
		b64_expected = base64.standard_b64encode(image_bytes).decode()
		# Check that b64 appears somewhere in the message content
		found = any(b64_expected in str(c) for c in msg_content)
		assert found

	def test_handles_non_content_response(self):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			mock_llm = MagicMock()
			mock_llm.invoke.return_value = 'plain string response'
			MockChat.return_value = mock_llm
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()

		result = vm.analyze_bytes(b'x', 'prompt')
		assert isinstance(result, str)


class TestAnalyzeImage:
	def test_reads_file_and_delegates(self):
		# Use a real temp file — avoids mimetypes misbehaving when builtins.open is patched globally
		import tempfile, os
		fake_bytes = b'\x89PNG fake'
		with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
			f.write(fake_bytes)
			tmppath = f.name
		try:
			with patch('langchain_ollama.ChatOllama') as MockChat:
				mock_llm = MagicMock()
				mock_llm.invoke.return_value = _make_llm_response('chart analysis')
				MockChat.return_value = mock_llm
				from core.ai_engine import OllamaVisionModel
				vm = OllamaVisionModel()
			result = vm.analyze_image(tmppath, 'What is this?')
			assert result == 'chart analysis'
		finally:
			os.unlink(tmppath)

	def test_guesses_mime_type(self):
		import tempfile, os
		with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
			f.write(b'JFIF fake')
			tmppath = f.name
		try:
			with patch('langchain_ollama.ChatOllama') as MockChat:
				mock_llm = MagicMock()
				mock_llm.invoke.return_value = _make_llm_response('ok')
				MockChat.return_value = mock_llm
				from core.ai_engine import OllamaVisionModel
				vm = OllamaVisionModel()
			vm.analyze_image(tmppath, 'describe')
			call_args = mock_llm.invoke.call_args[0][0]
			content = call_args[0].content
			assert any('image/jpeg' in str(c) for c in content)
		finally:
			os.unlink(tmppath)


class TestHighLevelMethods:
	def _vm_with_response(self, text):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			mock_llm = MagicMock()
			mock_llm.invoke.return_value = _make_llm_response(text)
			MockChat.return_value = mock_llm
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()
		return vm

	def test_describe_calls_analyze_image(self):
		vm = self._vm_with_response('A document with text.')
		with patch.object(vm, 'analyze_image', return_value='A document with text.') as mock_ai:
			result = vm.describe('/tmp/doc.png')
		mock_ai.assert_called_once()
		assert 'document' in result.lower()

	def test_extract_text_returns_string(self):
		vm = self._vm_with_response('Invoice #1234\nDate: 2024-01-15')
		with patch('builtins.open', mock_open(read_data=b'img')):
			result = vm.extract_text('/tmp/invoice.png')
		assert isinstance(result, str)

	def test_analyze_chart_parses_json(self):
		chart_json = json.dumps({
			'chart_type': 'bar', 'title': 'Revenue Q4',
			'data_series': [{'name': 'Revenue', 'values': [100, 120, 115]}],
			'key_insights': ['Growth of 20% in month 2'],
			'trend': 'up',
		})
		vm = self._vm_with_response(chart_json)
		with patch('builtins.open', mock_open(read_data=b'img')):
			result = vm.analyze_chart('/tmp/chart.png')
		assert result['chart_type'] == 'bar'
		assert result['trend'] == 'up'

	def test_analyze_chart_fallback_on_bad_json(self):
		vm = self._vm_with_response('The chart shows revenue going up significantly.')
		with patch('builtins.open', mock_open(read_data=b'img')):
			result = vm.analyze_chart('/tmp/chart.png')
		assert 'raw_description' in result

	def test_analyze_document_page_parses_json(self):
		doc_json = json.dumps({
			'title': 'Service Agreement',
			'document_type': 'contract',
			'sections': [{'heading': 'Terms', 'content': 'Party agrees...'}],
			'key_clauses': ['Liability limited to $100'],
		})
		vm = self._vm_with_response(doc_json)
		with patch('builtins.open', mock_open(read_data=b'img')):
			result = vm.analyze_document_page('/tmp/contract.png')
		assert result['document_type'] == 'contract'
		assert len(result['key_clauses']) == 1

	def test_analyze_screenshot_with_question(self):
		screen_json = json.dumps({
			'page_title': 'Company Dashboard',
			'main_content': 'Revenue: $1.2M',
			'answer': 'Revenue is $1.2M',
		})
		vm = self._vm_with_response(screen_json)
		with patch('builtins.open', mock_open(read_data=b'img')):
			result = vm.analyze_screenshot('/tmp/dash.png', 'What is the revenue?')
		assert result['answer'] == 'Revenue is $1.2M'

	def test_analyze_url_downloads_then_analyzes(self):
		mock_resp = MagicMock()
		mock_resp.content = b'fake image'
		mock_resp.headers = {'content-type': 'image/png'}
		mock_resp.raise_for_status.return_value = None

		vm = self._vm_with_response('A product image.')
		with patch('requests.get', return_value=mock_resp):
			result = vm.analyze_url('https://example.com/img.png', 'what product?')
		assert result == 'A product image.'


class TestCompareImages:
	def test_compare_calls_describe_twice(self):
		with patch('langchain_ollama.ChatOllama') as MockChat:
			mock_llm = MagicMock()
			mock_llm.invoke.return_value = _make_llm_response('{"similarities":[],"differences":["color"],"recommendation":"A"}')
			MockChat.return_value = mock_llm
			from core.ai_engine import OllamaVisionModel
			vm = OllamaVisionModel()

		with patch.object(vm, 'describe', side_effect=['desc A', 'desc B']) as mock_d:
			result = vm.compare_images('/tmp/a.png', '/tmp/b.png')
		assert mock_d.call_count == 2


# ── screenshot_url ────────────────────────────────────────────────────────────

class TestScreenshotUrl:
	def test_calls_playwright_and_returns_path(self):
		import sys
		mock_browser = MagicMock()
		mock_page = MagicMock()
		mock_browser.new_page.return_value = mock_page

		# sync_playwright() returns a context manager; __enter__ returns the playwright obj
		mock_p = MagicMock()
		mock_p.chromium.launch.return_value = mock_browser
		mock_sync_pw = MagicMock()
		mock_sync_pw.return_value.__enter__ = MagicMock(return_value=mock_p)
		mock_sync_pw.return_value.__exit__ = MagicMock(return_value=False)

		mock_sync_api = MagicMock()
		mock_sync_api.sync_playwright = mock_sync_pw

		with patch.dict(sys.modules, {
			'playwright':           MagicMock(),
			'playwright.sync_api':  mock_sync_api,
		}):
			from core.ai_engine import screenshot_url
			path = screenshot_url('https://example.com', '/tmp/test_shot.png')

		assert path == '/tmp/test_shot.png'
		mock_page.goto.assert_called_once()
		mock_page.screenshot.assert_called_once()


# ── Vision tools in core/tools.py ────────────────────────────────────────────

class TestVisionTools:
	def test_analyze_image_file_tool_exists(self):
		from core.tools import analyze_image_file, extract_text_from_image, screenshot_and_analyze
		# StructuredTool exposes .name and .func — use those rather than callable()
		assert analyze_image_file.name == 'analyze_image_file'
		assert extract_text_from_image.name == 'extract_text_from_image'
		assert screenshot_and_analyze.name == 'screenshot_and_analyze'

	def test_vision_tools_in_vision_tools_list(self):
		from core.tools import VISION_TOOLS, analyze_image_file
		assert analyze_image_file in VISION_TOOLS

	def test_analyze_image_file_returns_string(self):
		mock_vm = MagicMock()
		mock_vm.describe.return_value = 'A bar chart showing Q4 data.'
		with patch('core.ai_engine.OllamaVisionModel', return_value=mock_vm):
			from core.tools import analyze_image_file
			result = analyze_image_file.func('/tmp/chart.png', '')
		assert result == 'A bar chart showing Q4 data.'

	def test_analyze_image_file_error_returns_string(self):
		with patch('core.ai_engine.OllamaVisionModel', side_effect=Exception('model not loaded')):
			from core import tools
			result = tools.analyze_image_file.func('/tmp/missing.png', 'describe')
		assert 'Vision analysis failed' in result

	def test_extract_text_from_image_error_returns_string(self):
		with patch('core.ai_engine.OllamaVisionModel', side_effect=Exception('no model')):
			from core import tools
			result = tools.extract_text_from_image.func('/tmp/doc.png')
		assert 'OCR failed' in result

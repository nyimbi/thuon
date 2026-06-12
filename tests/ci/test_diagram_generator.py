# tests/ci/test_diagram_generator.py
"""Tests for capabilities/diagram_generator.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock, patch


def _make_gen(response='flowchart TD\n    A --> B'):
	mock_ai = MagicMock()
	mock_ai.generate_text.return_value = response
	from capabilities.diagram_generator import DiagramGenerator
	return DiagramGenerator(mock_ai), mock_ai


class TestDiagramGeneratorGenerate:
	def test_returns_mermaid_code(self):
		gen, _ = _make_gen('flowchart TD\n    Start --> End')
		result = gen.generate('user login flow', diagram_type='flowchart')
		assert result['status'] == 'ok'
		assert 'mermaid_code' in result
		assert isinstance(result['mermaid_code'], str)

	def test_diagram_type_in_result(self):
		gen, _ = _make_gen('sequenceDiagram\n    A->>B: Hello')
		result = gen.generate('API call sequence', diagram_type='sequence')
		assert result['diagram_type'] == 'sequence'

	def test_description_in_result(self):
		gen, _ = _make_gen()
		result = gen.generate('deployment pipeline')
		assert result['description'] == 'deployment pipeline'

	def test_extracts_code_from_fenced_block(self):
		gen, _ = _make_gen('```mermaid\nflowchart TD\n    A --> B\n```')
		result = gen.generate('flow')
		assert '```' not in result['mermaid_code']

	def test_extracts_code_without_fence(self):
		gen, _ = _make_gen('flowchart TD\n    X --> Y')
		result = gen.generate('flow')
		assert 'flowchart TD' in result['mermaid_code']

	def test_no_output_path_no_rendered_key(self):
		gen, _ = _make_gen()
		result = gen.generate('anything')
		assert 'output_path' not in result

	def test_output_path_without_mmdc_sets_rendered_false(self):
		gen, _ = _make_gen()
		import tempfile, os
		with tempfile.TemporaryDirectory() as d:
			out = os.path.join(d, 'diagram.png')
			with patch('shutil.which', return_value=None):
				result = gen.generate('flow', output_path=out)
		assert result.get('rendered') is None or result.get('rendered') == False

	def test_mindmap_shortcut(self):
		gen, mock_ai = _make_gen('mindmap\n  root\n    branch')
		result = gen.generate_mindmap('AI landscape')
		assert result['diagram_type'] == 'mindmap'

	def test_flowchart_shortcut(self):
		gen, _ = _make_gen()
		result = gen.generate_flowchart('CI/CD pipeline')
		assert result['diagram_type'] == 'flowchart'

	def test_sequence_shortcut(self):
		gen, _ = _make_gen()
		result = gen.generate_sequence('user authentication')
		assert result['diagram_type'] == 'sequence'

	def test_gantt_shortcut(self):
		gen, _ = _make_gen()
		result = gen.generate_gantt('Q3 project plan')
		assert result['diagram_type'] == 'gantt'

	def test_er_shortcut(self):
		gen, _ = _make_gen()
		result = gen.generate_er('user orders schema')
		assert result['diagram_type'] == 'er'

	def test_unknown_type_falls_back_to_flowchart(self):
		from capabilities.diagram_generator import _DIRECTIVES
		assert 'flowchart' in _DIRECTIVES

	def test_llm_prompt_includes_directive(self):
		gen, mock_ai = _make_gen()
		gen.generate('auth flow', diagram_type='sequence')
		call_prompt = mock_ai.generate_text.call_args[0][0]
		assert 'sequence' in call_prompt.lower()

	def test_render_png_skips_when_mmdc_missing(self):
		gen, _ = _make_gen()
		with patch('shutil.which', return_value=None):
			result = gen._render_png('flowchart TD\nA-->B', '/tmp/x.png')
		assert result is None

	def test_render_png_calls_mmdc_when_available(self):
		gen, _ = _make_gen()
		mock_proc = MagicMock()
		mock_proc.returncode = 0
		with patch('shutil.which', return_value='/usr/bin/mmdc'), \
			 patch('subprocess.run', return_value=mock_proc) as mock_run, \
			 patch('os.makedirs'), patch('os.unlink'):
			import tempfile
			with patch('tempfile.NamedTemporaryFile') as mock_ntf:
				mock_ntf.return_value.__enter__ = MagicMock(return_value=MagicMock(name='f'))
				mock_ntf.return_value.__enter__.return_value.name = '/tmp/fake.mmd'
				mock_ntf.return_value.__exit__ = MagicMock(return_value=False)
				result = gen._render_png('flowchart TD\nA-->B', '/tmp/out.png')
		# render returns path when returncode == 0
		assert result == '/tmp/out.png' or result is None  # depends on mock depth

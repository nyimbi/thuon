# tests/ci/test_thuon_ergonomics.py
"""
Tests for all 10 Thuon ergonomic improvements:
  1. Natural language dispatch (do)
  2. Autowiring DI container
  3. Fluent ThuonResult
  4. Capability registration decorator
  5. Streaming (generate_stream + CapabilityProxy.stream)
  6. Typed input schemas
  7. Pipeline-as-YAML
  8. Hot-reload config + model() override
  9. Explain/trace mode
 10. Self-describing capabilities()
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

from unittest.mock import MagicMock, patch, PropertyMock


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_ai(response='{"result": "ok"}'):
	m = MagicMock()
	m.generate_text.return_value = response
	m.generate_stream.return_value = iter(['tok1', ' tok2', ' tok3'])
	return m


def _mock_search(results=None):
	m = MagicMock()
	m.search.return_value = results or [
		{'title': 'Article', 'href': 'https://example.com', 'body': 'content'}
	]
	return m


# ── #3 ThuonResult fluent wrapper ─────────────────────────────────────────────

class TestThuonResult:
	def test_dict_access(self):
		from core.result import ThuonResult
		r = ThuonResult({'status': 'ok', 'answer': 'hello'}, capability_name='test')
		assert r['status'] == 'ok'
		assert r.get('answer') == 'hello'
		assert 'status' in r

	def test_get_with_default(self):
		from core.result import ThuonResult
		r = ThuonResult({}, capability_name='x')
		assert r.get('missing', 'fallback') == 'fallback'

	def test_to_dict(self):
		from core.result import ThuonResult
		r = ThuonResult({'a': 1, 'b': 2}, 'cap')
		assert r.to_dict() == {'a': 1, 'b': 2}

	def test_keys_values_items(self):
		from core.result import ThuonResult
		r = ThuonResult({'x': 10, 'y': 20}, 'cap')
		assert set(r.keys()) == {'x', 'y'}
		assert 10 in r.values()
		assert ('x', 10) in r.items()

	def test_repr_includes_capability_name(self):
		from core.result import ThuonResult
		r = ThuonResult({'k': 'v'}, 'my_capability')
		assert 'my_capability' in repr(r)

	def test_setitem(self):
		from core.result import ThuonResult
		r = ThuonResult({'a': 1}, 'cap')
		r['b'] = 2
		assert r['b'] == 2

	def test_to_pdf_adds_pdf_path(self):
		from core.result import ThuonResult
		from core.document_engine import generate_document
		r = ThuonResult({'content': '# Report\n## Section\nContent here with enough words ' * 5}, 'cap')
		with patch('core.document_engine._pdf', return_value='/tmp/out.pdf') as mock_pdf:
			r.to_pdf('/tmp/out.pdf')
		assert 'pdf_path' in r

	def test_to_docx_adds_docx_path(self):
		from core.result import ThuonResult
		r = ThuonResult({'content': '# Report\n' + 'text ' * 50}, 'cap')
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, 'out.docx')
			r.to_docx(path)
			assert 'docx_path' in r
			assert os.path.exists(r['docx_path'])

	def test_to_slides_adds_pptx_path(self):
		from core.result import ThuonResult
		r = ThuonResult({'content': '# Slide 1\nContent A\n# Slide 2\nContent B'}, 'cap')
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, 'out.pptx')
			r.to_slides(path)
			assert 'pptx_path' in r
			assert os.path.exists(r['pptx_path'])

	def test_to_xlsx_adds_xlsx_path(self):
		from core.result import ThuonResult
		r = ThuonResult({'rows': [{'A': 1}, {'A': 2}]}, 'cap')
		with tempfile.TemporaryDirectory() as d:
			path = os.path.join(d, 'out.xlsx')
			r.to_xlsx(output_path=path)
			assert 'xlsx_path' in r
			assert os.path.exists(r['xlsx_path'])

	def test_fluent_chaining_returns_self(self):
		from core.result import ThuonResult
		r = ThuonResult({'content': '# Title\nBody text goes here ' * 20}, 'cap')
		with tempfile.TemporaryDirectory() as d:
			result = r.to_docx(os.path.join(d, 'a.docx')).to_pdf(os.path.join(d, 'b.pdf'))
		assert result is r   # same object

	def test_content_extraction_from_content_key(self):
		from core.result import ThuonResult
		r = ThuonResult({'content': 'This is the main content ' * 10, 'other': 'x'}, 'cap')
		text = r._content_for_doc()
		assert 'main content' in text

	def test_content_fallback_to_json(self):
		from core.result import ThuonResult
		r = ThuonResult({'small': 'x'}, 'cap')
		text = r._content_for_doc()
		assert 'small' in text

	def test_trace_empty_by_default(self):
		from core.result import ThuonResult
		r = ThuonResult({'a': 1}, 'cap')
		assert r.trace == {}

	def test_explain_without_trace(self):
		from core.result import ThuonResult
		r = ThuonResult({'a': 1}, 'cap')
		explanation = r.explain()
		assert 'explain=True' in explanation

	def test_explain_with_trace(self):
		from core.result import ThuonResult
		r = ThuonResult({'a': 1}, 'cap', trace={'elapsed_seconds': 1.5, 'llm_calls': 2})
		explanation = r.explain()
		assert 'elapsed' in explanation or 'llm_calls' in explanation


# ── #6 Typed input schemas ────────────────────────────────────────────────────

class TestSchemas:
	def test_research_input_valid(self):
		from core.schemas import ResearchInput
		inp = ResearchInput(query='AI trends', depth='deep', num_sources=5)
		assert inp.query == 'AI trends'
		assert inp.depth == 'deep'

	def test_research_input_defaults(self):
		from core.schemas import ResearchInput
		inp = ResearchInput(query='x')
		assert inp.depth == 'medium'
		assert inp.num_sources == 5

	def test_research_input_invalid_depth(self):
		from core.schemas import ResearchInput
		import pytest
		with pytest.raises(Exception):
			ResearchInput(query='x', depth='ultradeep')

	def test_research_input_num_sources_bounds(self):
		from core.schemas import ResearchInput
		import pytest
		with pytest.raises(Exception):
			ResearchInput(query='x', num_sources=0)   # ge=1
		with pytest.raises(Exception):
			ResearchInput(query='x', num_sources=100) # le=20

	def test_tender_input_valid(self):
		from core.schemas import TenderInput
		inp = TenderInput(sector='ICT', countries=['Kenya', 'Nigeria'], max_results=10)
		assert inp.sector == 'ICT'
		assert inp.max_results == 10

	def test_contract_input_valid(self):
		from core.schemas import ContractInput
		inp = ContractInput(contract_text='Service agreement...', vendor='AWS', category='cloud')
		assert inp.category == 'cloud'

	def test_brief_input_optional_fields(self):
		from core.schemas import BriefInput
		inp = BriefInput()
		assert inp.topics is None

	def test_draft_email_input(self):
		from core.schemas import DraftEmailInput
		inp = DraftEmailInput(vendor='Netflix', current_price=1500.0, email_type='cancel')
		assert inp.email_type == 'cancel'

	def test_capability_schemas_registry_populated(self):
		from core.schemas import CAPABILITY_SCHEMAS
		assert 'research_assistant' in CAPABILITY_SCHEMAS
		assert 'tender_scout' in CAPABILITY_SCHEMAS
		assert 'daily_brief' in CAPABILITY_SCHEMAS

	def test_extra_fields_forbidden(self):
		from core.schemas import ResearchInput
		import pytest
		with pytest.raises(Exception):
			ResearchInput(query='x', unknown_field='y')


# ── #9 TraceContext ───────────────────────────────────────────────────────────

class TestTraceContext:
	def test_context_manager_captures_events(self):
		from core.trace import TraceContext, trace_emit
		with TraceContext() as tc:
			trace_emit('test_event', data='hello')
		events = tc.events
		assert len(events) == 1
		assert events[0]['type'] == 'test_event'

	def test_elapsed_is_positive(self):
		from core.trace import TraceContext
		import time
		with TraceContext() as tc:
			time.sleep(0.01)
		assert tc.elapsed >= 0.01

	def test_no_active_trace_emit_is_noop(self):
		from core.trace import trace_emit
		# Should not raise
		trace_emit('orphaned_event', key='value')

	def test_llm_call_counted(self):
		from core.trace import TraceContext, trace_llm
		with TraceContext() as tc:
			trace_llm('prompt text', 'response text', model='qwen3.5:4b')
			trace_llm('prompt2', 'response2')
		assert tc.to_dict()['llm_calls'] == 2

	def test_tool_call_counted(self):
		from core.trace import TraceContext, trace_tool
		with TraceContext() as tc:
			trace_tool('web_search', args={'query': 'AI'})
		assert tc.to_dict()['tool_calls'] == 1

	def test_phase_tracking(self):
		from core.trace import TraceContext, trace_phase
		with TraceContext() as tc:
			trace_phase('search')
			trace_phase('synthesize')
		assert 'search' in tc.to_dict()['phases']
		assert 'synthesize' in tc.to_dict()['phases']

	def test_data_source_tracking(self):
		from core.trace import TraceContext, trace_source
		with TraceContext() as tc:
			trace_source('NVD', items_found=5)
			trace_source('arXiv', items_found=3)
		d = tc.to_dict()
		assert 'NVD' in d['data_sources']
		assert 'arXiv' in d['data_sources']

	def test_summary_string(self):
		from core.trace import TraceContext, trace_llm
		with TraceContext() as tc:
			trace_llm('prompt', 'response')
		summary = tc.summary()
		assert 'Elapsed' in summary
		assert 'LLM calls' in summary

	def test_capturing_trace_context_manager(self):
		from core.trace import capturing_trace, trace_emit
		with capturing_trace() as tc:
			trace_emit('phase', name='init')
		assert len(tc.events) == 1


# ── #7 PipelineRunner ─────────────────────────────────────────────────────────

class TestPipelineRunner:
	def test_resolve_template_input(self):
		from core.pipeline_runner import _resolve_template
		result = _resolve_template('{input.company}', {'company': 'Safaricom'}, {})
		assert result == 'Safaricom'

	def test_resolve_template_steps(self):
		from core.pipeline_runner import _resolve_template
		result = _resolve_template(
			'{steps.research.market_size}',
			{},
			{'research': {'market_size': '$5B'}},
		)
		assert result == '$5B'

	def test_resolve_template_missing_returns_original(self):
		from core.pipeline_runner import _resolve_template
		result = _resolve_template('{input.missing}', {}, {})
		assert result == '{input.missing}'

	def test_resolve_params_substitutes_all(self):
		from core.pipeline_runner import _resolve_params
		params = {'topic': '{input.topic}', 'depth': 'deep', 'company': '{input.company}'}
		resolved = _resolve_params(params, {'topic': 'AI', 'company': 'Google'}, {})
		assert resolved == {'topic': 'AI', 'depth': 'deep', 'company': 'Google'}

	def test_pipeline_load_from_yaml_file(self):
		from core.pipeline_runner import PipelineRunner
		yaml_content = """
name: test_pipe
steps:
  - name: step1
    capability: research_assistant
    params:
      query: "{input.topic}"
"""
		with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as f:
			f.write(yaml_content)
			path = f.name
		try:
			runner = PipelineRunner(MagicMock())
			spec = runner._load(path)
			assert spec['name'] == 'test_pipe'
			assert len(spec['steps']) == 1
		finally:
			os.unlink(path)

	def test_pipeline_load_inline_dict(self):
		from core.pipeline_runner import PipelineRunner
		spec = {'name': 'inline', 'steps': []}
		runner = PipelineRunner(MagicMock())
		assert runner._load(spec) == spec

	def test_pipeline_load_unknown_name_raises(self):
		from core.pipeline_runner import PipelineRunner
		import pytest
		runner = PipelineRunner(MagicMock())
		with pytest.raises(FileNotFoundError):
			runner._load('nonexistent_pipeline_xyz')

	def test_pipeline_run_executes_steps(self):
		from core.pipeline_runner import PipelineRunner
		from core.result import ThuonResult

		mock_platform = MagicMock()
		step1_result = ThuonResult({'answer': 'research done'}, 'research_assistant')
		step2_result = ThuonResult({'brief': 'brief done'}, 'daily_brief')
		mock_platform.research_assistant.return_value = step1_result
		mock_platform.daily_brief.return_value = step2_result

		spec = {
			'name': 'test',
			'steps': [
				{'name': 'r', 'capability': 'research_assistant', 'params': {'query': 'AI'}},
				{'name': 'b', 'capability': 'daily_brief', 'params': {'topics': ['AI']}},
			],
		}
		runner = PipelineRunner(mock_platform)
		result = runner.run(spec, {})
		mock_platform.research_assistant.assert_called_once()
		mock_platform.daily_brief.assert_called_once()


# ── #5 Streaming ─────────────────────────────────────────────────────────────

class TestStreaming:
	def test_generate_stream_yields_chunks(self):
		with patch('langchain_ollama.OllamaLLM') as MockLLM:
			mock_llm = MagicMock()
			mock_llm.stream.return_value = iter(['Hello', ' world', '!'])
			MockLLM.return_value = mock_llm
			from core.ai_engine import OllamaModel
			model = OllamaModel()

		chunks = list(model.generate_stream('Say hello'))
		assert chunks == ['Hello', ' world', '!']

	def test_generate_stream_calls_llm_stream(self):
		with patch('langchain_ollama.OllamaLLM') as MockLLM:
			mock_llm = MagicMock()
			mock_llm.stream.return_value = iter(['chunk'])
			MockLLM.return_value = mock_llm
			from core.ai_engine import OllamaModel
			model = OllamaModel()

		list(model.generate_stream('prompt'))
		mock_llm.stream.assert_called_once_with('prompt')


# ── #2, #4, #8, #10 Thuon facade ─────────────────────────────────────────────

class TestThuonFacade:
	def _make_thuon(self, ai_response='{"result": "ok"}'):
		"""Build a Thuon instance with mocked AI and search deps."""
		from thuon import Thuon
		t = Thuon()
		mock_ai = _mock_ai(ai_response)
		mock_search = _mock_search()
		t._container['ai_engine']    = mock_ai
		t._container['search_engine'] = mock_search
		return t, mock_ai, mock_search

	# #2 Autowiring
	def test_getattr_returns_capability_proxy(self):
		from thuon import Thuon, CapabilityProxy
		t = Thuon()
		proxy = t.research_assistant
		assert isinstance(proxy, CapabilityProxy)

	def test_getattr_unknown_raises(self):
		from thuon import Thuon
		import pytest
		t = Thuon()
		with pytest.raises(AttributeError):
			_ = t.nonexistent_capability_xyz

	def test_private_attr_raises_attribute_error(self):
		from thuon import Thuon
		import pytest
		t = Thuon()
		with pytest.raises(AttributeError):
			_ = t._nonexistent

	# #4 Registration decorator
	def test_capability_decorator_registers(self):
		from thuon import Thuon
		t = Thuon()

		@t.capability(deps=[], description='test analyzer')
		def sector_analyzer(sector: str) -> dict:
			return {'sector': sector, 'status': 'ok'}

		assert 'sector_analyzer' in t._custom_caps

	def test_capability_decorator_callable(self):
		from thuon import Thuon, CapabilityProxy
		t = Thuon()

		@t.capability(deps=[], description='echo capability')
		def my_echo(message: str) -> dict:
			return {'echo': message}

		# Custom caps registered — check proxy available
		proxy = t.__getattr__('my_echo')
		assert isinstance(proxy, CapabilityProxy)

	# #8 Hot-reload
	def test_reload_config_clears_container(self):
		from thuon import Thuon
		import core.settings_manager as sm
		t = Thuon()
		t._container['ai_engine'] = MagicMock()
		assert 'ai_engine' in t._container
		t.reload_config()
		assert t._container == {}

	def test_model_override_creates_new_instance(self):
		from thuon import Thuon
		t = Thuon()
		t2 = t.model('llama3.3')
		assert t2 is not t
		assert t2._override_model == 'llama3.3'
		assert t._override_model is None   # original unchanged

	def test_model_override_pops_ai_engine_from_container(self):
		from thuon import Thuon
		t = Thuon()
		t._container['ai_engine'] = MagicMock()
		t2 = t.model('llama3.3')
		assert 'ai_engine' not in t2._container

	# #10 Self-describing
	def test_capabilities_returns_list(self):
		from thuon import Thuon
		t = Thuon()
		caps = t.capabilities()
		assert isinstance(caps, list)
		assert len(caps) > 0

	def test_capabilities_have_required_keys(self):
		from thuon import Thuon
		t = Thuon()
		for cap in t.capabilities():
			assert 'name' in cap
			assert 'description' in cap

	def test_capabilities_with_task_sorts_by_relevance(self):
		from thuon import Thuon
		t = Thuon()
		caps = t.capabilities(task='find government procurement tender')
		# tender_scout should be near the top
		names = [c['name'] for c in caps[:3]]
		assert 'tender_scout' in names

	def test_capabilities_with_task_research(self):
		from thuon import Thuon
		t = Thuon()
		caps = t.capabilities(task='research AI trends')
		names = [c['name'] for c in caps[:3]]
		assert 'research_assistant' in names or 'deep_researcher' in names

	def test_capabilities_includes_custom(self):
		from thuon import Thuon
		t = Thuon()

		@t.capability(deps=[], description='custom cap', keywords=['custom'])
		def my_custom(x: str) -> dict:
			return {'x': x}

		caps = t.capabilities()
		names = [c['name'] for c in caps]
		assert 'my_custom' in names

	# #9 Explain mode via CapabilityProxy
	def test_explain_flag_populates_trace(self):
		from thuon import Thuon, CapabilityProxy
		t, mock_ai, mock_search = self._make_thuon('{"answer": "AI is growing"}')

		# Mock the capability to avoid real instantiation
		mock_instance = MagicMock()
		mock_instance.perform_research.return_value = {'answer': 'AI is growing', 'status': 'ok'}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'perform_research', 'deps': ['ai_engine']}
		)):
			proxy = CapabilityProxy('research_assistant', t)
			result = proxy(query='AI trends', explain=True)

		assert result.trace != {}
		assert 'capability' in result.trace

	def test_explain_false_leaves_empty_trace(self):
		from thuon import Thuon, CapabilityProxy
		t, _, _ = self._make_thuon()

		mock_instance = MagicMock()
		mock_instance.perform_research.return_value = {'answer': 'ok', 'status': 'ok'}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'perform_research', 'deps': ['ai_engine']}
		)):
			proxy = CapabilityProxy('research_assistant', t)
			result = proxy(query='test')

		assert result.trace == {}


# ── #5 CapabilityProxy.stream ────────────────────────────────────────────────

class TestCapabilityProxyStream:
	def test_stream_yields_start_and_done(self):
		from thuon import Thuon, CapabilityProxy

		t = Thuon()
		mock_ai = _mock_ai()
		t._container['ai_engine'] = mock_ai

		mock_instance = MagicMock()
		mock_instance.perform_research.return_value = {'answer': 'streamed result', 'status': 'ok'}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'perform_research', 'deps': ['ai_engine']}
		)):
			proxy = CapabilityProxy('research_assistant', t)
			chunks = list(proxy.stream(query='AI trends'))

		types = [c['type'] for c in chunks]
		assert 'start' in types
		assert 'done' in types

	def test_stream_tokens_yielded(self):
		from thuon import Thuon, CapabilityProxy

		t = Thuon()
		mock_ai = _mock_ai()
		mock_ai.generate_stream.return_value = iter(['tok1', ' tok2'])
		t._container['ai_engine'] = mock_ai

		mock_instance = MagicMock()
		mock_instance.perform_research.return_value = {'answer': 'done', 'status': 'ok'}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'perform_research', 'deps': ['ai_engine']}
		)):
			proxy = CapabilityProxy('research_assistant', t)
			chunks = list(proxy.stream(query='AI trends'))

		token_chunks = [c for c in chunks if c['type'] == 'token']
		assert len(token_chunks) == 2

	def test_stream_done_chunk_has_result(self):
		from thuon import Thuon, CapabilityProxy
		from core.result import ThuonResult

		t = Thuon()
		mock_ai = _mock_ai()
		t._container['ai_engine'] = mock_ai

		mock_instance = MagicMock()
		mock_instance.perform_research.return_value = {'answer': 'final answer', 'status': 'ok'}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'perform_research', 'deps': ['ai_engine']}
		)):
			proxy = CapabilityProxy('research_assistant', t)
			chunks = list(proxy.stream(query='AI'))

		done = next(c for c in chunks if c['type'] == 'done')
		assert isinstance(done['result'], ThuonResult)

	# #6 Pydantic schema via proxy
	def test_proxy_schema_property(self):
		from thuon import Thuon, CapabilityProxy
		from core.schemas import ResearchInput

		t = Thuon()
		proxy = CapabilityProxy('research_assistant', t)
		assert proxy.schema is ResearchInput

	def test_proxy_schema_none_for_unknown(self):
		from thuon import Thuon, CapabilityProxy

		t = Thuon()
		proxy = CapabilityProxy('nonexistent_cap', t)
		assert proxy.schema is None

	# Non-default method access
	def test_proxy_non_default_method(self):
		from thuon import Thuon, CapabilityProxy
		from core.result import ThuonResult

		t = Thuon()
		mock_ai = _mock_ai()
		t._container['ai_engine']     = mock_ai
		t._container['search_engine'] = _mock_search()

		mock_instance = MagicMock()
		mock_instance.draft_email.return_value = {
			'subject': 'Discount Request', 'body': 'Dear AWS...', 'status': 'ok',
		}

		with patch.object(t, '_instantiate', return_value=(
			mock_instance,
			{'method': 'analyze_contract', 'deps': ['ai_engine', 'search_engine']}
		)):
			proxy = CapabilityProxy('contract_renegotiator', t)
			result = proxy.draft_email(vendor='AWS', current_price=5000.0)

		assert isinstance(result, ThuonResult)
		assert result['status'] == 'ok'


# ── #1 Natural language dispatch (routing only, no live LLM) ────────────────

class TestRouting:
	def test_keyword_fallback_research(self):
		from thuon import Thuon
		t = Thuon()
		mock_ai = _mock_ai('not valid json at all {broken')
		t._container['ai_engine'] = mock_ai

		cap, params = t._route('research the latest AI developments in East Africa')
		# Should fall back to research_assistant or deep_researcher via keyword match
		assert 'research' in cap

	def test_keyword_fallback_tender(self):
		from thuon import Thuon
		t = Thuon()
		mock_ai = _mock_ai('not json')
		t._container['ai_engine'] = mock_ai

		cap, params = t._route('find government procurement tender for ICT services')
		assert cap == 'tender_scout'

	def test_llm_routing_parses_json(self):
		from thuon import Thuon
		t = Thuon()
		mock_ai = _mock_ai(json.dumps({
			'capability': 'diagram_generator',
			'params': {'description': 'auth flow', 'diagram_type': 'flowchart'},
		}))
		t._container['ai_engine'] = mock_ai

		cap, params = t._route('generate a flowchart of our authentication flow')
		assert cap == 'diagram_generator'
		assert params.get('description') == 'auth flow'

	def test_llm_routing_invalid_capability_falls_back(self):
		from thuon import Thuon
		t = Thuon()
		mock_ai = _mock_ai(json.dumps({
			'capability': 'nonexistent_capability_xyz',
			'params': {},
		}))
		t._container['ai_engine'] = mock_ai

		cap, params = t._route('do something')
		# Should fall back to keyword matching, returning a valid capability
		from thuon import _REGISTRY
		assert cap in _REGISTRY

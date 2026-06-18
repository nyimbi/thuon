# thuon_platform/thuon.py
"""
Thuon — the single import you need.

  from thuon import Thuon
  t = Thuon()

  # Natural language dispatch (#1)
  result = t.do("research the impact of AI on Kenyan fintech and produce a PDF")

  # Autowired capability access (#2)
  result = t.research_assistant(query="AI trends", depth="deep")

  # Fluent results (#3)
  t.research_assistant(query="AI in healthcare").to_pdf().to_slides()

  # Capability decorator (#4)
  @t.capability(deps=['ai_engine', 'search_engine'])
  def my_sector_analyzer(ai_engine, search_engine, sector: str) -> dict:
      ...

  # Streaming (#5)
  for chunk in t.research_assistant.stream("AI in agriculture"):
      print(chunk['text'], end='', flush=True)

  # Typed inputs (#6)
  from core.schemas import ResearchInput
  result = t.research_assistant(ResearchInput(query="...", depth="phd"))

  # Pipeline-as-YAML (#7)
  result = t.run_pipeline("competitive_report", company="Safaricom", industry="telecom")

  # Hot-reload config (#8)
  t.reload_config()
  t.model("llama3.3").do("summarize EU AI Act")

  # Explain/trace (#9)
  result = t.do("analyze contract", explain=True)
  print(result.explain())

  # Self-describing (#10)
  t.capabilities()
  t.capabilities(task="find government procurement opportunities")
"""

from __future__ import annotations
import importlib
import inspect
import json
import os
import re
import time
from typing import Any, Generator, Iterator

from core.result import ThuonResult
from core.settings_manager import get_settings


# ── Capability registry ────────────────────────────────────────────────────

_REGISTRY: dict[str, dict] = {
	'research_assistant': {
		'module': 'capabilities.research_assistant',
		'class': 'ResearchAssistant',
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'method': 'perform_research',
		'description': 'Multi-depth web research on any topic',
		'keywords': ['research', 'investigate', 'find information', 'look up', 'study', 'analyze'],
		'example': 't.research_assistant(query="AI trends in Africa", depth="deep")',
	},
	'deep_researcher': {
		'module': 'capabilities.deep_researcher',
		'class': 'DeepResearcher',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'research',
		'description': 'PhD-level comprehensive research with Semantic Scholar citation chaining',
		'keywords': ['deep research', 'comprehensive', 'academic', 'phd', 'literature review'],
		'example': 't.deep_researcher(topic="CRISPR applications", depth="phd")',
	},
	'competitive_intelligence_operative': {
		'module': 'capabilities.competitive_intelligence_operative',
		'class': 'CompetitiveIntelligenceOperative',
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'method': 'gather_competitive_intelligence',
		'description': 'Competitive analysis and market intelligence',
		'keywords': ['competitive', 'competitor', 'market analysis', 'company analysis', 'compare'],
		'example': 't.competitive_intelligence_operative(company_name="Safaricom", area_of_interest="mobile money")',
	},
	'document_generator': {
		'module': 'capabilities.document_generator',
		'class': 'DocumentGenerator',
		'deps': ['ai_engine'],
		'method': 'generate',
		'description': 'Generate DOCX, PDF, PPTX, or XLSX documents from any topic',
		'keywords': ['document', 'report', 'pdf', 'word', 'powerpoint', 'excel', 'write report'],
		'example': 't.document_generator(topic="Q4 Strategy", format="pdf")',
	},
	'diagram_generator': {
		'module': 'capabilities.diagram_generator',
		'class': 'DiagramGenerator',
		'deps': ['ai_engine'],
		'method': 'generate',
		'description': 'Generate Mermaid diagrams: flowcharts, ERDs, sequence diagrams, mind maps',
		'keywords': ['diagram', 'flowchart', 'chart', 'visualize', 'mind map', 'erd'],
		'example': 't.diagram_generator(description="user auth flow", diagram_type="sequence")',
	},
	'daily_brief': {
		'module': 'capabilities.daily_brief',
		'class': 'DailyBrief',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'generate',
		'description': 'Daily news + knowledge digest with action items',
		'keywords': ['brief', 'summary', 'news', 'daily', 'digest', 'morning report'],
		'example': 't.daily_brief(topics=["AI", "Africa business"])',
	},
	'tender_scout': {
		'module': 'capabilities.tender_scout',
		'class': 'TenderScout',
		'deps': ['search_engine'],
		'method': 'search',
		'description': 'Search African procurement tenders across 15 countries',
		'keywords': ['tender', 'procurement', 'bid', 'government contract', 'RFP', 'RFQ'],
		'example': 't.tender_scout(sector="ICT", countries=["Kenya", "Nigeria"])',
	},
	'contract_renegotiator': {
		'module': 'capabilities.contract_renegotiator',
		'class': 'ContractRenegotiator',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'analyze_contract',
		'description': 'Contract/subscription renegotiation intelligence and email drafting',
		'keywords': ['contract', 'renegotiate', 'subscription', 'cancel', 'discount', 'renewal'],
		'example': 't.contract_renegotiator(contract_text="...", vendor="AWS", category="cloud")',
	},
	'receipt_analyzer': {
		'module': 'capabilities.receipt_analyzer',
		'class': 'ReceiptAnalyzer',
		'deps': [],
		'method': 'analyze',
		'description': 'OCR receipt and invoice images into structured transaction data',
		'keywords': ['receipt', 'invoice', 'OCR', 'scan', 'expense', 'transaction'],
		'example': 't.receipt_analyzer(image_path="/tmp/receipt.jpg")',
	},
	'legal_compliance_officer': {
		'module': 'capabilities.LegalComplianceOfficer',
		'class': 'LegalComplianceOfficer',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'review_contract',
		'description': 'Legal contract review, compliance gap analysis, risk identification',
		'keywords': ['legal', 'contract review', 'compliance', 'risk', 'clause', 'law'],
		'example': 't.legal_compliance_officer(contract_text="...", jurisdiction="Kenya")',
	},
	'cybersecurity_guardian': {
		'module': 'capabilities.CybersecurityGuardian',
		'class': 'CybersecurityGuardian',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'assess_security',
		'description': 'Security vulnerability assessment with NVD CVE lookup',
		'keywords': ['security', 'vulnerability', 'CVE', 'threat', 'pentest', 'cyber'],
		'example': 't.cybersecurity_guardian(system_description="web API", tech_stack="FastAPI")',
	},
	'financial_forecasting_analyst': {
		'module': 'capabilities.financial_forecasting_analyst',
		'class': 'FinancialForecastingAnalyst',
		'deps': ['ai_engine', 'db_handler'],
		'method': 'analyze_financial_data',
		'description': 'Financial data analysis, forecasting, and trend identification',
		'keywords': ['financial', 'forecast', 'revenue', 'budget', 'P&L', 'cash flow'],
		'example': 't.financial_forecasting_analyst(company="Acme", data_table="financials")',
	},
	'market_sales_research': {
		'module': 'capabilities.market_sales_research',
		'class': 'MarketSalesResearch',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'research_market',
		'description': 'Market size, growth rates, segments, and sales opportunity analysis',
		'keywords': ['market research', 'market size', 'TAM', 'sales', 'growth', 'segment'],
		'example': 't.market_sales_research(industry="edtech", geography="East Africa")',
	},
	'intellectual_property_strategist': {
		'module': 'capabilities.intellectual_property_strategist',
		'class': 'IntellectualPropertyStrategist',
		'deps': ['ai_engine', 'search_engine'],
		'method': 'strategize_ip',
		'description': 'Patent landscape analysis and IP strategy with USPTO data',
		'keywords': ['patent', 'IP', 'intellectual property', 'trademark', 'innovation'],
		'example': 't.intellectual_property_strategist(technology_area="AI inference chips")',
	},
	'code_writer': {
		'module': 'capabilities.code_writer',
		'class': 'CodeWriter',
		'deps': ['ai_engine'],
		'method': 'write_and_run',
		'description': 'Write, execute, and debug Python code with auto-install',
		'keywords': ['code', 'script', 'python', 'program', 'automate', 'function'],
		'example': 't.code_writer(task="parse CSV and plot bar chart", language="python")',
	},
}

# Augment SkillRegistry with CLI-only capabilities (keywords, examples, CLI-only caps)
try:
	from core.skill_registry import SkillRegistry as _SkillRegistry
	_SkillRegistry.get_instance().augment_cli(_REGISTRY)
except Exception:
	pass  # SkillRegistry is additive; CLI still works without it


# ── Dependency factories ───────────────────────────────────────────────────

def _make_ai_engine(settings, model_name: str | None = None):
	from core.ai_engine import OllamaModel
	return OllamaModel(model_name=model_name)


def _make_search_engine(settings):
	from core.search_engine import DuckDuckGoSearch
	return DuckDuckGoSearch()


def _make_rag_engine(settings):
	from core.rag_engine import RAGEngine
	from core.knowledge_graph_manager import KnowledgeGraphManager
	kg = KnowledgeGraphManager()
	return RAGEngine(knowledge_graph_manager=kg, ai_engine=_make_ai_engine(settings))


def _make_db_handler(settings):
	from core.data_handler import DatabaseHandler
	return DatabaseHandler()


_DEP_FACTORIES = {
	'ai_engine':    lambda s, m=None: _make_ai_engine(s, m),
	'search_engine': lambda s: _make_search_engine(s),
	'rag_engine':   lambda s: _make_rag_engine(s),
	'db_handler':   lambda s: _make_db_handler(s),
}


# ── CapabilityProxy ────────────────────────────────────────────────────────

class CapabilityProxy:
	"""
	Lazy proxy for a single capability. Resolves deps and calls the default
	method when invoked, or can stream output token-by-token.
	"""

	def __init__(self, name: str, platform: 'Thuon'):
		self._name = name
		self._platform = platform

	def __call__(self, *args, **kwargs) -> ThuonResult:
		"""
		Call the capability's default method.
		Accepts either positional Pydantic schema or keyword arguments.
		"""
		# Unwrap a Pydantic schema passed as first positional arg
		if args and hasattr(args[0], 'model_dump'):
			kwargs = {**args[0].model_dump(), **kwargs}

		explain = kwargs.pop('explain', False)
		start = time.time()

		instance, meta = self._platform._instantiate(self._name)
		method = getattr(instance, meta['method'])
		raw = method(**kwargs)

		trace: dict = {}
		if explain:
			trace = {
				'capability':      self._name,
				'method':          meta['method'],
				'elapsed_seconds': round(time.time() - start, 2),
				'deps_resolved':   meta['deps'],
			}

		return ThuonResult(
			raw if isinstance(raw, dict) else {'result': raw},
			capability_name=self._name,
			trace=trace if explain else None,
		)

	def stream(self, *args, **kwargs) -> Iterator[dict]:
		"""
		Stream capability output. Yields progress dicts then the final result.

		  {'type': 'start', 'capability': name}
		  {'type': 'token', 'text': chunk}    ← real LLM tokens if streaming available
		  {'type': 'done',  'result': ThuonResult}
		"""
		if args and hasattr(args[0], 'model_dump'):
			kwargs = {**args[0].model_dump(), **kwargs}

		yield {'type': 'start', 'capability': self._name}

		# Stream via OllamaModel.generate_stream if the capability supports a
		# query/topic/description kwarg we can extract.
		stream_key = next(
			(k for k in ('query', 'topic', 'description', 'instruction', 'task') if k in kwargs),
			None,
		)
		if stream_key:
			ai = self._platform._get_dep('ai_engine')
			if hasattr(ai, 'generate_stream'):
				for token in ai.generate_stream(str(kwargs[stream_key])):
					yield {'type': 'token', 'text': token}

		# Run the full capability for the structured result
		result = self(**kwargs)
		yield {'type': 'done', 'result': result}

	# Allow attribute access on proxy to call non-default methods:
	# t.contract_renegotiator.draft_email(vendor="AWS", current_price=5000)
	def __getattr__(self, method_name: str) -> Any:
		if method_name.startswith('_'):
			raise AttributeError(method_name)

		def _call(**kwargs) -> ThuonResult:
			instance, _ = self._platform._instantiate(self._name)
			method = getattr(instance, method_name)
			raw = method(**kwargs)
			return ThuonResult(
				raw if isinstance(raw, dict) else {'result': raw},
				capability_name=f'{self._name}.{method_name}',
			)
		return _call

	@property
	def info(self) -> dict:
		return _REGISTRY.get(self._name) or self._platform._custom_caps.get(self._name, {})

	@property
	def schema(self):
		from core.schemas import CAPABILITY_SCHEMAS
		return CAPABILITY_SCHEMAS.get(self._name)


# ── Main facade ─────────────────────────────────────────────────────────────

class Thuon:
	"""
	Thuon platform facade — the single entry point.

	Implements all 10 ergonomic improvements:
	  1. Natural language dispatch (do)
	  2. Autowiring DI container (__getattr__ + _instantiate)
	  3. Fluent result objects (ThuonResult)
	  4. Capability registration decorator (@capability)
	  5. Streaming (CapabilityProxy.stream)
	  6. Typed input schemas (CapabilityProxy.schema)
	  7. Pipeline-as-YAML (run_pipeline)
	  8. Hot-reload config (reload_config / model)
	  9. Explain/trace mode (explain=True)
	 10. Self-describing platform (capabilities())
	"""

	def __init__(
		self,
		config_path: str | None = None,
		output_dir: str = '/tmp/thuon',
	):
		self._settings     = get_settings()
		self._config_path  = config_path
		self._output_dir   = output_dir
		self._container: dict[str, Any] = {}
		self._custom_caps: dict[str, dict] = {}
		self._override_model: str | None = None
		os.makedirs(output_dir, exist_ok=True)

	# ── #1 Natural language dispatch ────────────────────────────────────────

	def do(
		self,
		instruction: str,
		explain: bool = False,
		model: str | None = None,
	) -> ThuonResult:
		"""
		Route any natural language instruction to the right capability.

		  t.do("research AI trends in East Africa and produce a PDF report")
		  t.do("search for ICT tenders in Kenya")
		  t.do("generate a flowchart of our deployment pipeline")
		"""
		cap_name, params = self._route(instruction)
		proxy = CapabilityProxy(cap_name, self if model is None else self.model(model))
		return proxy(explain=explain, **params)

	# ── #2 Autowiring DI via __getattr__ ────────────────────────────────────

	def __getattr__(self, name: str) -> CapabilityProxy:
		# Guard: only intercept known capability names
		if name.startswith('_'):
			raise AttributeError(name)
		cap_key = name
		if cap_key in _REGISTRY or cap_key in self.__dict__.get('_custom_caps', {}):
			return CapabilityProxy(cap_key, self)
		raise AttributeError(
			f"Thuon has no capability {name!r}. "
			f"Available: {list(_REGISTRY)}"
		)

	# ── #4 Registration decorator ───────────────────────────────────────────

	def capability(
		self,
		deps: list[str] | None = None,
		name: str | None = None,
		description: str = '',
		keywords: list[str] | None = None,
	):
		"""
		Register a custom function as a Thuon capability.

		  @t.capability(deps=['ai_engine', 'search_engine'], description='...')
		  def my_analyzer(ai_engine, search_engine, sector: str) -> dict:
		      ...

		After registration: t.my_analyzer(sector="fintech")
		"""
		def decorator(fn):
			cap_name = name or fn.__name__

			def _wrapped(**kwargs):
				resolved = {d: self._get_dep(d) for d in (deps or [])}
				return fn(**resolved, **kwargs)

			self._custom_caps[cap_name] = {
				'fn':          _wrapped,
				'deps':        deps or [],
				'description': description,
				'keywords':    keywords or [],
				'method':      '__call__',
			}
			return fn
		return decorator

	# ── #7 Pipeline-as-YAML ─────────────────────────────────────────────────

	def run_pipeline(self, pipeline: str | dict, hooks=None, **params) -> ThuonResult:
		"""
		Run a named pipeline or inline pipeline dict.

		  t.run_pipeline("competitive_report", company="Safaricom", industry="telco")
		  t.run_pipeline("research_brief", topic="AI regulation")
		"""
		from core.pipeline_runner import PipelineRunner
		return PipelineRunner(self, hooks=hooks).run(pipeline, params)

	# ── #8 Hot-reload config ─────────────────────────────────────────────────

	def reload_config(self) -> 'Thuon':
		"""Reload config.yaml and flush cached dependencies."""
		# Force settings to re-read from disk
		import core.settings_manager as sm
		sm._settings_instance = None
		self._settings = get_settings()
		self._container.clear()
		return self

	def model(self, model_name: str) -> 'Thuon':
		"""
		Return a Thuon instance that uses a specific model for this call chain.

		  t.model("llama3.3").do("summarize EU AI Act")
		  t.model("qwen3.5:4b").research_assistant(query="...")
		"""
		clone         = object.__new__(type(self))
		clone.__dict__ = {**self.__dict__, '_container': dict(self._container)}
		clone._override_model = model_name
		clone._container.pop('ai_engine', None)   # force re-create with new model
		return clone

	# ── #10 Self-describing ──────────────────────────────────────────────────

	def capabilities(self, task: str | None = None) -> list[dict]:
		"""
		Return a list of all available capabilities.

		  t.capabilities()
		  t.capabilities(task="find government procurement opportunities")
		"""
		all_caps = [
			{
				'name':        k,
				'description': v['description'],
				'keywords':    v.get('keywords', []),
				'deps':        v.get('deps', []),
				'example':     v.get('example', ''),
			}
			for k, v in {**_REGISTRY, **self._custom_caps}.items()
		]

		if task:
			task_lower = task.lower()

			def relevance(cap: dict) -> int:
				score = 0
				for kw in cap['keywords']:
					if kw.lower() in task_lower:
						score += 2
				if any(w in task_lower for w in cap['name'].split('_')):
					score += 1
				return score

			all_caps = sorted(all_caps, key=relevance, reverse=True)

		return all_caps

	# ── Internal: dep resolution ─────────────────────────────────────────────

	def _get_dep(self, dep: str) -> Any:
		if dep not in self._container:
			factory = _DEP_FACTORIES.get(dep)
			if factory is None:
				raise ValueError(f'Unknown dependency: {dep!r}')
			if dep == 'ai_engine' and self._override_model:
				self._container[dep] = factory(self._settings, self._override_model)
			else:
				sig = inspect.signature(factory)
				if len(sig.parameters) == 1:
					self._container[dep] = factory(self._settings)
				else:
					self._container[dep] = factory(self._settings)
		return self._container[dep]

	def _instantiate(self, cap_name: str) -> tuple[Any, dict]:
		"""Import, instantiate, and return (capability_instance, registry_meta)."""
		# Custom capability
		if cap_name in self._custom_caps:
			meta = self._custom_caps[cap_name]
			return meta['fn'], meta

		meta = _REGISTRY.get(cap_name)
		if meta is None:
			raise ValueError(f'Unknown capability: {cap_name!r}')

		mod  = importlib.import_module(meta['module'])
		cls  = getattr(mod, meta['class'])
		deps = {d: self._get_dep(d) for d in meta['deps']}

		# Try each dep as constructor kwarg; fall back to positional order
		try:
			instance = cls(**deps)
		except TypeError:
			instance = cls(*deps.values())

		return instance, meta

	# ── #1 Routing ───────────────────────────────────────────────────────────

	def _route(self, instruction: str) -> tuple[str, dict]:
		"""Route instruction to (capability_name, params) via SkillRouter."""
		from core.skill_router import SkillRouter
		router = SkillRouter(ai_engine=self._get_dep('ai_engine'))
		allowed = set(_REGISTRY) | set(self._custom_caps)
		return router.route_with_params(instruction, allowed_names=allowed)

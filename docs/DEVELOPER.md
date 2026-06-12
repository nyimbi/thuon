# Thuon Platform — Developer Reference

This document covers the internal architecture, module contracts, extension patterns, and testing approach for contributors and capability authors.

---

## Table of contents

1. [Project layout](#1-project-layout)
2. [Core layer](#2-core-layer)
3. [Capability module pattern](#3-capability-module-pattern)
4. [Adding a new capability](#4-adding-a-new-capability)
5. [Agent loop and tools](#5-agent-loop-and-tools)
6. [Deep researcher internals](#6-deep-researcher-internals)
7. [Niche finder internals](#7-niche-finder-internals)
8. [Web interface wiring](#8-web-interface-wiring)
9. [CLI wiring](#9-cli-wiring)
10. [Configuration system](#10-configuration-system)
11. [ThuonResult and exports](#11-thuonresult-and-exports)
12. [Knowledge ingestion pipeline](#12-knowledge-ingestion-pipeline)
13. [Pipeline runner](#13-pipeline-runner)
14. [Thuon façade](#14-thuon-façade)
15. [Testing guide](#15-testing-guide)
16. [Code conventions](#16-code-conventions)

---

## 1. Project layout

```
Thuon/
├── pyproject.toml                  # dependencies, project metadata
├── README.md                       # user-facing readme
├── docs/
│   ├── DEVELOPER.md                # this file
│   └── CAPABILITY_CATALOG.md       # full parameter + output schema per capability
└── thuon_platform/
    ├── main.py                     # entry point — dispatches to interfaces
    ├── thuon.py                    # Thuon façade — public Python API
    ├── config/
    │   └── config.yaml             # runtime configuration
    ├── data/
    │   ├── templates.yaml          # Jinja2 document templates
    │   └── pipelines/              # YAML pipeline definitions
    │       ├── research_brief.yaml
    │       └── competitive_report.yaml
    ├── core/                       # shared infrastructure (injected into capabilities)
    │   ├── ai_engine.py
    │   ├── agent_loop.py
    │   ├── data_handler.py
    │   ├── document_engine.py      # PDF / DOCX / PPTX / XLSX rendering
    │   ├── knowledge_graph_manager.py
    │   ├── knowledge_ingestion.py  # BM25 chunk store + URL/file extraction
    │   ├── pipeline.py             # Pipeline + Step Pydantic models
    │   ├── pipeline_runner.py      # PipelineRunner — executes YAML pipelines
    │   ├── rag_engine.py
    │   ├── result.py               # ThuonResult — fluent dict wrapper with export methods
    │   ├── result_store.py         # persistent result store
    │   ├── search_engine.py
    │   ├── settings_manager.py
    │   ├── template_manager.py
    │   ├── tools.py
    │   ├── transient_data_manager.py
    │   └── utils.py
    ├── capabilities/               # one file per business capability
    │   ├── research_assistant.py
    │   ├── deep_researcher.py
    │   ├── niche_finder.py
    │   ├── code_writer.py
    │   └── … (32 more)
    ├── interfaces/
    │   ├── web_app.py              # Flask app + CAPABILITY_REGISTRY
    │   ├── cli.py                  # argparse CLI
    │   └── templates/
    │       ├── base.html           # nav, health pill, toasts, shared CSS
    │       ├── index.html          # capability grid + NL dispatch bar + history
    │       ├── capability.html     # capability form + streaming panel + export toolbar
    │       ├── pipelines.html      # pipeline card grid
    │       └── pipeline_run.html   # pipeline inputs + step-progress visualiser
    └── long_running_processes/
        ├── reactor_control.py      # Blinker event bus + ProcessReactor
        └── sensor_monitor.py       # DataSourceManager polling loop
```

---

## 2. Core layer

All core modules live in `thuon_platform/core/`. They are instantiated once at app start and injected into capability constructors — capabilities never import them directly (except for type hints).

### `ai_engine.py`

```python
class AIModel(ABC):
    def generate_text(self, prompt: str, generation_parameters: dict = {}) -> str
    def analyze_sentiment(self, text: str) -> str           # 'positive'|'negative'|'neutral'
    def extract_entities(self, text: str) -> list[dict]
    def summarize_text(self, text: str, length: str) -> str # length: 'short'|'medium'|'long'
    def translate_text(self, text: str, target_language: str) -> str

class OllamaModel(AIModel):
    def __init__(self, model_name: str = 'deepseek-r1', base_url: str = 'http://localhost:11434')
```

`OllamaModel` wraps `langchain_ollama.OllamaLLM`. `OllamaDeepSeekR1` is an alias for backward compatibility.

The agent loop uses `langchain_ollama.ChatOllama` (chat completions with tool-calling) — configured separately in `agent_loop.py`.

### `search_engine.py`

```python
class SearchEngine(ABC):
    def search(self, query: str, num_results: int = 10) -> list[dict]
    # each result: {title, body, href}

class DuckDuckGoSearch(SearchEngine)   # no API key — default
class TavilySearch(SearchEngine)       # key: config api_keys.tavily
class GoogleSerperSearch(SearchEngine) # key: config api_keys.google_serper

def scrape_webpage(url: str) -> str    # returns plain text, truncated to 5000 chars
```

### `data_handler.py`

```python
class DatabaseHandler:
    def __init__(self, host, port, dbname, user, password)
    def connect(self) -> None
    def execute_query(self, query: str, params: tuple = ()) -> list[dict]
    def insert_data(self, table: str, data: dict) -> int           # returns row id
    def fetch_data(self, table: str, conditions: dict = {}) -> list[dict]
    def update_data(self, table: str, data: dict, conditions: dict) -> int
    def delete_data(self, table: str, conditions: dict) -> int
    def create_table(self, table_name: str, schema: dict) -> None
```

Constructed from `config.yaml` values. Call `connect()` lazily — `_ensure_connected()` is called automatically by every public method.

### `rag_engine.py`

```python
class RAGEngine:
    def __init__(self, weaviate_client, llm_engine: AIModel, kg_manager: KnowledgeGraphManager)
    def index_documents(self, documents: list[dict], collection_name: str) -> None
    def query_vector_database(self, query: str, collection_name: str, limit: int) -> list[dict]
    def augment_prompt_with_context(self, prompt: str, context_docs: list[dict]) -> str
    def generate_response_with_rag(self, query: str, collection_name: str) -> str
```

Backed by Weaviate v4 via `knowledge_graph_manager.py`. Near-text vector search for retrieval.

### `knowledge_graph_manager.py`

```python
class KnowledgeGraphManager:
    @classmethod
    def from_settings(cls) -> KnowledgeGraphManager   # reads weaviate.url from config
    def create_schema(self, class_name: str, properties: list[dict]) -> None
    def add_node(self, class_name: str, data: dict) -> str          # returns UUID
    def query_graph(self, class_name: str, query_text: str, limit: int) -> list[dict]
    def update_node_properties(self, class_name: str, uuid: str, data: dict) -> None
    def delete_node(self, class_name: str, uuid: str) -> None
    def add_edge(self, from_class, from_uuid, to_class, to_uuid, relation_name) -> None
```

### `template_manager.py`

```python
class TemplateManager:
    def load_templates(self) -> None                               # reads data/templates.yaml
    def get_template(self, name: str) -> dict                      # raises KeyError if missing
    def list_templates(self) -> list[str]
    def apply_data_to_template(self, template: dict, data: dict) -> str   # Jinja2 render
    def generate_document_from_template_string(
        self, template_str: str, data_dict: dict,
        output_format: str, output_path: str
    ) -> bool
```

`output_format` is `'md'` (plain text) or `'docx'` (python-docx). Returns `True` on success.

### `settings_manager.py`

```python
class SettingsManager:
    def get_setting(self, key_path: str, default=None) -> Any   # dot-path: 'ollama.model'
    def set_setting(self, key_path: str, value: Any) -> None
    def save_settings(self) -> None
    def get_user_preference(self, key: str, default=None) -> Any
    def set_user_preference(self, key: str, value: Any) -> None

def get_settings() -> SettingsManager   # module-level singleton
```

### `utils.py`

```python
def log_message(message: str, level: str = 'INFO') -> None
def handle_exception(exception: Exception, message: str) -> None
def validate_data(data: Any, schema: dict) -> bool          # jsonschema
def load_yaml_file(file_path: str) -> dict                  # returns {} on missing file
def save_yaml_file(data: dict, file_path: str) -> bool
def load_json_file(file_path: str) -> dict                  # returns {} on missing file
def save_json_file(data: dict, file_path: str) -> bool
```

### `transient_data_manager.py`

```python
class TransientDataManager:
    def __init__(self, base_dir: str = '/tmp/thuon')
    def create_temp_directory(self) -> str
    def create_temp_file(self, suffix: str = '.json') -> str    # returns path
    def save_data_to_temp_file(self, data: Any, file_path: str) -> bool
    def load_data_from_temp_file(self, file_path: str) -> Any
    def cleanup_temp_file(self, file_path: str) -> None
    def cleanup_temp_directory(self, dir_path: str) -> None
    def cleanup_all(self) -> None
```

---

## 3. Capability module pattern

Every capability follows this structure:

```python
# capabilities/my_capability.py
import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine  # inject only what you need


class MyCapability:
    def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
        self.ai_engine = ai_engine
        self.search_engine = search_engine

    def do_the_thing(self, param_a: str, param_b: list = []) -> dict:
        # 1. Gather context
        results = self.search_engine.search(f'{param_a} topic', num_results=5)
        context = '\n'.join(r.get('body', '')[:300] for r in results[:3])

        # 2. Build structured prompt
        prompt = (
            f'You are an expert in {param_a}.\n\n'
            f'Context:\n{context}\n\n'
            f'Task: {param_b}\n\n'
            f'Return JSON with keys: summary, recommendations (list), confidence_level.'
        )

        # 3. Call LLM and parse JSON
        response = self.ai_engine.generate_text(prompt)
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {'result': response, 'status': 'success'}
```

**Rules:**
- Constructor takes only core objects — never instantiate `OllamaModel` or `DuckDuckGoSearch` inside a capability.
- Primary method always returns `dict`.
- JSON extraction via `re.search(r'\{.*\}', response, re.DOTALL)` with a plain-text fallback.
- No side effects on the filesystem unless the method signature includes an `output_path` parameter.
- No `print()` statements — callers render the dict.

---

## 4. Adding a new capability

### Step 1 — Write the module

```bash
# thuon_platform/capabilities/my_new_cap.py
```

Follow the pattern in §3. Name the file in `snake_case.py`.

### Step 2 — Register it in the web app

Open `thuon_platform/interfaces/web_app.py` and add an entry to `CAPABILITY_REGISTRY`:

```python
'my_new_cap': {
    'description': 'One-sentence description shown in the UI.',
    'method': 'do_the_thing',           # public method to call
    'params': [
        {'name': 'param_a', 'type': 'str',  'required': True},
        {'name': 'param_b', 'type': 'list', 'required': False, 'default': []},
    ],
    'deps': ['ai_engine', 'search_engine'],   # keys from _build_deps()
    'module': 'capabilities.my_new_cap',
    'class': 'MyNewCap',
},
```

Available `deps` keys:

| Key | Type | Notes |
|---|---|---|
| `ai_engine` | `OllamaModel` | always available |
| `search_engine` | `DuckDuckGoSearch` | always available |
| `rag_engine` | `RAGEngine` | requires Weaviate |
| `db_handler` | `DatabaseHandler` | requires PostgreSQL |
| `template_manager` | `TemplateManager` | always available |

### Step 3 — Add to category map

In `web_app.py`, add your module name to `_CATEGORY_MAP`:

```python
'my_new_cap': 'strategy',   # research|content|analytics|strategy|hr|risk|data|dev
```

### Step 4 — Add a CLI subcommand (optional)

In `thuon_platform/interfaces/cli.py`, add a subcommand handler following the existing pattern:

```python
def cli_my_new_cap(args):
    deps = _build_common_deps(args)
    cap = MyNewCap(ai_engine=deps['ai_engine'], search_engine=deps['search_engine'])
    result = cap.do_the_thing(param_a=args.param_a, param_b=args.param_b)
    _print_result(result)
```

Register it in `main_cli()`:

```python
p = subparsers.add_parser('my-new-cap', help='...')
p.add_argument('--param-a', required=True)
p.add_argument('--param-b', nargs='+', default=[])
p.set_defaults(func=cli_my_new_cap)
```

### Step 5 — Write tests

```bash
tests/ci/test_my_new_cap.py
```

See §11 for the test pattern. Run `uv run pytest tests/ci/test_my_new_cap.py -v` before committing.

---

## 5. Agent loop and tools

### `core/tools.py`

Six LangChain `@tool`-decorated functions callable by the agent loop:

| Tool | Signature | Notes |
|---|---|---|
| `web_search` | `(query: str, num_results: int = 8) -> str` | Uses module-level `_search = DuckDuckGoSearch()` singleton |
| `scrape_url` | `(url: str) -> str` | `requests` + BeautifulSoup, 5000-char truncation |
| `execute_python` | `(code: str) -> str` | Sandboxed via `subprocess.run(['python3', tmpfile], timeout=30)` |
| `write_file` | `(path: str, content: str) -> str` | Writes to filesystem |
| `read_file` | `(path: str) -> str` | Reads from filesystem |
| `list_directory` | `(path: str = '.') -> str` | Returns directory listing |

Pre-built tool sets:

```python
RESEARCH_TOOLS = [web_search, scrape_url, execute_python, write_file, read_file]
CODE_TOOLS     = [execute_python, write_file, read_file, list_directory, web_search]
ALL_TOOLS      = [web_search, scrape_url, execute_python, write_file, read_file, list_directory]
```

**Patching in tests:** `web_search` uses a module-level singleton. Replace it directly:

```python
import core.tools as tools_mod
tools_mod._search = mock_search_object
```

### `core/agent_loop.py`

```python
class AgentLoop:
    def __init__(
        self,
        tools: list,
        model_name: str = None,      # defaults to config ollama.chat_model
        base_url: str = None,        # defaults to config ollama.endpoint
        max_iterations: int = 15,
        system_prompt: str = None,
        temperature: float = 0.0,
    )

    def run(self, query: str) -> dict:
        # Returns:
        # {
        #   answer: str,
        #   iterations: int,
        #   tool_calls: list[{tool, args, result_preview}],
        #   elapsed_seconds: float,
        #   status: 'success' | 'max_iterations_reached',
        #   warning: str,   # only when max_iterations_reached
        # }
```

The loop runs a ReAct cycle: `llm_with_tools.invoke(messages)` → check `response.tool_calls` → dispatch each to its `tool.invoke(args)` → append `ToolMessage` → repeat. Stops when the model returns no tool calls or `max_iterations` is reached.

Factory functions:

```python
research_agent(model_name=None, max_iterations=15) -> AgentLoop
code_agent(model_name=None, max_iterations=12)     -> AgentLoop
```

**Testing without Ollama:** bypass `__init__` with `AgentLoop.__new__(AgentLoop)` and set `llm_with_tools` directly:

```python
agent = AgentLoop.__new__(AgentLoop)
agent.tools = [mock_tool]
agent.tools_by_name = {'my_tool': mock_tool}
agent.max_iterations = 5
agent.system_prompt = None
agent.llm_with_tools = mock_llm   # MagicMock with .invoke.side_effect = [...]
```

---

## 6. Deep researcher internals

`capabilities/deep_researcher.py` — `DeepResearcher(ai_engine, search_engine)`

```python
def research(self, query: str, level: str = 'medium') -> dict
```

Level routing:

```python
RESEARCH_LEVELS = {
    'quick':         {'max_iter': 0,    ...},
    'shallow':       {'max_iter': 1,    ...},
    'medium':        {'max_iter': 10,   ...},
    'deep':          {'max_iter': 20,   ...},
    'comprehensive': {'max_iter': 35,   ...},
    'academic':      {'max_iter': None, ...},   # multi-phase orchestration
    'phd':           {'max_iter': None, ...},   # systematic review
}
```

Levels `quick`–`comprehensive` delegate to `AgentLoop` with increasing `max_iterations` and optional extra instructions (`read_full_articles`, `multi_angle`). Levels `academic` and `phd` are multi-phase Python orchestrations — each phase calls the LLM or a focused sub-agent independently, then synthesises.

**Academic phases** (7):
1. `_decompose` — LLM breaks the query into 5 sub-questions
2. `_investigate_sub_question` — one `AgentLoop(max_iter=8)` per sub-question
3. Full-text scraping of top 2 sources per sub-question
4. `_synthesize_sub_question` — focused LLM synthesis per sub-question
5. `_integrate` — LLM integrates all sub-syntheses
6. `_critique` — LLM evaluates the integrated analysis
7. `_write_academic_report` — structured JSON output (abstract, lit review, analysis, conclusion)

**PhD phases** (10):
1. `_formulate_research_question` — refine to precise scholarly RQ
2. `_define_scope` — inclusion/exclusion criteria, search strategy
3. Multi-angle literature search (5 orthogonal search vectors)
4. `_evaluate_sources` — LLM rates each source for inclusion
5. Full-text reading of top 8 sources
6. `_thematic_analysis` — identify cross-cutting themes
7. `_map_contradictions` — where sources disagree
8. `_gap_analysis` — what is NOT known
9. `_original_synthesis` — novel analytical perspective
10. `_write_thesis_chapter` — full academic chapter structure
11. `_self_critique` — peer-reviewer-style assessment

All LLM calls use `_llm_json(prompt, fallback_key)` which extracts the first JSON object from the response and falls back to `{fallback_key: response_text}`.

`ResearchAssistant.perform_research` routes to `DeepResearcher` for levels `quick`, `comprehensive`, `academic`, and `phd`. Levels `medium` and `deep` go through a direct `AgentLoop` call to preserve the exact API tested by `test_research_assistant_deep_uses_agent`.

---

## 7. Niche finder internals

`capabilities/niche_finder.py` — `NicheFinder(ai_engine, search_engine)`

```python
def find_niches(
    self,
    industry: str,
    mode: str = 'research',       # 'quick' | 'research'
    num_niches: int = 3,          # clamped to 1-5
    focus_area: str = '',
) -> dict
```

**Quick mode** — single structured LLM prompt with the full niche-finder system prompt. No search calls. Returns the same JSON schema as research mode but flagged with a `confidence_note`.

**Research mode** — 4 parallel search phases followed by an agent loop synthesis, then a final structured LLM call:

| Phase | Search queries | LLM output |
|---|---|---|
| `_phase_landscape` | incumbents, startup funding, product feature comparisons | `incumbents`, `startups`, `technology_stack`, `market_maturity` |
| `_phase_pmf` | user pain points (Reddit/HN), unmet needs, G2/Capterra reviews | `well_served_needs`, `underserved_needs`, `friction_points` |
| `_phase_trends` | regulatory changes, market reports, behavioral shifts | `regulatory_tailwinds`, `behavioral_trends`, `technology_enablers` |
| `_phase_pricing` | pricing pages, LTV/CAC benchmarks, unit economics teardowns | `observed_pricing_models`, `willingness_to_pay_signals` |
| `_phase_agent_synthesis` | `AgentLoop(max_iterations=15)` with niche-finder system prompt | Free-form research, follows cross-cutting leads |
| `_synthesize_niches` | All phase outputs combined | Final `niches` list with all required keys |

Each niche proposition contains: `hypothesis`, `target_segment`, `jtbd`, `differentiator`, `revenue_model`, `pricing_logic`, `market_size_estimate`, `competitive_moat`, `unit_economics_note`, `risks`, `gtm_path`.

---

## 8. Web interface wiring

`thuon_platform/interfaces/web_app.py`

### Routes

| Route | Method | Handler | Description |
|---|---|---|---|
| `/` | GET | `index` | Capability grid; passes `_CATEGORY_MAP` as `category_map` for Jinja `tojson` injection |
| `/capability/<name>` | GET | `capability_page` | Capability form with streaming toggle and export toolbar |
| `/api/<name>` | POST | `run_capability` | Synchronous JSON execution |
| `/api/stream/<name>` | POST | `stream_capability` | SSE: `start` → `token` chunks from result text fields → `done` |
| `/api/do` | POST | `nl_dispatch` | NL routing via `_get_router()._route(instruction)` |
| `/api/history` | GET | `run_history` | Returns `list(_run_history)` — last 50 entries |
| `/api/export` | POST | `export_result` | Wraps result in `ThuonResult`, renders to requested format, streams file |
| `/api/capabilities` | GET | `list_capabilities` | Full registry as JSON |
| `/pipelines` | GET | `pipelines_index` | Loads `data/pipelines/*.yaml`, renders card grid |
| `/pipeline/<name>` | GET | `pipeline_page` | Loads spec, extracts `{input.x}` vars, renders run form |
| `/api/pipeline/<name>` | POST | `run_pipeline` | Runs spec via `PipelineRunner(_PlatformShim())` |
| `/health` | GET | `health` | Service status dict |

#### SSE streaming detail

`stream_capability` runs the capability **once** then yields text fields as `token` chunks:

```python
# pseudo-code for _generate()
result = method(**call_kwargs)
for key in ('content', 'report', 'analysis', ...):
    if isinstance(result.get(key), str):
        for chunk in split_120(result[key]):
            yield SSE(type='token', text=chunk)
        break
yield SSE(type='done', result=result, elapsed=elapsed)
```

No preliminary AI pass — a single LLM call per request.

#### NL dispatch detail

`nl_dispatch` calls `_get_router()._route(instruction)` which uses a module-level `Thuon` instance (lazy-initialised). Routing tries LLM JSON extraction first, then falls back to keyword overlap scoring across all capabilities in `_REGISTRY`. If routing raises (e.g. Ollama down), the handler falls back to `research_assistant`.

### CAPABILITY_REGISTRY

The registry is a `dict[str, dict]` at module level. Every entry needs:

```python
{
    'description': str,
    'method': str,          # method name on the class
    'params': list[dict],   # {name, type, required, default, choices (optional)}
    'deps': list[str],      # subset of: ai_engine, search_engine, rag_engine, db_handler, template_manager
    'module': str,          # importable dotted path
    'class': str,           # class name within module
}
```

### Request handling

`POST /api/<cap_name>` flow:
1. Look up `cfg = CAPABILITY_REGISTRY[cap_name]`
2. Import `cfg['module']`, get `cfg['class']`
3. Build dependency dict from `cfg['deps']` using shared singletons
4. Instantiate: `instance = CapClass(**deps)`
5. Extract params from request JSON, apply defaults for missing optional params
6. Call `getattr(instance, cfg['method'])(**params)`
7. Return `jsonify(result)`

### Jinja2 filters

Three custom filters registered in `create_app()`:

| Filter | Function | Description |
|---|---|---|
| `categorize` | `_categorize_filter(name)` | Maps capability name → category string via `_CATEGORY_MAP` |
| `cap_icon` | `_cap_icon_filter(name)` | Maps capability name → emoji icon |
| `cap_icon_style` | `_cap_icon_style_filter(name)` | Maps category → CSS gradient style string |

---

## 9. CLI wiring

`thuon_platform/interfaces/cli.py`

### `_build_common_deps(args)`

Constructs all core objects from `args` flags and `config.yaml`. Returns:

```python
{
    'ai_engine':      OllamaModel(...),
    'search_engine':  DuckDuckGoSearch(),
    'db_handler':     DatabaseHandler(...),   # only if --use-db flag
    'rag_engine':     RAGEngine(...),          # only if --use-rag flag
    'template_manager': TemplateManager(),
}
```

### Subcommand handler pattern

```python
def cli_research_assistant(args):
    deps = _build_common_deps(args)
    ra = ResearchAssistant(
        ai_engine=deps['ai_engine'],
        search_engine=deps['search_engine'],
        rag_engine=deps.get('rag_engine'),
    )
    result = ra.perform_research(
        research_query=args.query,
        depth=args.depth,
    )
    _print_result(result)
```

`_print_result(result)` serialises `result` to indented JSON on stdout.

---

## 10. Configuration system

Settings are loaded once at startup by `get_settings()` (returns a `SettingsManager` singleton).

Dot-path access:

```python
from core.settings_manager import get_settings
settings = get_settings()

settings.get_setting('ollama.model')           # 'deepseek-r1'
settings.get_setting('database.host')          # 'localhost'
settings.get_setting('api_keys.tavily')        # 'YOUR_...'
settings.get_setting('nonexistent', default='fallback')
```

`OllamaModel`, `AgentLoop`, `DatabaseHandler`, and the search engines all read from `settings` during construction. Override at test time by passing explicit constructor arguments — no settings access needed.

---

## 11. ThuonResult and exports

`core/result.py` — `ThuonResult(data: dict, capability_name: str, trace: dict | None)`

All capability methods return plain `dict`. `ThuonResult` is a dict-compatible wrapper that adds fluent export methods. Flask's `jsonify` works directly because `ThuonResult` implements `keys()` and `items()`.

```python
from core.result import ThuonResult

result = ThuonResult({'summary': 'AI trends...', 'recommendations': [...]}, 'research_assistant')

# Export
result.to_docx()                   # writes to /tmp/thuon_results/<uuid>.docx
result.to_pdf()                    # → .pdf
result.to_slides()                 # → .pptx
result.to_xlsx(rows=[...])         # → .xlsx (pass rows explicitly or uses result['rows'])
result.as_diagram(ai_engine=ai)    # generates a Mermaid diagram via DiagramGenerator

# Access
result['summary']                  # dict-style read
result.get('missing', 'default')
'summary' in result                # True

# Trace (when explain=True was used)
result.trace                       # dict of execution trace entries
result.explain()                   # human-readable trace string
```

### `_content_for_doc()`

Extracts the best text field for document rendering. Checks keys in order: `content`, `report`, `analysis`, `result`, `text`, `summary`, `answer`, `proposal_content`, `brief`. Returns the first non-empty string. Falls back to `json.dumps(self._data)` if none found.

Threshold: `len(val) > 0` — any non-empty string qualifies. Previously `> 50` silently discarded short but valid content.

### `_tmp_path(ext)`

```python
def _tmp_path(ext: str) -> str:
    d = '/tmp/thuon_results'
    os.makedirs(d, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=f'.{ext}', dir=d)
    os.close(fd)
    return path
```

Uses `mkstemp` (not `mktemp`) to avoid TOCTOU races. The file descriptor is closed immediately; the path is passed to the document engine for writing.

### Export route cleanup

`POST /api/export` uses the same `mkstemp` pattern and registers an `after_this_request` hook to unlink the temp file after Flask streams it to the client.

---

## 12. Knowledge ingestion pipeline

`core/knowledge_ingestion.py` — `KnowledgeIngestionPipeline(store_path: str | None)`

A BM25-indexed chunk store for offline document retrieval. Useful for capabilities that need to search over a local corpus (e.g. uploaded PDFs, scraped articles).

```python
from core.knowledge_ingestion import KnowledgeIngestionPipeline

pipe = KnowledgeIngestionPipeline(store_path='/tmp/kb.json')

# Ingest sources
pipe.ingest_file('report.pdf')                         # PDF, DOCX, or plain text
pipe.ingest_url('https://example.com/article')         # trafilatura → fallback requests+BS4
pipe.ingest_text('Raw text content', source='manual')  # direct text

# Search
results = pipe.search('AI regulation', top_k=5)
# → [{'score': float, 'source': str, 'text': str}, ...]

context = pipe.get_context('AI regulation', top_k=3)
# → "[[Source: ...]\n<text>\n\n---\n\n[Source: ...]..."

# Metadata
pipe.chunk_count   # int — total chunks stored
pipe.source_count  # int — distinct sources
pipe.clear()       # wipe all chunks and delete store file
```

**Deduplication:** SHA-256 of the full text — ingesting the same document twice is a no-op.

**BM25 index:** built lazily on first `search()` call and invalidated only when new chunks are actually appended (`added > 0`). Re-ingesting a duplicate never triggers a rebuild.

**Persistence:** if `store_path` is supplied, chunks are saved to JSON after every successful ingest and loaded automatically on init.

**URL extraction:** tries `trafilatura` first (cleaner text extraction), falls back to `requests` + BeautifulSoup. The fallback calls `r.raise_for_status()` before parsing — HTTP errors surface as exceptions rather than returning error-page HTML silently.

---

## 13. Pipeline runner

`core/pipeline_runner.py` — `PipelineRunner(platform)`

Executes multi-step YAML pipelines. Each step calls a capability on `platform` (any object with a `__getattr__` that dispatches to capability methods).

```python
from core.pipeline_runner import PipelineRunner

runner = PipelineRunner(platform_shim)
results = runner.run(spec_dict, inputs_dict)
# → [{'step': 'research', 'status': 'success', 'result': {...}}, ...]
```

### YAML spec format

```yaml
name: research_brief
description: Research a topic then write an executive brief
steps:
  - name: research
    capability: research_assistant
    params:
      research_query: "{input.topic}"
      depth: medium
  - name: brief
    capability: ai_report_writer
    params:
      report_type: executive_brief
      context_data: "{research.summary}"
```

**Template interpolation:** `{input.x}` resolves from the caller-supplied `inputs` dict; `{step_name.key}` resolves from a previous step's result dict. Interpolation is applied to every string-valued param before the step runs.

### `_PlatformShim` (web_app.py)

The Flask `run_pipeline` route wraps `_build_instance` in a shim so `PipelineRunner` can call any registered capability without knowing about Flask:

```python
class _PlatformShim:
    def __getattr__(self, name):
        if name in CAPABILITY_REGISTRY:
            cfg = CAPABILITY_REGISTRY[name]
            instance = _build_instance(name)
            method = getattr(instance, cfg['method'])
            sig = inspect.signature(method)
            def _call(**kwargs):
                return method(**{k: v for k, v in kwargs.items() if k in sig})
            return _call
        raise AttributeError(name)
```

### Adding a pipeline

1. Create `thuon_platform/data/pipelines/<name>.yaml` following the spec above.
2. Use `{input.x}` for user-supplied inputs and `{prev_step.key}` for chaining.
3. The pipeline appears automatically in the `/pipelines` grid on next request — no code changes needed.

---

## 14. Thuon façade

`thuon_platform/thuon.py` — `Thuon(config_path=None, output_dir='/tmp/thuon')`

The public Python API for using Thuon programmatically without Flask or CLI:

```python
from thuon_platform.thuon import Thuon

t = Thuon()

# Natural language dispatch
result = t.do("research the global EV battery supply chain")
result = t.do("generate a SWOT diagram for Tesla", explain=True)
print(result.explain())        # execution trace
result.to_pdf()                # export to /tmp/thuon_results/<uuid>.pdf

# Direct capability access
result = t.research_assistant.perform_research("AI safety", depth="academic")
result = t.deep_researcher.research("fusion energy timelines", level="comprehensive")
result = t.niche_finder.find_niches("edtech", mode="research", num_niches=2)

# Model override
result = t.model('qwen2.5').code_writer.write_and_run("write a Fibonacci generator in Rust")

# Register a custom capability
t.register('my_cap', MyCapClass, deps=['ai_engine'], method='run')
result = t.my_cap.run(param='value')
```

### Dep injection

`Thuon` uses `_DEP_FACTORIES` — a dict of `dep_key → factory(settings)` functions. Deps are lazily created and cached in `self._container`. A capability receives only the deps it declares via `_get_dep(key)` — missing deps raise `ValueError`, not `None`.

### Routing

`Thuon._route(instruction)` calls the LLM with a structured prompt listing all capabilities and their descriptions, then parses the JSON response. Falls back to keyword-overlap scoring if JSON extraction fails. Used internally by `do()` and by the web app's NL dispatch handler.

### `CapabilityProxy`

`t.research_assistant` returns a `CapabilityProxy` object. Accessing a method name on it (`proxy.perform_research(...)`) instantiates the capability class with the right deps, calls the method, and wraps the result in `ThuonResult`. The proxy is not pre-instantiated — each attribute access creates a fresh instance.

---

## 15. Testing guide

All tests live in `tests/ci/`. Run with:

```bash
uv run pytest tests/ci/ -q        # all tests
uv run pytest tests/ci/ -v        # verbose
uv run pytest tests/ci/ -x        # stop on first failure
```

No live services are required. The full suite runs offline.

### Mocking the LLM

```python
from unittest.mock import MagicMock

ai = MagicMock()
ai.generate_text.return_value = '{"summary": "Test.", "key_findings": []}'
ai.summarize_text.return_value = 'Short summary.'
```

### Mocking search

```python
search = MagicMock()
search.search.return_value = [
    {'title': 'Source A', 'body': 'Content.', 'href': 'https://ex.com/a'},
]
```

### Mocking the agent loop

For capabilities that call `research_agent()` or `code_agent()` internally:

```python
from unittest.mock import patch, MagicMock

mock_result = {
    'answer': 'Agent answer.',
    'iterations': 5,
    'tool_calls': [],
    'elapsed_seconds': 2.0,
    'status': 'success',
}
with patch('core.agent_loop.research_agent') as mock_factory:
    mock_agent = MagicMock()
    mock_agent.run.return_value = mock_result
    mock_factory.return_value = mock_agent
    result = capability.method(...)
mock_factory.assert_called_once_with(max_iterations=10)
```

For `AgentLoop` instantiation (e.g. `NicheFinder`):

```python
with patch('core.agent_loop.AgentLoop') as MockLoop:
    mock_loop = MagicMock()
    mock_loop.run.return_value = mock_result
    MockLoop.return_value = mock_loop
    result = niche_finder.find_niches('fintech', mode='research')
```

### Mocking `web_search` tool

`web_search` uses a module-level singleton `_search`. Replace it directly:

```python
import core.tools as tools_mod

orig = tools_mod._search
tools_mod._search = mock_search
try:
    result = web_search.invoke({'query': 'test', 'num_results': 3})
finally:
    tools_mod._search = orig
```

### Patching `research_agent` called inside a function body

Because `research_agent` is imported inside `_deep_research` / `_agentic` at call time, patch the source module:

```python
with patch('core.agent_loop.research_agent') as mock:
    ...
```

Patching `capabilities.research_assistant.research_agent` will **not** work — the name doesn't exist at the module level of `research_assistant`.

### Async tests

No `@pytest.mark.asyncio` decorator needed. Use plain `async def` and call via:

```python
loop = asyncio.get_event_loop()
result = loop.run_until_complete(my_async_func())
```

### Test file naming

`tests/ci/test_<module_or_feature>.py` — pytest autodiscovers everything in `tests/ci/`.

---

## 16. Code conventions

**Language:** Python 3.11+  
**Formatter/linter:** `ruff check`  
**Type checker:** `uv run pyright`  
**Package manager:** `uv` — edit `pyproject.toml`, run `uv sync`

**Style:**
- Tabs, not spaces
- Modern typing: `str | None`, `list[str]`, `dict[str, Any]`
- No comments unless the *why* is non-obvious
- No docstrings on obvious methods

**Models:** Pydantic v2 when structured input validation is needed:
```python
from pydantic import BaseModel, ConfigDict, Field
class MyModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_by_name=True)
    name: str
    value: int = Field(default=0)
```

**IDs:** UUID7 via `uuid6`:
```python
from uuid6 import uuid7
id: str = Field(default_factory=lambda: str(uuid7()))
```

**Logging:** use `log_message` from `core.utils`, not `print()` or bare `logging`.

**Error handling:** validate at system boundaries (user input, external APIs). Don't add try/except for internal code paths that shouldn't fail.

**Capability return values:** always `dict`. Never raise — return `{'error': '...'}` for user-facing errors, let internal exceptions propagate to the interface layer which catches and serialises them.

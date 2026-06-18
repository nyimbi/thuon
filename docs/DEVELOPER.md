# Thuon Platform — Developer Reference

Internal architecture, module contracts, extension patterns, and testing guide.

---

## Table of contents

1. [Project layout](#1-project-layout)
2. [Bundle-aware path resolution](#2-bundle-aware-path-resolution)
3. [Core layer](#3-core-layer)
4. [Capability module pattern](#4-capability-module-pattern)
5. [Adding a new capability](#5-adding-a-new-capability)
6. [Skill registry and SKILL.md](#6-skill-registry-and-skillmd)
7. [Pipeline runner](#7-pipeline-runner)
8. [Pipeline lifecycle hooks](#8-pipeline-lifecycle-hooks)
9. [Business data stores](#9-business-data-stores)
10. [Notification bus and scheduler](#10-notification-bus-and-scheduler)
11. [Memory system](#11-memory-system)
12. [Company knowledge base](#12-company-knowledge-base)
13. [Web interface wiring](#13-web-interface-wiring)
14. [Desktop app](#14-desktop-app)
15. [Packaging — PyInstaller .app bundle](#15-packaging--pyinstaller-app-bundle)
16. [MCP server](#16-mcp-server)
17. [Agent loop and tools](#17-agent-loop-and-tools)
18. [Deep researcher internals](#18-deep-researcher-internals)
19. [Niche finder internals](#19-niche-finder-internals)
20. [ThuonResult and exports](#20-thuonresult-and-exports)
21. [Knowledge ingestion pipeline](#21-knowledge-ingestion-pipeline)
22. [Thuon façade](#22-thuon-façade)
23. [Testing guide](#23-testing-guide)
24. [Code conventions](#24-code-conventions)

---

## 1. Project layout

```
Thuon/
├── pyproject.toml
├── README.md
├── Makefile                        # build / dmg / install / login-enable targets
├── thuon.spec                      # PyInstaller build spec
├── docs/
│   ├── DEVELOPER.md                # this file
│   ├── CAPABILITY_CATALOG.md       # full parameter + output schema per capability
│   └── research/                   # research reports for feature decisions
└── thuon_platform/
    ├── main.py                     # entry point — dispatches to interfaces
    ├── app_entry.py                # frozen entry point for .app bundle
    ├── thuon.py                    # Thuon façade — public Python API
    ├── config/
    │   └── config.yaml             # runtime configuration
    ├── data/
    │   ├── templates.yaml          # Jinja2 document templates
    │   ├── company/                # company knowledge base *.md files
    │   └── pipelines/              # YAML pipeline definitions
    ├── skills/                     # SKILL.md extension directory
    ├── core/                       # shared infrastructure
    │   ├── bundle.py               # ★ bundle-aware path resolution
    │   ├── ai_engine.py
    │   ├── agent_loop.py
    │   ├── calendar_store.py       # business calendar (SQLite)
    │   ├── company_profile.py      # BM25 knowledge store over company/*.md
    │   ├── data_handler.py
    │   ├── document_engine.py
    │   ├── knowledge_graph_manager.py
    │   ├── knowledge_ingestion.py
    │   ├── login_item.py           # macOS LaunchAgent plist management
    │   ├── mcp_server.py           # MCP tool definitions from SkillRegistry
    │   ├── memory_store.py         # three-tier persistent memory
    │   ├── neditor_bridge.py
    │   ├── notification_bus.py     # thread-safe event queue + SSE generator
    │   ├── obsidian_bridge.py
    │   ├── pipeline.py
    │   ├── pipeline_hooks.py       # PipelineHooks — before/after/error/complete
    │   ├── pipeline_runner.py
    │   ├── rag_engine.py
    │   ├── result.py
    │   ├── result_store.py
    │   ├── rfp_tracker.py          # RFP record store (JSON-persisted, status FSM)
    │   ├── scheduler.py            # APScheduler wrapper + job registration
    │   ├── search_engine.py
    │   ├── session_store.py
    │   ├── settings_manager.py
    │   ├── skill_registry.py       # SkillRegistry singleton
    │   ├── skill_router.py
    │   ├── task_store.py           # todo / task store (SQLite)
    │   ├── template_manager.py
    │   ├── tools.py
    │   └── utils.py
    ├── capabilities/               # one file per business capability (60+)
    └── interfaces/
        ├── web_app.py
        ├── desktop_app.py          # macOS menubar app
        ├── cli.py
        └── templates/
```

---

## 2. Bundle-aware path resolution

**All file paths must go through `core/bundle.py`.** Never use `Path(__file__).parent.parent` to construct data paths.

### Why

PyInstaller freezes `__file__` to a path inside `sys._MEIPASS` (a temp extraction dir). Parent-chain navigation still points into the read-only bundle. Writable runtime data must go to `~/Library/Application Support/Thuon/` so the app can write without needing admin rights.

Additionally, pywebview injects `..` components into `__file__` at runtime, which confuses `pathlib.Path.parent` counts. `.resolve()` is required to collapse them.

### API

```python
from core.bundle import (
    app_root,        # read-only: source tree in dev, _MEIPASS in bundle
    user_data_dir,   # writable: ~/.thuon/ in dev, ~/Library/Application Support/Thuon/ in bundle
    config_dir,      # config/  — writable in bundle, source tree in dev
    writable_data_dir,  # data/  — writable runtime data (DBs, generated files)
    pipelines_dir,   # data/pipelines/  — always read-only
    skills_dirs,     # [app_root/skills, user_data_dir/skills]
)
```

In dev mode all functions return paths inside `thuon_platform/` — identical to the old hardcoded values. The bundle-aware behaviour only activates when `sys.frozen` is set by PyInstaller.

### Usage pattern

```python
# ✓ correct
from core.bundle import writable_data_dir
_DB_PATH = writable_data_dir() / 'tasks.db'

# ✗ wrong — breaks in bundle
_DB_PATH = Path(__file__).parent.parent / 'data' / 'tasks.db'
```

### Override for tests

```python
# conftest.py or individual test
import os, tempfile
os.environ['THUON_DATA_DIR'] = tempfile.mkdtemp()
```

`writable_data_dir()` and `config_dir()` will use the override path; `app_root()` always returns the source tree root regardless.

---

## 3. Core layer

All core modules are in `thuon_platform/core/`. They are instantiated once at startup and injected into capability constructors.

### `ai_engine.py`

```python
class AIModel(ABC):
    def generate_text(self, prompt: str, generation_parameters: dict = {}) -> str
    def analyze_sentiment(self, text: str) -> str
    def summarize_text(self, text: str, length: str) -> str   # 'short'|'medium'|'long'
    def translate_text(self, text: str, target_language: str) -> str

class OllamaModel(AIModel):
    def __init__(self, model_name='deepseek-r1', base_url='http://localhost:11434')
```

### `search_engine.py`

```python
class DuckDuckGoSearch(SearchEngine)   # no API key — default
class TavilySearch(SearchEngine)       # config api_keys.tavily
class GoogleSerperSearch(SearchEngine) # config api_keys.google_serper

def scrape_webpage(url: str) -> str    # plain text, truncated to 5000 chars
```

### `settings_manager.py`

```python
from core.settings_manager import get_settings
s = get_settings()
s.get_setting('ollama.model')              # dot-path access
s.set_setting('company.name', 'Acme')
s.save_settings()
```

Config lives at `config_dir() / 'config.yaml'` (via `bundle.config_dir()`).

### `template_manager.py`

Loads `data/templates.yaml` (via `bundle.app_root()`). Jinja2 renders to `md` or `docx`.

---

## 4. Capability module pattern

```python
# capabilities/my_capability.py
from core.ai_engine import AIModel
from core.search_engine import SearchEngine

class MyCapability:
    def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
        self.ai_engine = ai_engine
        self.search_engine = search_engine

    def do_the_thing(self, param_a: str, param_b: list = []) -> dict:
        results = self.search_engine.search(param_a, num_results=5)
        context = '\n'.join(r.get('body', '')[:300] for r in results[:3])
        prompt = (
            f'Context:\n{context}\n\n'
            f'Return JSON: {{"summary": str, "recommendations": list}}'
        )
        response = self.ai_engine.generate_text(prompt)
        from core.llm_utils import extract_json
        return extract_json(response) or {'result': response}
```

Rules:
- Constructor takes only injected core objects — never instantiate `OllamaModel` inside a capability.
- Primary method returns `dict`.
- No `print()` — callers render the dict.
- Use `core.llm_utils.extract_json` for JSON extraction with fallback.
- Writable output files use `writable_data_dir() / 'subdir'`, not `Path(__file__)`.

---

## 5. Adding a new capability

### 1. Write the module

`thuon_platform/capabilities/my_new_cap.py` following §4.

### 2. Register in web_app.py

```python
'my_new_cap': {
    'description': 'One-sentence description shown in the UI.',
    'method': 'do_the_thing',
    'params': [
        {'name': 'param_a', 'type': 'str',  'required': True},
        {'name': 'param_b', 'type': 'list', 'required': False, 'default': []},
    ],
    'deps': ['ai_engine', 'search_engine'],
    'module': 'capabilities.my_new_cap',
    'class': 'MyNewCap',
},
```

Available `deps` keys: `ai_engine`, `search_engine`, `rag_engine`, `db_handler`, `template_manager`, `company_profile`.

### 3. Add to category map

```python
'my_new_cap': 'strategy',  # research|content|analytics|strategy|hr|risk|data|dev
```

### 4. Write tests

`tests/ci/test_my_new_cap.py` — see §23 for patterns. Move passing tests to `tests/ci/` for CI autodiscovery.

---

## 6. Skill registry and SKILL.md

`core/skill_registry.py` — `SkillRegistry` singleton.

All capabilities are unified in a single registry. The registry is seeded at startup from `CAPABILITY_REGISTRY` (web) and `_REGISTRY` (CLI façade), then augmented with any `SKILL.md` files found in `skills_dirs()`.

### SKILL.md format

```markdown
---
name: my_skill
description: What this skill does
keywords: [keyword1, keyword2]
thuon:
  module: capabilities.my_module
  class: MyClass
  method: run
  deps: [ai_engine]
  category: research
  params:
    - name: topic
      type: str
      required: true
---

Natural language description of the skill, trigger phrases, usage examples.
Injected into context when the skill activates.
```

Drop a `SKILL.md` file in `thuon_platform/skills/<skill-name>/SKILL.md` (or `~/.thuon/skills/<skill-name>/SKILL.md` for user-local extensions). The registry picks it up at next startup — no Python code changes needed.

### Registry API

```python
from core.skill_registry import SkillRegistry

reg = SkillRegistry.get_instance()
manifest = reg.get('deep_researcher')         # → SkillManifest | None
results  = reg.search('find government tenders', top_k=5)  # BM25 keyword search
all_caps = reg.all()                          # → list[SkillManifest]
```

---

## 7. Pipeline runner

`core/pipeline_runner.py` — `PipelineRunner(platform, hooks=None)`

Executes multi-step YAML pipelines. Template vars: `{input.x}` from user inputs, `{steps.step_name.key}` from previous step results.

```yaml
name: rfp_response
steps:
  - name: ingest
    capability: rfp_ingester
    params:
      rfp_source: "{input.rfp_source}"
  - name: bid
    capability: rfp_bid_evaluator
    params:
      scope_summary: "{steps.ingest.scope_summary}"
```

Pipelines are YAML files in `pipelines_dir()` (`thuon_platform/data/pipelines/`). Drop a new file there — it appears automatically in the `/pipelines` grid.

### Adding a pipeline

1. Create `thuon_platform/data/pipelines/<name>.yaml`.
2. Use `{input.x}` for user inputs and `{steps.prev_step.key}` for chaining.
3. No code changes needed.

---

## 8. Pipeline lifecycle hooks

`core/pipeline_hooks.py` — `PipelineHooks`

```python
from core.pipeline_hooks import PipelineHooks, StepEvent

hooks = PipelineHooks()
hooks.on_before(lambda e: print(f'→ {e.step_name}'))
hooks.on_after(lambda e: print(f'✓ {e.step_name} ({e.elapsed:.1f}s)'))
hooks.on_error(lambda e: print(f'✗ {e.step_name}: {e.error}'))
hooks.on_complete(lambda e: print('pipeline done'))

from core.pipeline_runner import PipelineRunner
runner = PipelineRunner(platform_shim, hooks=hooks)
result = runner.run('rfp_response', {'rfp_source': 'path/to/rfp.pdf'})
```

`StepEvent` fields: `pipeline_name`, `step_name`, `cap_name`, `params`, `result` (after), `elapsed` (after), `error` (on_error).

`PipelineHooks.is_empty()` — `True` if no handlers registered. The runner checks this once before the loop to avoid overhead when hooks aren't used.

---

## 9. Business data stores

All stores use SQLite or JSON, live in `writable_data_dir()`, and expose a module-level singleton getter.

### `task_store.py` — `TaskStore`

```python
from core.task_store import get_task_store
store = get_task_store()
task = store.create(title='Follow up on proposal', priority=1, due_date='2026-07-01')
store.update(task['id'], status='in_progress')
store.by_status()          # → {pending: [...], in_progress: [...], ...}
store.overdue()            # tasks with due_date < today
store.stats()              # → {total, pending, in_progress, completed, overdue}
```

Statuses: `pending` → `in_progress` → `completed` | `cancelled`.

### `calendar_store.py` — `CalendarStore`

```python
from core.calendar_store import get_calendar_store
cal = get_calendar_store()
cal.create(title='RFP Deadline: Acme', date='2026-07-15', event_type='rfp_deadline')
cal.upcoming(days=30)
cal.for_month(2026, 7)
cal.sync_rfp_deadlines()   # pulls deadlines from RFPTracker and upserts
cal.due_alerts()           # events whose alert threshold crossed but not yet fired
```

Event types: `rfp_deadline`, `contract_start`, `contract_end`, `certification_exp`, `meeting`, `review`, `milestone`, `reminder`, `other`.

### `rfp_tracker.py` — `RFPTracker`

JSON-persisted. Status FSM: `discovered → evaluating → awaiting_strategy → responding → in_review → submitted → won | lost | no_bid`.

```python
from core.rfp_tracker import get_rfp_tracker
tracker = get_rfp_tracker()
rfp = tracker.create(title='..', issuer='..', summary='..')
tracker.advance_status(rfp.id, 'evaluating')   # validates FSM transitions
tracker.all(status='responding')
```

### `memory_store.py` — `MemoryStore`

Three-tier: `USER.md` (identity), `MEMORY.md` (facts), `sessions.db` (episodic log with FTS5).

```python
from core.memory_store import get_memory_store
mem = get_memory_store()
mem.add_user_fact('Prefers executive summaries under 200 words')
mem.add_memory_fact('Q3 target market: Federal civilian agencies')
mem.log_episode(session_id, 'user', 'What RFPs do we have?')
ctx = mem.get_context_block('RFP response', top_episodes=5)  # for prompt injection
```

---

## 10. Notification bus and scheduler

### `notification_bus.py` — `NotificationBus`

Thread-safe queue for in-app notifications. The `/api/notifications/stream` SSE endpoint consumes it.

```python
from core.notification_bus import get_notification_bus, Notification
bus = get_notification_bus()
bus.publish(Notification(
    event_type='rfp_found',
    title='New RFP: Acme Corp',
    message='Deadline: 2026-08-01',
    data={'rfp_id': '...'},
))
```

### `scheduler.py` — `Scheduler`

APScheduler wrapper. Jobs are registered at app startup in `create_app()`.

Default jobs:

| Job | Schedule | Action |
|---|---|---|
| `rfp_discovery` | every 6h | runs `tender_scout` → publishes `rfp_found` notifications |
| `social_daily` | daily 08:00 | collects ideas → runs `social_posts` pipeline |
| `kb_reload` | every 1h | `company_profile.reload()` |
| `alert_check` | daily 07:00 | `calendar_store.due_alerts()` → notifications |

To add a job:

```python
from core.scheduler import get_scheduler
sched = get_scheduler()
sched.add_job('my_job', my_function, trigger='interval', hours=2)
```

---

## 11. Memory system

See §9 `memory_store.py` for the API. The three-tier design:

| Tier | File | Contents |
|---|---|---|
| 1 | `USER.md` | User identity, preferences, working style |
| 2 | `MEMORY.md` | Persistent facts about the company and world |
| 3 | `sessions.db` | Episodic event log — FTS5 indexed for semantic recall |

`get_context_block(query)` returns a formatted block ready for injection into capability prompts. It pulls all three tiers: user profile, memory facts, and top-matching episodes.

`MemoryConsolidator` (capability) runs periodically to summarise old episodes into `MEMORY.md` and prune the episodic log.

---

## 12. Company knowledge base

`core/company_profile.py` — `CompanyProfile`

Loads all `data/company/*.md` files into a BM25 store at startup. All RFP and content capabilities receive the company profile as an injected dep.

```python
from core.company_profile import get_company_profile
kb = get_company_profile()
ctx = kb.get_context('past performance federal contracts', top_k=5)
raw = kb.get_file('win_themes.md')
kb.list_files()    # → ['bid_criteria.md', 'capabilities.md', ...]
kb.reload()        # re-ingest all files (called hourly by scheduler)
```

The default directory is `writable_data_dir() / 'company'`. Override via `config.yaml → company.profile_dir`.

Relative paths in config are resolved against `app_root().parent` (the repo root), which makes paths like `thuon_platform/data/company` work correctly in dev.

---

## 13. Web interface wiring

`thuon_platform/interfaces/web_app.py` — `create_app() -> Flask`

### Route groups

| Group | Routes | Description |
|---|---|---|
| Capabilities | `/`, `/capability/<n>`, `/api/<n>`, `/api/stream/<n>` | Capability grid, form, sync/stream execution |
| Dispatch | `/api/do` | NL routing |
| Pipelines | `/pipelines`, `/pipeline/<n>`, `/api/pipeline/<n>` | YAML pipeline UI and execution |
| RFP | `/rfps`, `/rfp/<id>`, `/api/rfp/*` | Kanban, detail, discover, approve, CRUD |
| Content | `/content`, `/content/blog`, `/content/social`, `/content/website` | Content hub |
| Tasks | `/tasks`, `/api/tasks`, `/api/tasks/<id>` | Task CRUD |
| Calendar | `/calendar`, `/api/events` | Calendar CRUD + RFP sync |
| Memory | `/memory`, `/api/memory/*` | Memory viewer and management |
| Settings | `/settings/company`, `/api/settings/company/<f>` | Company KB editor |
| Notifications | `/api/notifications/stream`, `/api/notifications` | SSE feed |
| Export | `/api/export` | Download result as docx/pdf/xlsx/pptx |
| Health | `/health` | Service status |

### CAPABILITY_REGISTRY entry

```python
'cap_name': {
    'description': str,
    'method': str,
    'params': [{'name', 'type', 'required', 'default', 'choices'}],
    'deps': ['ai_engine', 'search_engine', ...],
    'module': 'capabilities.module_name',
    'class': 'ClassName',
}
```

### SSE streaming

`/api/stream/<cap>` runs the capability **once**, then chunks text fields into `token` SSE events before the final `done` event. No double LLM call.

### NL dispatch

`POST /api/do` → `_get_router()._route(instruction)` → LLM JSON extraction → keyword fallback → capability execution.

---

## 14. Desktop app

`interfaces/desktop_app.py` — `run_desktop_app()`

Architecture:
1. Flask starts in a daemon thread on port 5099.
2. pywebview creates a WKWebView window pointing at `http://localhost:5099`.
3. `webview.start(callback)` calls `callback` from a background thread.
4. AppKit/NSStatusBar work is dispatched to the main thread via `performSelectorOnMainThread_withObject_waitUntilDone_`.

```python
# Main-thread dispatch pattern (required for all AppKit calls)
class _MainDispatch(NSObject):
    def runSetup_(self, _):
        refs = _setup_statusbar(win)
        _refs.extend(refs)   # keep PyObjC objects alive

trampoline = _MainDispatch.alloc().init()
trampoline.performSelectorOnMainThread_withObject_waitUntilDone_(
    'runSetup:', None, False
)
```

`NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)` hides the app from the Dock and Cmd-Tab switcher. `LSUIElement: True` in the bundle plist handles this at the OS level before any Python runs.

`_refs` list is kept in the enclosing `run_desktop_app` scope to prevent PyObjC objects from being garbage-collected.

### Login item

`core/login_item.py` writes `~/Library/LaunchAgents/com.thuon.app.plist` and calls `launchctl load -w`. Only active in the frozen bundle (`sys.frozen`). No-op in dev.

```python
from core.login_item import enable, disable, toggle, is_enabled
toggle()   # installs or removes the plist, returns True if now enabled
```

---

## 15. Packaging — PyInstaller .app bundle

### Build

```bash
make build      # uv run pyinstaller --clean --noconfirm thuon.spec → dist/Thuon.app
make dmg        # wraps dist/Thuon.app in a hdiutil UDZO DMG
make install    # cp -R dist/Thuon.app /Applications/
```

### Entry point

`thuon_platform/app_entry.py` — the frozen entry script:
1. Ensures `sys._MEIPASS` is in `sys.path`.
2. Calls `ensure_first_run()` to seed user data dir on first launch.
3. Calls `run_desktop_app()`.

### Spec key points (`thuon.spec`)

- `pathex=['thuon_platform']` — so `from core.bundle import …` resolves without the `thuon_platform.` prefix.
- `datas` includes: `interfaces/templates`, `interfaces/static`, `skills`, `data/pipelines`, `data/company`, `config`.
- `hiddenimports` includes PyObjC (`AppKit`, `Foundation`, `objc`) and `webview.platforms.cocoa` which PyInstaller misses.
- `LSUIElement: True` in `info_plist` — Dock hide at OS level.
- `NSAllowsLocalNetworking: True` — allows WKWebView to reach `localhost:5099`.

### First-run seeding (`core/bundle.py` — `ensure_first_run()`)

On the first launch, copies bundled defaults into `user_data_dir()`:
- `config/config.yaml`
- `data/company/` (template markdown files)
- `data/pipelines/`
- `data/templates.yaml`

Writes `user_data_dir() / .initialized` marker so the copy only runs once.

---

## 16. MCP server

`core/mcp_server.py` exposes all registered Thuon capabilities as MCP tools.

Tools are generated dynamically from `SkillRegistry.all()`. Each `SkillManifest` becomes an MCP tool with:
- `name` → `manifest.name`
- `description` → `manifest.description`
- `inputSchema` → built from `manifest.params`

Start alongside Flask:
```python
from core.mcp_server import create_mcp_server
mcp = create_mcp_server()
mcp.run()   # stdio or SSE transport
```

Or use the CLI: `uv run python thuon_platform/main.py mcp`.

---

## 17. Agent loop and tools

### `core/tools.py`

Six LangChain `@tool` functions:

| Tool | Signature | Notes |
|---|---|---|
| `web_search` | `(query, num_results=8)` | Uses module-level `_search` singleton |
| `scrape_url` | `(url)` | BeautifulSoup, 5000-char truncation |
| `execute_python` | `(code)` | Subprocess sandbox, 30s timeout |
| `write_file` | `(path, content)` | |
| `read_file` | `(path)` | |
| `list_directory` | `(path='.')` | |

Patch `web_search` in tests: `import core.tools as t; t._search = mock_search`

### `core/agent_loop.py`

```python
class AgentLoop:
    def __init__(self, tools, model_name=None, max_iterations=15, system_prompt=None)
    def run(self, query: str) -> dict
    # → {answer, iterations, tool_calls, elapsed_seconds, status, warning?}

research_agent(model_name=None, max_iterations=15) -> AgentLoop
code_agent(model_name=None, max_iterations=12)     -> AgentLoop
```

ReAct loop: `llm_with_tools.invoke(messages)` → dispatch tool calls → append `ToolMessage` → repeat until no tool calls or `max_iterations`.

Testing without Ollama:
```python
agent = AgentLoop.__new__(AgentLoop)
agent.tools = []; agent.tools_by_name = {}; agent.max_iterations = 5
agent.system_prompt = None
agent.llm_with_tools = MagicMock()
agent.llm_with_tools.invoke.side_effect = [mock_response]
```

---

## 18. Deep researcher internals

`capabilities/deep_researcher.py` — `DeepResearcher(ai_engine, search_engine)`

Levels `quick`–`comprehensive` delegate to `AgentLoop` with increasing `max_iterations`. Levels `academic` and `phd` are multi-phase Python orchestrations.

**Academic** (7 phases): decompose → investigate each sub-question (one AgentLoop each) → full-text scrape top sources → per-sub synthesize → integrate → critique → structured report.

**PhD** (10 phases): formulate RQ → define scope → multi-angle lit search (5 vectors) → evaluate sources → full-text read top 8 → thematic analysis → contradiction mapping → gap analysis → original synthesis → thesis chapter → self-critique.

All LLM calls use `_llm_json(prompt, fallback_key)` which extracts the first JSON object and falls back to `{fallback_key: response_text}`.

---

## 19. Niche finder internals

`capabilities/niche_finder.py` — `NicheFinder(ai_engine, search_engine)`

**Quick mode:** single structured LLM prompt, no search.

**Research mode:** 4 parallel search phases (landscape, PMF signals, trends, pricing) → `AgentLoop(max_iter=15)` synthesis → final structured LLM call with all phase outputs.

Each niche: `hypothesis`, `target_segment`, `jtbd`, `differentiator`, `revenue_model`, `pricing_logic`, `market_size_estimate`, `competitive_moat`, `unit_economics_note`, `risks`, `gtm_path`.

---

## 20. ThuonResult and exports

`core/result.py` — `ThuonResult(data: dict, capability_name: str)`

Dict-compatible wrapper with export methods. `jsonify` works directly.

```python
result = ThuonResult({'summary': '...', 'recommendations': [...]}, 'research_assistant')
result.to_docx()     # → /tmp/thuon_results/<uuid>.docx
result.to_pdf()
result.to_slides()   # → .pptx
result.to_xlsx(rows=[...])
result['summary']    # dict-style access
```

`_content_for_doc()` checks keys in order: `content`, `report`, `analysis`, `result`, `text`, `summary`, `answer`, `proposal_content`, `brief`.

---

## 21. Knowledge ingestion pipeline

`core/knowledge_ingestion.py` — `KnowledgeIngestionPipeline(store_path)`

BM25-indexed chunk store for local corpus search.

```python
pipe = KnowledgeIngestionPipeline('/tmp/kb.json')
pipe.ingest_file('report.pdf')
pipe.ingest_url('https://example.com/article')
pipe.ingest_text('Raw content', source='manual')
results = pipe.search('AI regulation', top_k=5)
# → [{score, source, text}, ...]
```

Deduplication via SHA-256. BM25 index rebuilt lazily only when new chunks are added. URL extraction tries `trafilatura` first, falls back to requests + BeautifulSoup.

---

## 22. Thuon façade

`thuon_platform/thuon.py` — `Thuon(config_path=None)`

```python
from thuon_platform.thuon import Thuon
t = Thuon()

# NL dispatch
result = t.do("research EV battery supply chain")
result.to_pdf()

# Direct capability access
result = t.research_assistant.perform_research("AI safety", depth="academic")
result = t.niche_finder.find_niches("edtech", mode="research", num_niches=2)

# Pipeline with hooks
from core.pipeline_hooks import PipelineHooks
hooks = PipelineHooks()
hooks.on_after(lambda e: print(f'✓ {e.step_name} ({e.elapsed:.1f}s)'))
result = t.run_pipeline("rfp_response", hooks=hooks, rfp_source="path/to/rfp.pdf")

# Model override
result = t.model('qwen2.5').code_writer.write_and_run("Fibonacci in Rust")
```

Deps are lazily created and cached. `CapabilityProxy.__call__` instantiates fresh capability instances per call.

---

## 23. Testing guide

All tests in `tests/ci/`. No live services required.

```bash
cd thuon_platform
uv run pytest tests/ci/ -q        # all tests
uv run pytest tests/ci/ -x -v     # stop on first failure, verbose
uv run pyright                     # type check
```

### Mocking the LLM

```python
ai = MagicMock()
ai.generate_text.return_value = '{"summary": "Test.", "key_findings": []}'
```

### Mocking search

```python
search = MagicMock()
search.search.return_value = [{'title': 'A', 'body': 'Content.', 'href': 'https://ex.com'}]
```

### Mocking the agent loop

```python
with patch('core.agent_loop.research_agent') as mock_factory:
    mock_agent = MagicMock()
    mock_agent.run.return_value = {'answer': '...', 'status': 'success', 'tool_calls': []}
    mock_factory.return_value = mock_agent
    result = capability.method(...)
```

Patch `core.agent_loop.research_agent`, not `capabilities.my_cap.research_agent` — the name doesn't exist at the capability module level.

### Mocking `web_search` tool

```python
import core.tools as tools_mod
orig = tools_mod._search
tools_mod._search = mock_search
try:
    result = web_search.invoke({'query': 'test', 'num_results': 3})
finally:
    tools_mod._search = orig
```

### Async tests

No `@pytest.mark.asyncio` needed:

```python
async def test_something():
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(my_async_func())
    assert result['status'] == 'success'
```

### Isolating writable data in tests

```python
import os, tempfile, pytest

@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path):
    os.environ['THUON_DATA_DIR'] = str(tmp_path)
    yield
    del os.environ['THUON_DATA_DIR']
```

This redirects all `writable_data_dir()` calls to a temp directory without touching `~/.thuon/`.

---

## 24. Code conventions

**Language:** Python 3.11+  
**Formatter/linter:** `ruff check`  
**Type checker:** `uv run pyright`  
**Package manager:** `uv` — edit `pyproject.toml`, run `uv sync`

**Style:**
- Tabs, not spaces
- Modern typing: `str | None`, `list[str]`, `dict[str, Any]`
- No comments unless the *why* is non-obvious
- No docstrings on obvious methods

**Models:** Pydantic v2:
```python
from pydantic import BaseModel, ConfigDict, Field
class MyModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_by_name=True)
    name: str
    value: int = Field(default=0)
```

**IDs:** UUID7:
```python
from uuid6 import uuid7
id: str = Field(default_factory=lambda: str(uuid7()))
```

**Logging:** `logging.getLogger('thuon.<module>')`, not `print()`.

**Paths:** always via `core.bundle` functions — see §2.

**Capability return values:** always `dict`. Return `{'error': '...'}` for user-facing errors; let internal exceptions propagate to the interface layer.

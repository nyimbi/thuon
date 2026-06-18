# Thuon

Thuon is a locally-run AI business automation platform. It chains 60+ atomic capabilities — each producing structured JSON — into YAML pipelines that cover the full business development cycle: RFP response, content creation, company knowledge management, competitive intelligence, and more.

All inference runs through a local **Ollama** server. No external LLM API keys required. Runs as a macOS menu-bar app, a web server, or a CLI.

---

## Quick start

### Desktop app (recommended)

```bash
uv sync
uv run python thuon_platform/main.py desktop
```

Thuon appears as a `T` icon in your menu bar. No Dock icon. Click the icon to show/hide the panel.

### Web server

```bash
uv run python thuon_platform/main.py web
# → http://localhost:5000
```

### CLI

```bash
uv run python thuon_platform/main.py cli research --query "AI in drug discovery"
uv run python thuon_platform/main.py cli report --type market_analysis --context "EV sector 2025"
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| [uv](https://docs.astral.sh/uv/) | latest | package manager |
| [Ollama](https://ollama.ai) | latest | local LLM server |
| PostgreSQL | 14+ | optional — DB-backed capabilities only |
| Weaviate | 1.24+ | optional — RAG capabilities only |

```bash
# Pull required Ollama models
ollama pull deepseek-r1   # text generation / reasoning
ollama pull qwen2.5       # tool-calling agent loop
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Interfaces                                     │
│  Desktop (menubar)   Flask Web (:5000)   CLI (argparse)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Capability Layer  (60+ modules)                │
│  RFP: ingester · bid_evaluator · section_writer · assembler      │
│  Content: blog_researcher · blog_writer · seo_optimizer          │
│  Intel: deep_researcher · competitive_intel · niche_finder       │
│  Strategy: proposal · rfp_win_strategy · website_refresh         │
└──────┬─────────────┬──────────────┬─────────────┬───────────────┘
       │             │              │             │
┌──────▼──────┐ ┌────▼────┐ ┌──────▼──────┐ ┌───▼──────────────┐
│  AI Engine  │ │ Search  │ │  Knowledge  │ │  Persistent Data  │
│ OllamaModel │ │DuckDuckG│ │    Store    │ │  SQLite / JSON    │
│ deepseek-r1 │ │ Tavily  │ │ BM25 + RAG  │ │  tasks · rfp      │
│  qwen2.5   │ └─────────┘ └─────────────┘ │  calendar · memory│
└──────┬──────┘                             └───────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                  YAML Pipeline Runner                            │
│  rfp_response · blog_post · website_refresh · social_posts       │
│  Template vars: {input.x}  {steps.step_name.key}                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

`thuon_platform/config/config.yaml`:

```yaml
ollama:
  endpoint: http://localhost:11434
  model: deepseek-r1          # text generation, reasoning
  chat_model: qwen2.5         # tool-calling agent loop

database:
  host: localhost
  port: 5432
  dbname: thuon_db
  user: thuon_user
  password: thuon_password    # optional — only for DB capabilities

weaviate:
  url: http://localhost:8080   # optional — only for RAG capabilities

api_keys:
  tavily: YOUR_TAVILY_API_KEY  # optional — better search quality

company:
  profile_dir: ""              # absolute path to your company/*.md files
                               # default: thuon_platform/data/company/

obsidian:
  vault_path: ""               # absolute path to Obsidian vault (optional)
  inbox_folder: "Thuon Inbox"
  rfp_folder: "RFPs"
  blog_folder: "Blog Posts"

website:
  url: ""                      # your site URL for the website refresh pipeline
  site_repo_path: ""           # local static site repo root

scheduler:
  enabled: true
  rfp_discovery_interval_hours: 6
  social_daily_hour: 8
```

---

## Desktop app

The desktop app is a macOS menu-bar accessory (no Dock icon, no Cmd-Tab entry). It embeds the full web UI in a WKWebView panel.

```
Menu:  T
       ├── Toggle Thuon
       ├── ─────────────
       ├── Home
       ├── RFPs
       ├── Content
       ├── Company KB
       ├── ─────────────
       ├── ✓ Open at Login   ← toggle LaunchAgent
       ├── ─────────────
       └── Quit Thuon  ⌘Q
```

**Open at Login** installs a LaunchAgent plist at `~/Library/LaunchAgents/com.thuon.app.plist` so Thuon starts automatically at login.

---

## Web interface

| Route | Description |
|---|---|
| `/` | Capability grid — search, filter, NL dispatch bar |
| `/capability/<name>` | Capability form with streaming toggle + export toolbar |
| `/pipelines` | Pipeline card grid |
| `/pipeline/<name>` | Pipeline run form with step-progress visualiser |
| `/rfps` | RFP Kanban board |
| `/rfp/<id>` | RFP detail — bid score, approval buttons |
| `/content` | Content hub — blog, social, website |
| `/content/blog` | Blog post board |
| `/content/social` | Social idea board + generated posts |
| `/content/website` | Website refresh controls |
| `/tasks` | Task / to-do Kanban |
| `/calendar` | Business calendar (RFP deadlines, milestones) |
| `/memory` | Three-tier memory viewer |
| `/settings/company` | Edit company knowledge base files in-browser |
| `/health` | Ollama / DB / scheduler status |

### API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/<capability>` | POST | Call any capability (JSON in, JSON out) |
| `/api/stream/<capability>` | POST | SSE stream — `start` → `token` chunks → `done` |
| `/api/do` | POST | Natural-language dispatch |
| `/api/pipeline/<name>` | POST | Execute a YAML pipeline |
| `/api/history` | GET | Last 50 run records |
| `/api/export` | POST | Download result as `docx`, `pdf`, `xlsx`, `pptx` |
| `/api/capabilities` | GET | All capabilities and parameter schemas |
| `/api/rfp/discover` | POST | Trigger RFP discovery |
| `/api/rfp/<id>/approve` | POST | Advance past a human checkpoint |
| `/api/notifications/stream` | GET | SSE notification feed |
| `/api/tasks` | GET/POST | Task CRUD |
| `/api/events` | GET/POST | Calendar event CRUD |

---

## Natural language dispatch

```bash
curl -X POST http://localhost:5000/api/do \
  -H "Content-Type: application/json" \
  -d '{"instruction": "research the competitive landscape for AI coding assistants"}'
# → {"capability": "competitive_intelligence_operative", "result": {...}, "elapsed": 4.2}
```

---

## Streaming

```bash
curl -N -X POST http://localhost:5000/api/stream/research_assistant \
  -H "Content-Type: application/json" \
  -d '{"research_query": "quantum computing timelines"}'
# data: {"type": "start", "capability": "research_assistant"}
# data: {"type": "token", "text": "Quantum computing ..."}
# data: {"type": "done", "result": {...}, "elapsed": 12.4}
```

---

## Pipelines

Chain capabilities with YAML. Drop files in `thuon_platform/data/pipelines/` — they appear automatically.

```yaml
# thuon_platform/data/pipelines/research_brief.yaml
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
      context_data: "{steps.research.summary}"
```

```bash
curl -X POST http://localhost:5000/api/pipeline/research_brief \
  -H "Content-Type: application/json" \
  -d '{"topic": "synthetic biology commercialisation"}'
```

### Pipeline lifecycle hooks

```python
from thuon import Thuon
from core.pipeline_hooks import PipelineHooks, StepEvent

hooks = PipelineHooks()
hooks.on_before(lambda e: print(f"→ {e.step_name}"))
hooks.on_after(lambda e: print(f"✓ {e.step_name} ({e.elapsed:.1f}s)"))

t = Thuon()
result = t.run_pipeline("rfp_response", hooks=hooks, rfp_source="path/to/rfp.pdf")
```

---

## Company knowledge base

Fill in `thuon_platform/data/company/*.md` — all RFP, content, and strategy capabilities pull context from these files automatically.

| File | Contents |
|---|---|
| `profile.md` | Name, tagline, mission, NAICS codes, certifications, diversity status |
| `capabilities.md` | Service catalog, technical specs, differentiators |
| `past_performance.md` | Project write-ups with client, results, contract value |
| `personnel.md` | Key personnel bios, skills, clearances |
| `pricing.md` | Rate cards, overhead/G&A, escalation rules |
| `win_themes.md` | Battle-tested win themes with proof points |
| `compliance_boilerplate.md` | Standard T&Cs, insurance certs |
| `style_guide.md` | Tone of voice, formatting rules |
| `bid_criteria.md` | Bid/no-bid rules: revenue floors, risk thresholds |

Edit files in-browser at `/settings/company` or directly on disk. The knowledge base reloads hourly via the scheduler.

---

## Capabilities

### RFP & Proposals

| Module | Description |
|---|---|
| `rfp_ingester` | Parse RFP source (URL/path/text) → structured requirements |
| `rfp_compliance_matrix_builder` | Build shall/should compliance matrix from requirements |
| `rfp_bid_evaluator` | Score bid 0-100, recommend go/no-go with rationale |
| `rfp_customer_researcher` | Customer strategic priorities, pain points, leadership focus |
| `rfp_competitor_analyst` | Incumbents, competitor strengths, differentiation angles |
| `rfp_win_strategy_builder` | Win themes, ghost strategies, executive summary blueprint |
| `rfp_section_writer` | Write a single proposal section against requirements |
| `rfp_consistency_checker` | Cross-check all sections against compliance matrix |
| `rfp_assembler` | Assemble sections into final document |
| `proposal_compositor` | General business proposal composition |
| `contract_renegotiator` | Contract renegotiation strategy |

### Content

| Module | Description |
|---|---|
| `blog_topic_researcher` | Discover SEO-optimised blog topics with keyword targets |
| `blog_outliner` | Section-by-section outline with word targets |
| `blog_section_writer` | Write individual blog sections |
| `blog_seo_optimizer` | Optimize full post for target keyword; output to `data/blog/` |
| `social_trend_researcher` | Platform trends, hashtags, best posting times |
| `social_post_writer` | Platform-specific post text (LinkedIn, Twitter, etc.) |
| `website_content_auditor` | Audit a page for content quality, freshness, SEO |
| `website_gap_analyzer` | Missing topics, outdated claims, SEO gaps vs competitors |
| `website_section_writer` | Rewrite a page section with improvements |
| `website_seo_optimizer` | SEO-optimize page with title tag and meta description |
| `website_change_assembler` | Write optimized pages to site repo |
| `website_creator` | Generate page-by-page website content from scratch |
| `ai_report_writer` | Structured reports from templates |
| `internal_communications_automator` | Memos, announcements, briefings |
| `course_creator` | Course outlines with assessments |
| `long_form_document_engine` | 10k–100k word documents (books, white papers, reports) |
| `document_generator` | General document generation |
| `diagram_generator` | Mermaid diagram generation |

### Research & Intelligence

| Module | Description |
|---|---|
| `research_assistant` | Web + RAG research across 7 depth levels |
| `deep_researcher` | Standalone multi-level research engine |
| `niche_finder` | Strategic niche analysis with GTM propositions |
| `competitive_intelligence_operative` | Competitor landscape, positioning matrix |
| `market_sales_research` | Market sizing, segment analysis, forecasting |
| `consulting_research_engine` | Consulting-grade research synthesis |
| `ma_target_profiler` | M&A target profiling |
| `psychographic_profile_generator_analyzer` | Customer psychographic segmentation |
| `brand_sentiment_orchestrator` | Multi-channel brand sentiment analysis |
| `intellectual_property_strategist` | Patent landscape and IP strategy |
| `tender_scout` | Discover public tenders matching company profile |
| `daily_brief` | Morning brief: emails, todos, calendar, FX, weather |

### Analytics & Finance

| Module | Description |
|---|---|
| `financial_forecasting_analyst` | Financial forecasting from DB data |
| `FinancialAccountant` | Invoice generation and records |
| `process_optimization_analyst` | Process efficiency analysis |
| `sustainability_impact_simulator` | Environmental impact scoring |
| `receipt_analyzer` | Receipt parsing and expense categorization |

### Strategy & Operations

| Module | Description |
|---|---|
| `negotiation_strategy_builder` | BATNA and negotiation tactics |
| `supply_chain_resilience_planner` | Supply chain risk and mitigation |
| `crisis_simulation_response_architect` | Crisis simulation and response playbooks |
| `cultural_transformation_designer` | Culture change roadmap |
| `WorkflowAutomator` | Workflow automation blueprints |
| `weekly_review_generator` | Weekly business review synthesis |
| `pre_meeting_brief` | Pre-meeting research and agenda preparation |
| `meeting_notes_extractor` | Extract action items and decisions from meeting notes |

### HR & People

| Module | Description |
|---|---|
| `HumanResourceManager` | Onboarding plans and HR records |
| `talent_analytics_succession_forecaster` | Succession candidate prediction |
| `ProjectTaskManager` | Project and task breakdown |

### Risk & Compliance

| Module | Description |
|---|---|
| `ethical_ai_governance_engine` | Ethical risk scoring for AI systems |
| `CybersecurityGuardian` | Vulnerability assessment reports |
| `LegalComplianceOfficer` | Contract review and compliance gaps |
| `accessibility_compliance_verifier` | WCAG / ADA compliance checklist |
| `regulatory_change_manager` | Regulatory monitoring and impact assessment |

---

## Research depth levels

Both `research_assistant` and `deep_researcher` accept a `depth`/`level` parameter:

| Level | Strategy | Approx. time |
|---|---|---|
| `quick` | LLM prior knowledge only | ~2 s |
| `shallow` | Single search batch + synthesis | ~10 s |
| `medium` | Agent loop, 10 iterations *(default)* | ~1 min |
| `deep` | 20 iterations, reads full articles | ~3 min |
| `comprehensive` | 35 iterations, multi-angle search | ~5 min |
| `academic` | Decompose → investigate each sub-question → cross-synthesise → critique | ~10 min |
| `phd` | Systematic review: question formulation → scoped lit search → source evaluation → thematic analysis → gap analysis → original synthesis | ~20 min |

---

## Export

```bash
curl -X POST http://localhost:5000/api/export \
  -H "Content-Type: application/json" \
  -d '{"format": "docx", "data": {"report": "..."}, "title": "Q3 Analysis"}' \
  --output export.docx
```

Supported: `docx`, `pdf`, `xlsx`, `pptx`.

---

## Packaging & distribution

Build a standalone macOS `.app` with no Python or uv dependency:

```bash
make build       # → dist/Thuon.app
make dmg         # → dist/Thuon.dmg  (drag-to-Applications)
make install     # copy to /Applications/
```

Enable login item (run at startup):

```bash
make login-enable    # installs LaunchAgent
make login-disable   # removes it
```

Or toggle from the `T` menu bar icon → **Open at Login**.

---

## Testing

```bash
# All CI tests (no live services required)
cd thuon_platform && uv run pytest tests/ci/ -q

# Single file
uv run pytest tests/ci/test_deep_researcher.py -v

# Type checking
uv run pyright
```

---

## License

MIT

---

Built by **Datacraft** · nyimbi@gmail.com

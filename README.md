# Thuon Platform

Thuon is a locally-run, modular AI business-capability platform. Each capability is a self-contained module that combines an LLM, web search, vector-RAG, and a SQL database to produce structured JSON output. A Flask web app and a CLI surface every module without writing code.

All inference runs through a local **Ollama** server — no external LLM API keys required.

---

## Quick start

```bash
# 1. Install dependencies (Python 3.11+ and uv required)
uv sync

# 2. Start Ollama and pull the required models
ollama pull deepseek-r1   # text generation / reasoning
ollama pull qwen2.5       # tool-calling agent loop

# 3. (Optional) Start PostgreSQL and Weaviate
#    Needed only for DB-backed and RAG capabilities
docker compose up -d

# 4. Edit the config
cp thuon_platform/config/config.yaml thuon_platform/config/config.yaml.bak
# set your DB credentials if using PostgreSQL

# 5. Launch the web UI
uv run python thuon_platform/main.py web
# → http://localhost:5000
```

```bash
# Or use the CLI directly
uv run python thuon_platform/main.py cli research --query "AI in drug discovery"
uv run python thuon_platform/main.py cli research --query "climate policy" --depth phd
uv run python thuon_platform/main.py cli report --type market_analysis --context "EV sector 2025"
```

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                       Interfaces                          │
│   Flask Web App (:5000)          CLI (argparse)           │
└────────────────────┬──────────────────────────────────────┘
                     │
┌────────────────────▼──────────────────────────────────────┐
│               Capability Layer  (36 modules)              │
│  research_assistant · niche_finder · deep_researcher      │
│  code_writer · competitive_intel · ai_report_writer · …   │
└──────┬─────────────┬─────────────┬──────────────┬─────────┘
       │             │             │              │
┌──────▼──────┐ ┌────▼────┐ ┌─────▼────┐ ┌──────▼──────┐
│  AI Engine  │ │ Search  │ │   RAG    │ │  Database   │
│ OllamaModel │ │DuckDuck │ │ Weaviate │ │ PostgreSQL  │
│ deepseek-r1 │ │  Go     │ │   v4     │ │  psycopg2   │
│  qwen2.5   │ │ Tavily  │ └──────────┘ └─────────────┘
└──────┬──────┘ └─────────┘
       │
┌──────▼────────────────────────────────────────────────────┐
│                  Agent Loop  (ReAct)                      │
│  ChatOllama.bind_tools()                                  │
│  web_search · scrape_url · execute_python                 │
│  write_file · read_file · list_directory                  │
└───────────────────────────────────────────────────────────┘
```

**Data flow:** Interface → capability class (injected deps) → primary method → structured `dict` returned as JSON.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| [uv](https://docs.astral.sh/uv/) | latest | package manager |
| [Ollama](https://ollama.ai) | latest | local LLM server |
| PostgreSQL | 14+ | optional — DB-backed capabilities only |
| Weaviate | 1.24+ | optional — RAG capabilities only |

---

## Configuration

`thuon_platform/config/config.yaml`:

```yaml
database:
  host: localhost
  port: 5432
  dbname: thuon_db
  user: thuon_user
  password: thuon_password

ollama:
  endpoint: http://localhost:11434
  model: deepseek-r1      # text generation, reasoning
  chat_model: qwen2.5     # tool-calling agent loop

weaviate:
  url: http://localhost:8080

api_keys:
  tavily: YOUR_TAVILY_API_KEY       # optional
  google_serper: YOUR_SERPER_KEY    # optional
```

DuckDuckGo search works with no key. Tavily and Google Serper are optional upgrades for higher-quality results.

---

## Web interface

```bash
uv run python thuon_platform/main.py web [--host 0.0.0.0] [--port 5000] [--debug]
```

| Route | Method | Description |
|---|---|---|
| `/` | GET | Capability grid — search, filter by category |
| `/capability/<name>` | GET | Capability form with live result panel |
| `/api/<capability>` | POST | Call any capability (JSON in, JSON out) |
| `/api/capabilities` | GET | List all capabilities and their parameter schemas |
| `/health` | GET | Health check — Ollama, PostgreSQL, Weaviate status |

---

## CLI

```bash
uv run python thuon_platform/main.py cli <subcommand> [options]
```

| Subcommand | Key flags | Capability |
|---|---|---|
| `research` | `--query TEXT`, `--depth LEVEL` | ResearchAssistant |
| `report` | `--type STR`, `--context STR`, `--output PATH` | AIReportWriter |
| `competitive-intel` | `--industry STR`, `--competitors LIST` | CompetitiveIntelligenceOperative |
| `social-media` | `--brand STR`, `--audience STR`, `--platforms LIST` | SocialMediaManager |
| `market-research` | `--product STR`, `--region STR` | MarketSalesResearch |
| `proposal` | `--type STR`, `--client STR`, `--description STR` | ProposalCompositor |
| `cybersecurity` | `--system STR`, `--scan-type STR` | CybersecurityGuardian |

---

## Capabilities

### Research & Intelligence

| Module | Primary method | Description |
|---|---|---|
| `research_assistant` | `perform_research(query, depth)` | Web + RAG research across 7 depth levels |
| `deep_researcher` | `research(query, level)` | Standalone multi-level research engine |
| `niche_finder` | `find_niches(industry, mode, num_niches, focus_area)` | Strategic niche analysis with GTM propositions |
| `competitive_intelligence_operative` | `analyze_competitor_landscape(industry, competitors)` | Competitor landscape, positioning matrix |
| `market_sales_research` | `analyze_market_trends(product_category, region)` | Market sizing, segment analysis, forecasting |
| `ma_target_profiler` | `profile_ma_target(target_company, areas_of_interest)` | M&A target profiling |
| `psychographic_profile_generator_analyzer` | `generate_customer_psychographic_profile(segment, dimensions)` | Customer psychographic segmentation |
| `regulatory_change_manager` | `monitor_regulatory_changes(industry, jurisdictions)` | Regulatory monitoring and impact assessment |
| `brand_sentiment_orchestrator` | `analyze_brand_sentiment(brand_name, channels)` | Multi-channel sentiment analysis |
| `intellectual_property_strategist` | `conduct_patent_landscape_analysis(keywords, jurisdictions)` | Patent landscape and IP strategy |

### Content & Communications

| Module | Primary method | Description |
|---|---|---|
| `ai_report_writer` | `generate_report(report_type, context_data, output_path)` | Structured reports from templates |
| `proposal_compositor` | `compose_proposal(proposal_type, context_data, output_path)` | Business proposals |
| `internal_communications_automator` | `draft_internal_communication(type, context_data, audience)` | Memos, announcements, briefings |
| `course_creator` | `design_course_outline(topic, objectives, audience)` | Course outlines with assessments |
| `website_creator` | `generate_website_content(purpose, audience, features)` | Page-by-page website content |
| `customer_support_chatbot_builder` | `design_chatbot_flow(support_area, queries, persona)` | Intent trees and response templates |

### Analytics & Finance

| Module | Primary method | Description |
|---|---|---|
| `financial_forecasting_analyst` | `forecast_financial_performance(table, metrics, years)` | Financial forecasting from DB data |
| `financial_accountant` | `create_invoice(customer_id, items, dates)` | Invoice generation and records |
| `process_optimization_analyst` | `analyze_process_efficiency(description, table, metrics)` | Process efficiency analysis |
| `sustainability_impact_simulator` | `simulate_environmental_impact(lifecycle, categories)` | Environmental impact scoring |

### Strategy & Operations

| Module | Primary method | Description |
|---|---|---|
| `negotiation_strategy_builder` | `develop_negotiation_strategy(context, outcomes, counterparty)` | BATNA and negotiation tactics |
| `supply_chain_resilience_planner` | `assess_supply_chain_risks(description, risk_factors)` | Supply chain risk and mitigation |
| `crisis_simulation_response_architect` | `simulate_crisis_scenario(crisis_type, org_profile)` | Crisis simulation and response playbooks |
| `cultural_transformation_designer` | `design_cultural_transformation_plan(current, desired, objectives)` | Culture change roadmap |
| `workflow_automator` | `create_workflow(name, description, triggers, actions)` | Workflow automation blueprints |
| `social_media_manager` | `analyze_social_trends(keywords, platforms)` | Platform-specific social strategy |

### HR & People

| Module | Primary method | Description |
|---|---|---|
| `human_resource_manager` | `onboard_new_employee(name, title, department, start_date)` | Onboarding plans and HR records |
| `talent_analytics_succession_forecaster` | `predict_succession_candidates(role, table, criteria)` | Succession candidate prediction |
| `project_task_manager` | `create_project(name, description, team, deadline)` | Project and task breakdown |

### Risk & Compliance

| Module | Primary method | Description |
|---|---|---|
| `ethical_ai_governance_engine` | `assess_ethical_risks(system_description, guidelines)` | Ethical risk scoring for AI systems |
| `cybersecurity_guardian` | `perform_vulnerability_scan(system_description, scan_type)` | Vulnerability assessment reports |
| `legal_compliance_officer` | `review_contract_for_compliance(contract_text, standards)` | Contract review and compliance gaps |
| `accessibility_compliance_verifier` | `verify_accessibility_compliance(asset_description, standards)` | WCAG / ADA compliance checklist |

### Data & Development

| Module | Primary method | Description |
|---|---|---|
| `customer_relationship_manager` | `create_customer_profile(name, contact_details, industry)` | CRM profile creation and storage |
| `data_integrator` | `connect_to_data_source(name, type, parameters)` | Data source connection and schema mapping |
| `code_writer` | `write_and_run(task_description, language)` | Agentic code generation, execution, testing |

---

## Deep research levels

Both `research_assistant` and `deep_researcher` accept a `depth`/`level` parameter:

| Level | Strategy | Approx. time |
|---|---|---|
| `quick` | LLM prior knowledge, no search | ~2 s |
| `shallow` | Single search batch + LLM synthesis | ~10 s |
| `medium` | Agent loop, 10 iterations *(default)* | ~1 min |
| `deep` | Agent loop, 20 iterations, reads full articles | ~3 min |
| `comprehensive` | 35 iterations, multi-angle search | ~5 min |
| `academic` | Multi-phase: decompose → investigate each sub-question → cross-synthesise → critique → structured report | ~10 min |
| `phd` | Systematic review: research question formulation → scoped lit search → source evaluation → thematic analysis → gap analysis → original synthesis → thesis chapter | ~20 min |

```bash
# Via CLI
uv run python thuon_platform/main.py cli research \
  --query "long-term effects of social media on adolescent cognition" \
  --depth phd

# Via API
curl -X POST http://localhost:5000/api/deep_researcher \
  -H "Content-Type: application/json" \
  -d '{"query": "CRISPR off-target effects", "level": "academic"}'
```

---

## Niche finder

```bash
# Quick mode — LLM prior knowledge (~5 s)
curl -X POST http://localhost:5000/api/niche_finder \
  -H "Content-Type: application/json" \
  -d '{"industry": "proptech", "mode": "quick", "num_niches": 3}'

# Research mode — agentic search + synthesis (~10 min)
curl -X POST http://localhost:5000/api/niche_finder \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "healthtech",
    "mode": "research",
    "focus_area": "remote patient monitoring",
    "num_niches": 2
  }'
```

Each niche proposition contains: hypothesis, target segment, job-to-be-done, differentiator, revenue model, pricing logic, market size estimate, competitive moat, unit economics note, risks with mitigations, and a step-by-step GTM path.

---

## Testing

```bash
# All CI tests (no live services required)
uv run pytest tests/ci/ -q

# Single file
uv run pytest tests/ci/test_deep_researcher.py -v

# Type checking
uv run pyright
```

All tests mock Ollama, PostgreSQL, and Weaviate — the CI suite runs entirely offline.

---

## License

MIT

---

## Contact

Built by **Datacraft** · nyimbi@gmail.com

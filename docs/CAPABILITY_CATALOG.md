# Thuon Platform — Capability Catalog

36 capabilities across 9 categories. Each entry covers: what it does, dependencies, parameters, full output schema, and a usage example.

All capabilities are accessible via:
- **Web UI:** `http://localhost:5000/capability/<name>`
- **REST API:** `POST http://localhost:5000/api/<name>` (JSON body)
- **Python:** instantiate the class directly with injected deps

---

## How to read this catalog

**Parameters table columns:**
- *Name* — parameter name in the JSON request body / Python call
- *Type* — `str`, `int`, `list`, `dict`, `bool`
- *Required* — whether it must be supplied
- *Default* — value used when omitted

**Output schema** lists every top-level key the LLM is asked to produce. Keys marked `(list)` are JSON arrays; `(dict)` are nested objects. Actual content depends on the LLM response — all capabilities fall back to `{"result": "<raw text>", "status": "success"}` if JSON parsing fails.

---

## Categories

| Category | Web UI filter | Capabilities |
|---|---|---|
| [Research & Intelligence](#research--intelligence) | `research` | research_assistant, competitive_intelligence_operative, market_sales_research, ma_target_profiler, psychographic_profile_generator_analyzer, regulatory_change_manager, brand_sentiment_orchestrator, intellectual_property_strategist |
| [Content & Communications](#content--communications) | `content` | ai_report_writer, proposal_compositor, internal_communications_automator, course_creator, website_creator, customer_support_chatbot_builder |
| [Analytics & Finance](#analytics--finance) | `analytics` | financial_forecasting_analyst, financial_accountant, process_optimization_analyst, sustainability_impact_simulator |
| [Strategy & Operations](#strategy--operations) | `strategy` | negotiation_strategy_builder, supply_chain_resilience_planner, crisis_simulation_response_architect, cultural_transformation_designer, workflow_automator, social_media_manager, brand_sentiment_orchestrator, intellectual_property_strategist, niche_finder |
| [HR & People](#hr--people) | `hr` | human_resource_manager, talent_analytics_succession_forecaster, project_task_manager, cultural_transformation_designer |
| [Risk & Compliance](#risk--compliance) | `risk` | ethical_ai_governance_engine, cybersecurity_guardian, legal_compliance_officer, accessibility_compliance_verifier, crisis_simulation_response_architect, regulatory_change_manager |
| [Data](#data) | `data` | customer_relationship_manager, data_integrator |
| [Dev](#dev) | `dev` | code_writer, deep_researcher, niche_finder |

---

## Research & Intelligence

---

### `research_assistant`

Performs multi-depth research combining web search, RAG retrieval, and a ReAct agent loop. The depth parameter controls the strategy used — from a quick LLM answer to a PhD-quality systematic review.

**Dependencies:** `ai_engine`, `search_engine`, `rag_engine` (optional), `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default | Notes |
|---|---|---|---|---|
| `research_query` | str | yes | — | The question or topic to research |
| `sources` | list | no | `['web','knowledge_graph']` | Hint only — actual sources depend on depth |
| `depth` | str | no | `'medium'` | See depth table below |

**Depth levels:**

| `depth` | Strategy | Time |
|---|---|---|
| `quick` | LLM prior knowledge, no search | ~2 s |
| `shallow` | Single search batch + synthesis | ~10 s |
| `medium` | Agent loop, 10 iterations | ~1 min |
| `deep` | Agent loop, 20 iterations, reads full articles | ~3 min |
| `comprehensive` | 35 iterations, multi-angle search | ~5 min |
| `academic` | Decompose → investigate sub-questions → cross-synthesise → critique → report | ~10 min |
| `phd` | Full systematic review → thesis chapter structure | ~20 min |

**Output schema (shallow depth):**

| Key | Type | Description |
|---|---|---|
| `summary` | str | Narrative synthesis of findings |
| `key_findings` | list | Bullet-level findings |
| `data_points` | list | Quantitative facts extracted |
| `sources_used` | list | URLs / source names referenced |
| `confidence_level` | str | `high` / `medium` / `low` |
| `recommendations` | list | Actionable next steps |
| `query` | str | Echo of input query |
| `depth` | str | Echo of depth used |
| `web_results_count` | int | Number of search results gathered |

For `medium`/`deep` depths the output mirrors the agent loop result — see `deep_researcher` for `academic`/`phd` schemas.

**Example:**
```bash
curl -X POST http://localhost:5000/api/research_assistant \
  -H "Content-Type: application/json" \
  -d '{"research_query": "impact of LLMs on legal research", "depth": "deep"}'
```

---

### `deep_researcher`

Standalone multi-level research engine. Identical depth scale to `research_assistant` but exposes the full multi-phase orchestration directly, including per-phase intermediate results.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `query` | str | yes | — |
| `level` | str | no | `'medium'` |

**Output schema — quick:**

| Key | Type | Description |
|---|---|---|
| `summary` | str | Answer from LLM prior knowledge |
| `key_points` | list | Core takeaways |
| `confidence_level` | str | `high` / `medium` / `low` |
| `caveats` | list | Limitations of LLM-only answer |
| `suggested_followup_questions` | list | Directions for deeper research |

**Output schema — shallow:**

| Key | Type | Description |
|---|---|---|
| `summary` | str | Synthesis of search results |
| `key_findings` | list | Key findings from sources |
| `sources` | list | `{title, url, relevance}` per source |
| `confidence_level` | str | |
| `knowledge_gaps` | list | What the search didn't answer |
| `recommendations` | list | |
| `sources_searched` | int | Number of results gathered |

**Output schema — academic:**

| Key | Type | Description |
|---|---|---|
| `abstract` | str | 200-word research abstract |
| `introduction` | str | Context and motivation |
| `literature_review` | str | What the field says |
| `analysis` | str | Synthesis and interpretation |
| `discussion` | str | Implications |
| `conclusion` | str | Summary and outlook |
| `key_citations` | list | URLs found during research |
| `confidence_level` | str | |
| `research_quality_score` | int | 1–10 self-assessment |
| `phases` | dict | Intermediate: `decomposition`, `investigations`, `syntheses`, `integration`, `critique` |

**Output schema — phd:**

| Key | Type | Description |
|---|---|---|
| `title` | str | Chapter title |
| `abstract` | str | 250-word abstract |
| `introduction` | str | ~600 words: background, motivation, structure |
| `theoretical_framework` | str | ~300 words |
| `literature_review` | str | ~1500 words organised by themes |
| `critical_analysis` | str | ~600 words: contradictions, evidence quality |
| `synthesis` | str | ~600 words: original analytical perspective |
| `research_gaps_and_future_directions` | str | ~400 words |
| `conclusion` | str | ~300 words |
| `references` | list | URLs as placeholder citations |
| `word_count_estimate` | int | |
| `academic_quality_score` | int | 1–10 |
| `limitations` | dict | Peer-reviewer-style critique |
| `phases` | dict | All 10 intermediate phase results |

---

### `niche_finder`

Maps a competitive landscape, identifies underserved user needs and product-market gaps, evaluates commercial viability, and synthesises 1–5 concrete niche propositions — each with a GTM path.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default | Notes |
|---|---|---|---|---|
| `industry` | str | yes | — | e.g. `'fintech'`, `'healthtech'`, `'proptech'` |
| `mode` | str | no | `'research'` | `'quick'` (LLM only, ~5 s) or `'research'` (agentic, ~10 min) |
| `num_niches` | int | no | `3` | Clamped to 1–5 |
| `focus_area` | str | no | `''` | Optional sub-domain constraint, e.g. `'SME lending'` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `landscape_summary` | str | 2–3 sentence competitive overview |
| `key_gaps` | list | Top product-market gaps identified |
| `niches` | list | See niche proposition schema below |
| `methodology_note` | str | How the analysis was conducted |
| `confidence_level` | str | `high` / `medium` / `low` with reasoning |
| `phases` | dict | Research mode only — intermediate phase results |

**Each niche proposition:**

| Key | Description |
|---|---|
| `hypothesis` | One-line value proposition |
| `target_segment` | Precisely who |
| `jtbd` | Underserved job-to-be-done |
| `differentiator` | Vs. incumbents and alternatives |
| `revenue_model` | SaaS / marketplace / usage / services |
| `pricing_logic` | Initial price, rationale, competitive anchors |
| `market_size_estimate` | TAM → SAM → SOM reasoning |
| `competitive_moat` | Why it's hard to replicate |
| `unit_economics_note` | CAC, LTV, payback period intuition |
| `risks` | list of `{risk, mitigation}` |
| `gtm_path` | Step-by-step: first 10 customers → first $1M ARR |

**Example:**
```bash
curl -X POST http://localhost:5000/api/niche_finder \
  -H "Content-Type: application/json" \
  -d '{"industry": "proptech", "mode": "research", "focus_area": "property management", "num_niches": 2}'
```

---

### `competitive_intelligence_operative`

Profiles up to 5 competitors across chosen dimensions using live web search, then produces a comparative landscape analysis with strategic recommendations.

**Dependencies:** `ai_engine`, `search_engine`, `rag_engine` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `industry` | str | yes | — |
| `competitors` | list | yes | — |
| `analysis_dimensions` | list | no | `['product','pricing','marketing']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `competitors` | dict | Per-competitor profile keyed by name |
| `landscape_summary` | str | Overall market narrative |
| `market_dynamics` | str | Forces shaping competition |
| `strategic_threats` | list | Threats from the competitor set |
| `opportunities` | list | Gaps the requester could exploit |
| `recommendations` | list | Actionable strategic moves |
| `areas_analyzed` | list | Echo of `analysis_dimensions` |

---

### `market_sales_research`

Delivers market sizing, customer segmentation, competitive landscape, and sales intelligence for a product category and region.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `product_category` | str | yes | — |
| `region` | str | yes | — |
| `metrics` | list | no | `['market_size','growth_rate','customer_segments']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `market_overview` | str | Narrative summary |
| `market_size` | dict | `{value, unit, year}` |
| `growth_rate` | str | CAGR % |
| `market_size_forecast_5yr` | str | |
| `customer_segments` | list | `{segment_name, size_percentage, key_needs, buying_behavior}` |
| `competitive_landscape` | list | Players with `market_share` |
| `key_trends` | list | |
| `opportunities` | list | |
| `threats` | list | |
| `entry_barriers` | list | |
| `sales_channels` | list | |
| `pricing_insights` | str | |
| `recommendations` | list | |

---

### `ma_target_profiler`

Profiles an M&A acquisition target across financials, market position, technology stack, and culture fit, then delivers a deal recommendation.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `target_company` | str | yes | — |
| `acquirer_profile` | str | yes | — |
| `areas_of_interest` | list | no | `['financials','technology','market_position']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `company_name` | str | |
| `executive_summary` | str | |
| `financials` | dict | `{revenue, profitability, debt_level, valuation_estimate}` |
| `market_position` | dict | `{market_share, competitive_advantages, customer_base}` |
| `technology_stack` | dict | `{key_technologies, ip_assets, tech_debt_risk}` |
| `culture_fit` | dict | `{values, management_style, integration_risk}` |
| `synergy_opportunities` | list | |
| `risk_factors` | list | |
| `acquisition_recommendation` | str | |
| `estimated_deal_value` | str | |

---

### `psychographic_profile_generator_analyzer`

Builds a deep psychographic profile for a customer segment across chosen dimensions, including persona archetypes, messaging recommendations, and product feature priorities.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `target_segment_description` | str | yes | — |
| `profile_dimensions` | list | no | `['values','interests','lifestyle','personality']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `segment_name` | str | |
| `segment_summary` | str | |
| `psychographic_profile` | dict | One key per dimension |
| `motivators` | list | |
| `pain_points` | list | |
| `decision_making_style` | str | |
| `brand_affinities` | list | |
| `media_consumption_habits` | list | |
| `messaging_recommendations` | list | |
| `product_feature_priorities` | list | |
| `persona_name` | str | Fictional name for the archetype |
| `persona_quote` | str | Representative voice-of-customer quote |

---

### `regulatory_change_manager`

Monitors regulatory news for an industry and jurisdiction, assesses business impact, and surfaces compliance deadlines and required actions.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `industry_sector` | str | yes | — |
| `jurisdictions` | list | no | `['US','EU']` |
| `regulation_types` | list | no | `['data_privacy','financial','environmental']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `regulatory_summary` | str | Overview of the regulatory environment |
| `recent_changes` | list | `{regulation_name, effective_date, impact_level, description, required_actions}` |
| `compliance_deadlines` | list | |
| `risk_areas` | list | |
| `recommended_actions` | list | |
| `monitoring_frequency` | str | Suggested review cadence |

---

### `brand_sentiment_orchestrator`

Analyses brand perception across channels, scores overall sentiment, surfaces trending topics and reputation risks, and generates strategy recommendations.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `brand_name` | str | yes | — |
| `analysis_channels` | list | no | `['news','social_media','reviews']` |
| `time_period_days` | int | no | `30` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `brand_name` | str | |
| `overall_sentiment` | str | `positive` / `negative` / `neutral` / `mixed` |
| `sentiment_score` | float | –1.0 to 1.0 |
| `source_breakdown` | dict | Per channel: `{sentiment, key_themes, representative_mentions}` |
| `trending_topics` | list | |
| `brand_strengths` | list | |
| `brand_weaknesses` | list | |
| `recommendations` | list | |
| `monitoring_keywords` | list | |

---

### `intellectual_property_strategist`

Conducts a patent landscape analysis across jurisdictions, identifies white spaces, assesses freedom-to-operate, and recommends IP strategy.

**Dependencies:** `ai_engine`, `search_engine`, `rag_engine` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `technology_domain` | str | yes | — |
| `company_focus` | str | yes | — |
| `analysis_scope` | list | no | `['filing_trends','key_players','white_spaces']` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `technology_area` | str | |
| `landscape_summary` | str | |
| `key_patent_holders` | list | |
| `patent_trends` | list | Filing volume, jurisdictions, technology vectors |
| `white_spaces` | list | Unprotected areas with opportunity |
| `jurisdiction_analysis` | dict | Per jurisdiction: `{activity_level, key_players, notable_patents}` |
| `competitive_threats` | list | |
| `ip_opportunities` | list | |
| `strategic_recommendations` | list | |
| `freedom_to_operate_assessment` | str | |

---

## Content & Communications

---

### `ai_report_writer`

Generates a structured business report document (`.docx` or `.md`) from contextual data and a named template. Returns `true`/`false`.

**Dependencies:** `ai_engine`, `template_manager`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `report_type` | str | yes | — | e.g. `'executive_report'`, `'market_analysis_report'`, `'technical_report'` |
| `context_data` | str | yes | — | Background information the report should incorporate |
| `output_path` | str | no | `'ai_report.docx'` | File path to write |

**Available report types:** `executive_report`, `technical_report`, `market_analysis_report`, `business_proposal`, `project_proposal`, `internal_memo`, `announcement`, `course_outline`

**LLM-generated content keys** (merged into template):

| Key | Description |
|---|---|
| `title` | Report title |
| `executive_summary` | |
| `key_findings` | |
| `recommendations` | |
| `conclusion` | |
| `market_overview`, `market_size`, `customer_segments`, `competitive_landscape`, `opportunities_threats` | Market reports |
| `overview`, `methodology`, `analysis`, `results` | Technical reports |

**Returns:** `bool` — `true` if the file was written successfully.

**Example:**
```bash
curl -X POST http://localhost:5000/api/ai_report_writer \
  -H "Content-Type: application/json" \
  -d '{"report_type": "market_analysis_report", "context_data": "EV battery market in Southeast Asia 2025", "output_path": "/tmp/ev_report.docx"}'
```

---

### `proposal_compositor`

Composes a professional business proposal document from contextual data. Supports service proposals, partnership proposals, grant proposals, and project proposals.

**Dependencies:** `ai_engine`, `template_manager`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `proposal_type` | str | yes | — | `'service'`, `'partnership'`, `'grant'`, `'project'` |
| `client_name` | str | yes | — | |
| `project_description` | str | yes | — | |
| `budget_range` | str | no | `'TBD'` | |

**LLM-generated content keys:**

| Key | Description |
|---|---|
| `proposal_title` | |
| `executive_summary` | |
| `problem_statement` | |
| `proposed_solution` | |
| `scope_of_work` | |
| `timeline` | |
| `investment` | Budget/pricing section |
| `why_us` | Differentiators |
| `next_steps` | |
| `project_name`, `project_lead`, `objectives`, `deliverables`, `resources`, `risks`, `budget` | Project proposals |

**Returns:** `bool`

---

### `internal_communications_automator`

Drafts internal communications (memos, announcements, briefings) and writes them to a document file.

**Dependencies:** `ai_engine`, `template_manager`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `communication_type` | str | yes | — | `'memo'`, `'announcement'`, `'briefing'`, `'newsletter'` |
| `key_message` | str | yes | — | Core message to communicate |
| `target_audience` | str | yes | — | e.g. `'all staff'`, `'engineering team'` |
| `tone` | str | no | `'professional'` | `'professional'`, `'casual'`, `'urgent'` |

**LLM-generated content keys:**

| Key | Description |
|---|---|
| `subject` | |
| `to` | Recipient |
| `from_name` | Sender |
| `body` | Full communication body |
| `headline` | Announcement headline |
| `key_messages` | list — bullet points |
| `call_to_action` | |
| `follow_up_date` | |

**Returns:** `bool`

---

### `course_creator`

Designs a complete course outline with module breakdown, learning activities, and assessment strategy.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `course_topic` | str | yes | — | |
| `target_audience` | str | yes | — | |
| `course_duration_hours` | int | no | `10` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `course_title` | str | |
| `description` | str | |
| `prerequisites` | list | |
| `modules` | list | `{module_number, title, duration_hours, topics, activities, assessment_type}` |
| `total_duration_hours` | int | |
| `assessment_strategy` | str | |
| `resources` | list | |
| `certification_criteria` | str | |

---

### `website_creator`

Generates complete website copy and information architecture for every page, including SEO keywords, conversion goals, and design direction.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `website_purpose` | str | yes | — | |
| `target_audience` | str | yes | — | |
| `key_features` | list | no | `['homepage','about_us','contact_form','product_catalog']` | Page list |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `site_name_suggestion` | str | |
| `tagline` | str | |
| `value_proposition` | str | |
| `pages` | dict | Per page: `{headline, subheadline, body_content, call_to_action, seo_keywords}` |
| `navigation_structure` | list | |
| `tone_and_voice` | str | |
| `color_palette_suggestion` | str | |
| `typography_suggestion` | str | |
| `social_proof_elements` | list | |
| `trust_signals` | list | |
| `conversion_goals` | list | |

---

### `customer_support_chatbot_builder`

Designs a full chatbot interaction system: intents, conversation flows, escalation logic, fallback responses, and integration requirements.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `support_area` | str | yes | — | e.g. `'e-commerce returns'`, `'SaaS billing'` |
| `common_customer_queries` | list | yes | — | Top questions the bot should handle |
| `desired_chatbot_persona` | str | yes | — | e.g. `'friendly and efficient'` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `chatbot_name` | str | |
| `persona_description` | str | |
| `intents` | list | `{intent_name, example_utterances, response_template, follow_up_actions}` |
| `conversation_flows` | list | `{trigger, steps: [{message, user_options}]}` |
| `escalation_triggers` | list | Conditions that route to a human |
| `handoff_to_human_criteria` | list | |
| `fallback_responses` | list | Responses when intent is unrecognised |
| `success_metrics` | list | KPIs for measuring chatbot performance |
| `integration_requirements` | list | APIs / systems the bot needs access to |
| `training_data_recommendations` | str | |

---

## Analytics & Finance

---

### `financial_forecasting_analyst`

Loads historical financial data from a PostgreSQL table and produces multi-year forecasts with scenario analysis.

**Dependencies:** `ai_engine`, `db_handler` (optional — uses LLM knowledge if unavailable)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `financial_data_table` | str | yes | — | PostgreSQL table name |
| `forecast_metrics` | list | no | `['revenue_forecast','profit_margin_forecast','cash_flow_forecast']` | |
| `forecast_period_years` | int | no | `5` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `forecast_summary` | str | Narrative overview |
| `assumptions` | list | Key forecasting assumptions |
| `forecasts` | dict | Per metric: `{year_1…year_5, growth_rate, confidence_interval}` |
| `scenario_analysis` | dict | `{optimistic, base, pessimistic}` |
| `key_drivers` | list | Factors driving the forecast |
| `risks_to_forecast` | list | What could make it wrong |
| `recommended_actions` | list | |
| `break_even_analysis` | str | |
| `cash_runway_months` | int | |

---

### `financial_accountant`

Generates a complete structured invoice with line items, tax calculations, payment terms, and accounting codes. Optionally persists to a PostgreSQL `invoices` table.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `customer_id` | str | yes | — | |
| `invoice_items` | list | yes | — | Each item: `{description, quantity, unit_price}` |
| `invoice_date` | str | yes | — | ISO date string |
| `due_date` | str | yes | — | ISO date string |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `invoice_number` | str | Generated invoice ID |
| `customer_id` | str | |
| `invoice_date` | str | |
| `due_date` | str | |
| `line_items` | list | `{description, quantity, unit_price, tax_rate, line_total}` |
| `subtotal` | float | |
| `tax_amount` | float | |
| `discount_amount` | float | |
| `total_amount` | float | |
| `currency` | str | |
| `payment_terms` | str | |
| `payment_methods_accepted` | list | |
| `late_payment_penalty_percent` | float | |
| `accounting_codes` | list | `{code, amount, description}` |
| `notes` | str | |
| `status` | str | `draft` / `issued` |

---

### `process_optimization_analyst`

Analyses a business process using Lean/Six Sigma framing. Loads process metrics from a DB table, identifies bottlenecks and waste, and produces a prioritised improvement roadmap.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `process_description` | str | yes | — | Narrative description of the process |
| `process_data_table` | str | yes | — | PostgreSQL table with metrics |
| `efficiency_metrics` | list | no | `['cycle_time','resource_utilization','error_rate']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `process_summary` | str | |
| `current_performance` | dict | Per metric: `{current_value, benchmark, gap}` |
| `bottlenecks` | list | `{step, issue, impact}` |
| `waste_identified` | list | `{waste_type, description, estimated_cost}` |
| `root_causes` | list | |
| `improvement_opportunities` | list | `{opportunity, methodology, estimated_improvement, implementation_effort, priority}` |
| `quick_wins` | list | High-impact, low-effort actions |
| `implementation_roadmap` | list | Phased rollout plan |
| `estimated_efficiency_gain_percent` | float | |
| `roi_estimate` | str | |

---

### `sustainability_impact_simulator`

Simulates environmental impact across a product lifecycle, scores sustainability performance, and produces a net-zero pathway.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `product_lifecycle_description` | str | yes | — | Raw materials → manufacturing → distribution → use → end-of-life |
| `impact_categories` | list | no | `['carbon_footprint','water_usage','waste_generation','resource_depletion']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `product_summary` | str | |
| `impact_assessment` | dict | Per category: `{estimated_value, unit, severity, comparison_to_industry_average, reduction_potential}` |
| `overall_sustainability_score` | int | 1–100 |
| `lifecycle_hotspots` | list | Stages with highest impact |
| `improvement_opportunities` | list | `{action, estimated_reduction_percent, implementation_cost}` |
| `regulatory_compliance` | list | Relevant standards (ISO 14001, GHG Protocol, etc.) |
| `certification_eligibility` | list | Certifications the product could qualify for |
| `net_zero_pathway` | str | Roadmap to carbon neutrality |

---

## Strategy & Operations

---

### `negotiation_strategy_builder`

Develops a comprehensive negotiation playbook: BATNA, opening/target/walk-away positions, concessions, anticipated objections, and psychological tactics.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `negotiation_context` | str | yes | — | What is being negotiated and why |
| `desired_outcomes` | list | yes | — | Priority-ordered list of goals |
| `counterparty_profile` | str | yes | — | Who you're negotiating with |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `strategy_summary` | str | |
| `opening_position` | str | Initial ask |
| `target_position` | str | Ideal outcome |
| `walk_away_point` | str | BATNA |
| `key_arguments` | list | |
| `concessions_to_offer` | list | `{concession, value_to_us, value_to_them}` |
| `anticipated_objections` | list | `{objection, counter_response}` |
| `negotiation_tactics` | list | |
| `red_lines` | list | Non-negotiables |
| `psychological_insights` | str | |
| `success_metrics` | list | |

---

### `supply_chain_resilience_planner`

Assesses supply chain risk across user-specified factors, produces a risk matrix with scores and mitigations, and recommends diversification opportunities.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `supply_chain_description` | str | yes | — | |
| `risk_factors` | list | no | `['geopolitical_instability','natural_disasters','supplier_financial_health']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `supply_chain_summary` | str | |
| `risk_assessment` | list | `{risk_factor, likelihood, impact, risk_score (1-10), description, mitigation_strategies}` |
| `overall_resilience_score` | int | 1–10 |
| `critical_vulnerabilities` | list | |
| `recommended_actions` | list | Ordered by priority |
| `diversification_opportunities` | list | |
| `monitoring_indicators` | list | KPIs to track |

---

### `crisis_simulation_response_architect`

Simulates a specified crisis scenario against an organisation profile, assesses multi-dimensional impact, and produces a phased response playbook.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `crisis_type` | str | yes | — | e.g. `'cyberattack'`, `'supply disruption'`, `'executive misconduct'` |
| `organization_description` | str | yes | — | Size, industry, structure |
| `severity_level` | str | no | `'high'` | `'low'` / `'medium'` / `'high'` / `'critical'` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `scenario_description` | str | Simulated crisis narrative |
| `impact_assessment` | dict | `{financial_impact, operational_impact, reputational_impact, severity_level}` |
| `response_phases` | list | `{phase, timeframe, actions, responsible_parties}` |
| `communication_plan` | str | Internal and external messaging strategy |
| `resource_requirements` | list | |
| `recovery_timeline` | str | |
| `lessons_learned` | list | Post-incident takeaways |
| `prevention_measures` | list | |

---

### `cultural_transformation_designer`

Designs an organisation-wide culture change programme: gap analysis, transformation phases, leadership actions, change agent strategy, and KPI framework.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `current_culture_description` | str | yes | — | How culture is today |
| `desired_culture_description` | str | yes | — | Target state |
| `change_objectives` | list | no | `['improved_collaboration','increased_innovation','enhanced_customer_centricity']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `transformation_vision` | str | |
| `gap_analysis` | list | Current vs. desired deltas |
| `transformation_phases` | list | `{phase_name, duration, key_initiatives, success_metrics, change_agents}` |
| `leadership_actions` | list | What leaders must do differently |
| `employee_engagement_strategies` | list | |
| `resistance_management` | list | How to handle pushback |
| `measurement_framework` | list | KPIs and measurement cadence |
| `timeline_months` | int | |
| `estimated_roi` | str | |
| `risks` | list | |

---

### `workflow_automator`

Produces a complete workflow specification with trigger conditions, step-by-step logic, decision branching, data mappings, error handling, and monitoring alerts.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `workflow_name` | str | yes | — | |
| `description` | str | yes | — | What the workflow should accomplish |
| `triggers` | list | yes | — | Events that start the workflow |
| `actions` | list | yes | — | Operations the workflow performs |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `workflow_id` | str | Slug identifier |
| `workflow_name` | str | |
| `trigger_conditions` | list | `{trigger_type, condition, data_inputs}` |
| `workflow_steps` | list | `{step_number, step_name, action_type, input_mapping, output_mapping, error_handling, retry_policy}` |
| `decision_nodes` | list | `{condition, true_branch, false_branch}` |
| `data_flow` | str | How data moves through the workflow |
| `integration_requirements` | list | External systems needed |
| `monitoring_alerts` | list | Conditions that trigger notifications |
| `estimated_time_saved_hours_per_month` | float | |
| `implementation_notes` | list | |

---

### `social_media_manager`

Analyses social trends across platforms for given keywords, delivers platform-by-platform content recommendations, trending hashtags, and a posting schedule.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `brand_name` | str | yes | — | |
| `target_audience` | str | yes | — | |
| `platforms` | list | no | `['Twitter','LinkedIn','Instagram']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `trend_summary` | str | |
| `platform_breakdown` | dict | Per platform: `{sentiment, top_topics, engagement_level, recommended_content_types}` |
| `trending_hashtags` | list | |
| `audience_insights` | str | |
| `content_recommendations` | list | |
| `posting_schedule` | str | |

---

## HR & People

---

### `human_resource_manager`

Creates a comprehensive onboarding plan and optionally persists the employee record to a PostgreSQL `employees` table.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `employee_name` | str | yes | — | |
| `job_title` | str | yes | — | |
| `department` | str | yes | — | |
| `start_date` | str | yes | — | ISO date |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `employee_id` | str | Generated slug |
| `employee_name` | str | |
| `job_title` | str | |
| `department` | str | |
| `start_date` | str | |
| `onboarding_schedule` | list | `{day, week, activities, responsible_party}` |
| `required_training` | list | `{course_name, duration_hours, deadline, mandatory}` |
| `systems_access_needed` | list | `{system, access_level, request_date}` |
| `equipment_checklist` | list | |
| `buddy_program_suggestions` | str | |
| `30_60_90_day_goals` | dict | `{day_30, day_60, day_90}` each a list of goals |
| `key_contacts` | list | `{name, role, contact_purpose}` |
| `compliance_requirements` | list | |
| `onboarding_completion_criteria` | list | |

---

### `talent_analytics_succession_forecaster`

Loads employee data from a PostgreSQL table, ranks succession candidates for a given role, and produces development recommendations.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `role_title` | str | yes | — | Role to plan succession for |
| `employee_data_table` | str | no | `'employees'` | PostgreSQL table name |
| `assessment_criteria` | list | no | `['performance_ratings','skill_scores','leadership_potential']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `role` | str | |
| `top_candidates` | list | `{name/id, readiness_level, strengths, development_gaps, estimated_readiness_date, overall_score}` |
| `talent_pipeline_health` | str | |
| `critical_gaps` | list | Skills missing from the pipeline |
| `development_recommendations` | list | |
| `succession_risk_level` | str | `low` / `medium` / `high` / `critical` |

---

### `project_task_manager`

Creates a full project plan with WBS, task dependencies, risk register, and communication plan. Optionally persists to a PostgreSQL `projects` table.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `project_name` | str | yes | — | |
| `description` | str | yes | — | |
| `team_members` | list | yes | — | Names or `{name, role}` objects |
| `deadline` | str | yes | — | ISO date |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `project_id` | str | Generated slug |
| `project_name` | str | |
| `description` | str | |
| `team_members` | list | `{name, role, responsibilities}` |
| `milestones` | list | `{name, due_date, deliverables, owner}` |
| `tasks` | list | `{task_id, name, description, assignee, priority, estimated_hours, dependencies, status}` |
| `risks` | list | `{risk, probability, impact, mitigation}` |
| `communication_plan` | dict | `{meeting_cadence, reporting_format, escalation_path}` |
| `success_criteria` | list | |
| `estimated_total_hours` | int | |
| `project_health_indicators` | list | |

---

## Risk & Compliance

---

### `ethical_ai_governance_engine`

Evaluates an AI system description against ethical guidelines and produces a risk assessment with mitigation steps per guideline.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `ai_system_description` | str | yes | — | What the AI system does |
| `ethical_guidelines` | list | no | `['fairness','transparency','privacy','accountability']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `overall_risk_level` | str | `low` / `medium` / `high` / `critical` |
| `guideline_assessments` | dict | Per guideline: `{risk_level, findings, mitigation_steps}` |
| `key_concerns` | list | |
| `recommended_safeguards` | list | |
| `compliance_status` | str | Summary compliance verdict |

---

### `cybersecurity_guardian`

Researches current threat intelligence and CVE data, then produces a vulnerability assessment for a described system.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `system_description` | str | yes | — | Architecture, stack, exposure |
| `scan_type` | str | no | `'quick'` | `'quick'` / `'comprehensive'` |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `scan_summary` | str | |
| `risk_score` | float | 0–10 |
| `vulnerabilities` | list | `{cve_id, name, severity, description, affected_component, exploitation_likelihood, remediation, patch_available}` |
| `attack_surface_analysis` | list | Exposed entry points |
| `compliance_gaps` | list | `{standard, gap, remediation}` |
| `immediate_actions` | list | Fix within 24–48 hours |
| `security_hardening_recommendations` | list | |
| `monitoring_recommendations` | list | |
| `estimated_remediation_time_days` | int | |

---

### `legal_compliance_officer`

Reviews contract text against compliance standards (GDPR, CCPA, HIPAA, etc.), identifies gaps and problematic clauses, and recommends changes.

**Dependencies:** `ai_engine`, `search_engine`, `rag_engine` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `contract_text` | str | yes | — | Full contract text (truncated to 3000 chars for LLM) |
| `compliance_standards` | list | no | `['GDPR','CCPA','HIPAA']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `overall_compliance_score` | int | 0–100 |
| `standards_analysis` | dict | Per standard: `{compliant, score, gaps: [{clause, issue, severity, recommendation}]}` |
| `risk_areas` | list | `{area, risk_level, description}` |
| `missing_clauses` | list | `{clause_name, why_required, suggested_language}` |
| `problematic_clauses` | list | `{clause_excerpt, issue, recommendation}` |
| `recommended_changes` | list | |
| `legal_risk_rating` | str | `low` / `medium` / `high` / `critical` |
| `requires_legal_counsel` | bool | |
| `summary` | str | |

---

### `accessibility_compliance_verifier`

Evaluates a digital asset description against accessibility standards (WCAG, Section 508, ADA), produces a violation list ordered by severity, and generates a remediation roadmap.

**Dependencies:** `ai_engine`, `search_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `digital_asset_description` | str | yes | — | What the asset is and how it works |
| `compliance_standards` | list | no | `['WCAG','Section508','ADA']` | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `overall_compliance_score` | int | 0–100 |
| `standards_compliance` | dict | Per standard: `{score, status, violations: [{criterion, description, severity, remediation}]}` |
| `priority_violations` | list | Top 5 by severity |
| `quick_fixes` | list | Lowest effort, highest impact |
| `estimated_remediation_effort` | int | Days |
| `recommended_tools` | list | Axe, Lighthouse, NVDA, etc. |
| `compliance_roadmap` | list | Phased remediation plan |
| `legal_risk_level` | str | |

---

## Data & Development

---

### `customer_relationship_manager`

Creates an enriched CRM profile for a customer, generates relationship health scores and upsell opportunities, and optionally persists to a PostgreSQL `customers` table.

**Dependencies:** `ai_engine`, `db_handler` (optional)

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `customer_name` | str | yes | — | |
| `contact_details` | dict | yes | — | `{email, phone, address, …}` |
| `industry` | str | yes | — | |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `customer_id` | str | Generated slug |
| `customer_name` | str | |
| `industry` | str | |
| `contact_details` | dict | |
| `company_size_estimate` | str | |
| `decision_making_process` | str | |
| `key_pain_points` | list | |
| `buying_signals` | list | |
| `relationship_stage` | str | `prospect` / `active` / `at-risk` / `champion` |
| `recommended_next_actions` | list | |
| `communication_preferences` | str | |
| `account_health_score` | int | 0–100 |
| `upsell_opportunities` | list | |

---

### `data_integrator`

Designs a data integration plan for a given source — schema discovery, data quality assessment, transformation recommendations, and sync strategy. Does not make live connections.

**Dependencies:** `ai_engine`

**Parameters:**

| Name | Type | Required | Default |
|---|---|---|---|
| `source_name` | str | yes | — | |
| `source_type` | str | yes | — | `'postgresql'`, `'mysql'`, `'rest_api'`, `'csv'`, `'s3'`, `'mongodb'` |
| `connection_parameters` | dict | yes | — | Credentials and endpoint info (passwords are stripped before processing) |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `connection_id` | str | Generated slug |
| `source_name` | str | |
| `source_type` | str | |
| `connection_status` | str | Simulated: `connected` / `failed` |
| `schema_discovery` | list | `{name, fields, record_count_estimate}` |
| `data_quality_assessment` | list | `{field, quality_score, issues}` |
| `recommended_transformations` | list | |
| `sync_strategy` | str | `full` / `incremental` / `streaming` |
| `estimated_data_volume_gb` | float | |
| `integration_pipeline_steps` | list | |
| `monitoring_metrics` | list | |
| `error_handling_strategy` | str | |

> **Security note:** `connection_parameters` values containing `password`, `secret`, `key`, or `token` are stripped before the dict is passed to the LLM.

---

### `code_writer`

Uses a ReAct agent loop (write → execute → observe → fix) to produce working code for any task. Also provides standalone explanation, review, and test-generation methods.

**Dependencies:** `ai_engine`

**Primary method — `write_and_run`:**

| Name | Type | Required | Default |
|---|---|---|---|
| `task_description` | str | yes | — | What the code should do |
| `language` | str | no | `'python'` | |
| `output_file` | str | no | `''` | Path to write the final code file |

**Output schema:**

| Key | Type | Description |
|---|---|---|
| `answer` | str | Final agent response |
| `code` | str | Extracted code block |
| `output` | str | Execution output |
| `iterations` | int | Agent loop iterations used |
| `tool_calls` | list | `{tool, args, result_preview}` per call |
| `status` | str | `success` / `max_iterations_reached` |
| `task` | str | Echo of `task_description` |

**Additional methods:**

| Method | Parameters | Description |
|---|---|---|
| `explain_code(code, detail_level='medium')` | | Returns `{summary, line_by_line, time_complexity, space_complexity, potential_bugs, improvement_suggestions, dependencies}` |
| `review_and_fix(code, error_message='')` | | Agent loop to diagnose and fix bugs. Returns agent result + `{original_code, fixed_code}` |
| `generate_tests(code, framework='pytest')` | | Agent loop to write and run a test suite. Returns agent result + `{test_code, framework}` |

**Example:**
```bash
curl -X POST http://localhost:5000/api/code_writer \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Write a Python function that parses a CSV file and returns a list of dicts, with error handling", "language": "python"}'
```

---

## Dependency matrix

| Capability | ai_engine | search_engine | rag_engine | db_handler | template_manager |
|---|:---:|:---:|:---:|:---:|:---:|
| research_assistant | ✓ | ✓ | opt | opt | |
| deep_researcher | ✓ | ✓ | | | |
| niche_finder | ✓ | ✓ | | | |
| competitive_intelligence_operative | ✓ | ✓ | opt | | |
| market_sales_research | ✓ | ✓ | | | |
| ma_target_profiler | ✓ | ✓ | | | |
| psychographic_profile_generator_analyzer | ✓ | ✓ | | | |
| regulatory_change_manager | ✓ | ✓ | | | |
| brand_sentiment_orchestrator | ✓ | ✓ | | | |
| intellectual_property_strategist | ✓ | ✓ | opt | | |
| ai_report_writer | ✓ | | | | ✓ |
| proposal_compositor | ✓ | | | | ✓ |
| internal_communications_automator | ✓ | | | | ✓ |
| course_creator | ✓ | | | | |
| website_creator | ✓ | | | | |
| customer_support_chatbot_builder | ✓ | | | | |
| financial_forecasting_analyst | ✓ | | | opt | |
| financial_accountant | ✓ | | | opt | |
| process_optimization_analyst | ✓ | | | opt | |
| sustainability_impact_simulator | ✓ | | | | |
| negotiation_strategy_builder | ✓ | | | | |
| supply_chain_resilience_planner | ✓ | ✓ | | | |
| crisis_simulation_response_architect | ✓ | | | | |
| cultural_transformation_designer | ✓ | | | | |
| workflow_automator | ✓ | | | | |
| social_media_manager | ✓ | ✓ | | | |
| human_resource_manager | ✓ | | | opt | |
| talent_analytics_succession_forecaster | ✓ | | | opt | |
| project_task_manager | ✓ | | | opt | |
| ethical_ai_governance_engine | ✓ | | | | |
| cybersecurity_guardian | ✓ | ✓ | | | |
| legal_compliance_officer | ✓ | ✓ | opt | | |
| accessibility_compliance_verifier | ✓ | ✓ | | | |
| customer_relationship_manager | ✓ | | | opt | |
| data_integrator | ✓ | | | | |
| code_writer | ✓ | | | | |

`opt` = optional — capability degrades gracefully when this dep is unavailable (uses LLM knowledge instead of live data).

# Research: Agent Memory Architecture & Business Capabilities for Thuon

**Date**: 2026-06-13  
**Purpose**: Design foundation for Thuon's persistent memory, task/calendar system, and expanded business automation capabilities

---

## Part 1: Hermes Agent Architecture Analysis

Source: `github.com/nousresearch/hermes-agent`

### Memory System

Hermes implements **four tiers** of memory:

| Tier | File/Store | Purpose |
|---|---|---|
| Semantic — User | `~/.hermes/memories/USER.md` | Who the user is — preferences, communication style, corrections |
| Semantic — World | `~/.hermes/memories/MEMORY.md` | Facts about environment, project conventions, tool quirks |
| Episodic | `~/.hermes/sessions.db` (SQLite FTS5) | Full session event log with full-text search |
| External | `MemoryProvider` ABC | Pluggable backends: Honcho (dialectic user modeling), Mem0, Supermemory, etc. |

**Key patterns adopted for Thuon:**
- `§` delimiter in markdown files for clean fact boundaries
- Frozen-snapshot injection: memory loaded at session start, never mutated mid-session (preserves LLM prefix cache)
- Three-tier system prompt: `stable` (identity) / `context` (cwd-dependent) / `volatile` (USER.md + MEMORY.md + date)
- Background review fork: after N turns, spawn isolated agent with whitelist {memory, skill} tools only — updates stores without contaminating main conversation

### Skills System

- Skills = directories with `SKILL.md` (YAML frontmatter + markdown body)
- Progressive disclosure: index (always loaded) → instructions (on demand via `skill_view`) → linked files
- Self-improvement: background fork after complex tasks (≥5 tool calls) reviews conversation → creates/patches skills
- Lifecycle: `active → stale → archived` managed by weekly `curator.py`
- Skills are instruction documents, NOT typed function signatures

**Thuon equivalent**: Thuon's YAML pipeline files serve the same role as skills — instruction documents for capability chains.

### Task / Todo System

- `TodoStore`: in-memory per session, `{id, content, status: pending|in_progress|completed|cancelled}`
- Compression survival: active tasks re-injected after context compression
- Kanban (`kanban.db` SQLite): multi-agent, multi-session task orchestration
- Heartbeat mechanism prevents task orphaning

### Calendar / Cron System

```json
{
  "id": "uuid",
  "prompt": "natural language task description",
  "schedule": "cron expr OR '2h' | '1d'",
  "skills": ["skill-name"],
  "state": "scheduled|paused|running",
  "next_run": "ISO timestamp"
}
```

- Tick every 60s from background thread
- File-based lock prevents concurrent races
- `[SILENT]` sentinel suppresses delivery while saving output
- Security: `cronjob` toolset forbidden in cron agents (no recursive scheduling)

### Identity / Persona

- `SOUL.md` = agent identity (first block of stable system prompt tier)
- Multiple named profiles under `~/.hermes/profiles/<name>/`
- Honcho plugin: dialectic user modeling via plastic-labs API
- `cross_profile=True` required for cross-profile writes (safety guard)

### Notable Design Patterns

1. **Prompt cache as first-class constraint** — entire architecture organized around prefix cache preservation
2. **Narrow core / fat edges** — capability lives at edges (skills, plugins) not in core tools
3. **Background fork for learning** — memory/skill writes happen asynchronously after each turn
4. **Behavioral guidance in schema descriptions** — guidance co-located with tool definition, not bloating system prompt
5. **Injection defense in depth** — threat scanning at: context load, memory writes, skill loads, cron assembly

---

## Part 2: Agent Memory Architecture Survey (2025-2026)

### Memory Taxonomy (CoALA Framework)

| Type | Cognitive Analog | LLM Implementation |
|---|---|---|
| Working | Phonological loop | Context window tokens |
| Episodic | Hippocampal sequences | Timestamped event logs (SQLite) |
| Semantic | Neocortical concepts | BM25/vector store over extracted facts |
| Procedural | Basal ganglia IF-THEN | Agent code + skill libraries + LLM weights |
| Sensory | Perceptual buffer | Real-time tool outputs (transient) |

### MemGPT / Letta

OS-inspired tiered memory. Agent self-manages via function calls:
- **Core memory**: always in-context, char-limited `human` and `persona` blocks
- **Recall storage**: full event log (keyword search)
- **Archival storage**: vector-embedded, infinite (semantic search)

Eviction: FIFO conversation queue → evicted to recall storage → recursive summary in slot 0.

**Failure modes**: model-dependent reliability, framework lock-in, token overhead.

### Mem0

Extraction-centric passive capture:
1. LLM extracts atomic facts from each conversation turn
2. Vector similarity check against existing memories
3. Operation determined: ADD / UPDATE / DELETE / NOOP
4. Graph store (Neo4j) for entity-relationship extraction

Retrieval: BM25 + embedding cosine + entity matching (fused ranking, +29.6 pts temporal reasoning vs pure vector).

Multi-scope: `user_id` + `agent_id` + `run_id` + `app_id` — strict tenant isolation.

### A-MEM (NeurIPS 2025)

Zettelkasten-inspired — **backward propagation** distinguishes it:
- New memory insertion links to top-k similar existing notes
- Propagates back to update linked notes' contextual representations
- Existing memories evolve when new evidence arrives (vs append-only in Mem0/MemGPT)

### Reflexion

Verbal reinforcement: policy θ = {model, memory}. Memory IS the policy.
- After failed trial: LLM generates diagnostic reflection → appended to memory
- Sliding window eviction (Ω=1-3)
- +22% ALFWorld, +20% HotPotQA, +11% HumanEval vs baseline

### Practical Data Model (PostgreSQL + pgvector)

```sql
-- User identity (semantic)
user_profiles: id, facts JSONB, embedding vector, valid_from, valid_until, source, confidence

-- Session history (episodic)  
session_events: id, session_id, user_id, event_type, content, metadata, created_at

-- Extracted memories (semantic)
memories: id, user_id, content, memory_type, embedding, access_count, last_accessed, expires_at

-- Skills (procedural)
skills: id, agent_id, description, embedding, code, success_count, fail_count
```

**Retrieval pipeline** (single PostgreSQL query): semantic similarity ∪ recent episodes ∪ relevant skills → BM25+embedding fusion rerank → inject top-N.

**Consolidation** (background job): episodic → semantic summarization, dedup by cosine similarity, staleness detection via `expires_at + access_count decay`.

---

## Part 3: Business Automation Capabilities Survey

### Top 5 Highest-ROI for 10-50 Person Federal Consulting Firm

| Priority | Automation | Time to Value | Annual ROI Estimate |
|---|---|---|---|
| 1 | SAM.gov monitoring + bid/no-bid triage | Days | Avoid 1 missed recompete = $500K-$5M |
| 2 | Meeting notes + action item extraction | Days | 4+ hrs/week/person recovered |
| 3 | Utilization + burn rate dashboard | 3-6 weeks | +5% utilization = $312K/yr (20 consultants @ $150/hr) |
| 4 | FAR/DFARS compliance + cert renewal | 1-2 weeks | Prevent 1 compliance failure = $500K+ |
| 5 | Proposal knowledge library | 4-8 weeks | 30-50% reduction in proposal labor |

### Full Capability Inventory by Domain

#### CRM-Adjacent
- Relationship heat maps (contact staleness alerts)
- Follow-up reminders with context ("You last talked to X about Y — 47 days ago")
- Pipeline stage summaries with probability-weighted revenue
- Capture gate review checklists (PWin, differentiators, teaming gaps)

#### Financial
- Draft client invoices (T&M, FFP milestone, cost-reimbursable) from approved time
- Burn rate dashboards (% ceiling consumed vs PoP elapsed)
- Utilization reports (billable % per consultant vs 70-80% target)
- "At-risk" alerts when burn projects contract overrun within 60 days

#### Operations
- Weekly project status reports (% complete, schedule variance, EAC)
- Resource demand/supply forecasts (who available, when, what skills)
- Subcontractor deliverable tracking + invoice approval queues
- Margin-at-risk reports per project

#### Business Development
- Win probability scores per pursuit (incumbent, competition, fit factors)
- Weighted pipeline forecast (30/60/90/180-day revenue)
- Win rate by category (agency, NAICS, vehicle, set-aside, contract size)
- Price-to-win estimates from FPDS historical award data

#### Compliance
- Clause inventory per contract with risk flags
- Certification renewal calendar (SAM.gov, 8(a), ISO, CMMC, clearances)
- CMMC continuous compliance dashboard
- Regulatory change digest (new FAR/DFARS rules with effective dates)

#### Knowledge Management
- Structured meeting summaries (decisions, action items, open questions)
- Lessons learned capture (tagged by project type, failure mode)
- Expertise locator ("Who has experience with GSA MAS + cleared staff?")
- Auto-updated past performance library

#### Communication
- Client status reports (formatted for CO/COR, PM, or executive audience)
- BD outreach emails (introduction, capability teaser, follow-up)
- Weekly executive brief (pipeline, financials, utilization, risks)
- Board report narrative (quarterly)

#### HR/People
- Skills gap analysis (current vs. future pipeline requirements)
- Individual learning paths (certifications, stretch assignments)
- Certification expiration alerts (individual + firm-wide)
- "Bench risk" reports (cleared staff at bench > 30 days)

#### Market Intelligence
- Daily opportunity digest (SAM.gov, filtered by NAICS/agency/keyword)
- Recompete radar (contracts expiring within 180 days)
- Competitor win tracking (who's winning what, at what price)
- Agency spending trends (increasing/decreasing in your capability area)

#### Personal Productivity
- Pre-meeting briefs (who you're meeting, history, talking points, open items)
- Action item extraction from transcripts (owner + deadline)
- Weekly review (open items, overdue tasks, pipeline status)
- Daily brief (inbox priority, top 3 priorities, flagged risks)

---

## Part 4: What Was Implemented in Thuon

### New Core Infrastructure

| File | What it does |
|---|---|
| `core/memory_store.py` | Three-tier memory: USER.md + MEMORY.md (file-backed) + SQLite FTS5 episodic store |
| `core/task_store.py` | Persistent SQLite task/todo store with Kanban support |
| `core/calendar_store.py` | Calendar events store with typed events, alert thresholds, RFP sync |

### New Capabilities

| Capability | What it does |
|---|---|
| `meeting_notes_extractor` | Extracts decisions, action items, follow-ups from transcripts → auto-creates tasks + calendar events |
| `pre_meeting_brief` | Generates who-you're-meeting + history + talking points + open items |
| `weekly_review_generator` | Aggregates RFP pipeline + tasks + calendar + memory into executive weekly brief |
| `memory_consolidator` | Background review fork: extracts durable facts from recent activity → USER.md + MEMORY.md |
| `company_profile_generator` | AI interview → generates all 9 company KB files |

### Hermes Patterns Adapted for Thuon

| Hermes Pattern | Thuon Implementation |
|---|---|
| USER.md + MEMORY.md | `data/memory/USER.md` + `data/memory/MEMORY.md` |
| SQLite FTS5 session store | `data/memory/sessions.db` |
| Background review fork | `memory_consolidator` capability (manual trigger + scheduled) |
| Three-tier system prompt | Memory context block injected via `get_context_block()` |
| TodoStore with compression survival | `core/task_store.py` (SQLite-persisted, survives restarts) |
| Cron jobs with delivery | Existing `core/scheduler.py` with `schedule` library |
| SOUL.md identity | `data/company/profile.md` as company identity |
| Skill library | `data/pipelines/*.yaml` as reusable workflow patterns |

### Patterns NOT Adopted (and Why)

| Pattern | Why Not |
|---|---|
| External memory providers (Honcho, Mem0) | Adds cloud dependency; Thuon is designed for local-first operation |
| Prefix cache optimization | Thuon doesn't use Claude API natively (uses Ollama); not applicable |
| `check_fn` TTL-cached availability | Thuon capabilities are always-available; no dynamic toolset composition |
| Subagent spawning (`delegate_task`) | Thuon uses YAML pipeline runner for multi-step orchestration |

---

## Part 5: Implementation Roadmap (Remaining)

### High Priority (next sprint)

1. **Contact Intelligence** (`contact_intelligence.py`) — CRM-lite with relationship heat maps
2. **Compliance Tracker** (`compliance_tracker.py`) — certification renewal calendar + FAR clause flagging
3. **Utilization Analyzer** (`utilization_analyzer.py`) — timesheet CSV → burn rate + utilization reports
4. **SAM.gov Monitor** — enhance existing RFP discovery with FPDS price-to-win data
5. **Memory injection into capability prompts** — wire `memory_store.get_context_block()` into existing capabilities

### Medium Priority

6. **Invoice Draft Generator** (`invoice_generator.py`) — T&M invoices from timesheet data
7. **Executive Brief Writer** (enhanced `daily_brief.py`) — full aggregate brief with pipeline + financial + risks
8. **Win Rate Analyzer** (`win_rate_analyzer.py`) — historical win/loss pattern analysis
9. **Lessons Learned Capture** (`lessons_learned.py`) — structured post-project knowledge capture

### Low Priority / Future

10. Dialectic user modeling (Honcho-style) — requires conversational interface
11. Skill self-improvement loop — Thuon would need to create/modify YAML pipelines autonomously
12. Multi-agent Kanban — relevant when multiple people use the same Thuon instance

---

## Key Sources

- Hermes Agent: https://github.com/nousresearch/hermes-agent
- MemGPT Paper: arXiv:2310.08560
- Mem0 Paper: arXiv:2504.19413
- A-MEM (NeurIPS 2025): arXiv:2502.12110
- CoALA Cognitive Architecture: arXiv:2309.02427
- Reflexion: arXiv:2303.11366
- SPI Research PSA Benchmarks (2025)
- GovDash Federal Contracting CRM Guide (2026)
- Federal News Network: AI-evaluated proposals (Apr 2026)

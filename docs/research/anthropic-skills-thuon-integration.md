# Anthropic Agent Skills — Architecture & Thuon Integration Proposal

**Date:** 2026-06-13  
**Researcher:** Claude Sonnet 4.6 (parallel 4-agent sweep)  
**Status:** Complete

---

## Executive Summary

The Anthropic Agent Skills framework (launched December 2025, now an open standard at agentskills.io) defines **directory-based prompt bundles** — a `SKILL.md` file with YAML frontmatter and a Markdown body — that Claude loads via three-tier progressive disclosure. They are *not* tool/function-call definitions; they are **structured prompt templates** that get injected into context when triggered. The standard is now supported by ~40 clients (Cursor, VS Code, Gemini CLI, OpenAI Codex, Goose, OpenHands, Spring AI, Databricks, Snowflake, and others).

For Thuon, the most practical integration is a **hybrid approach**: adopt the SKILL.md file format as Thuon's own capability manifest (replacing the two hardcoded Python registries with filesystem discovery), wire SearXNG + Firecrawl as the web-access foundation for skills that need external data, and build a `SkillRouter` that translates natural-language requests into capability invocations — giving Thuon genuine "learn to do new things" capability without requiring code changes.

---

## Part 1: The Agent Skills Framework — Complete Technical Breakdown

### 1.1 Repository Structure

**Repository:** https://github.com/anthropics/skills  
**Open standard:** https://agentskills.io/specification  
**API guide:** https://platform.claude.com/docs/en/api/skills-guide  
**Anthropic blog:** https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

The repo contains **17 reference skills**, each a directory:

```
anthropics/skills/
├── README.md
├── marketplace.json          # catalog metadata for all skills
├── SKILL_TEMPLATE/           # canonical authoring template
│   ├── SKILL.md
│   └── README.md
├── web-search/
│   └── SKILL.md
├── computer-use/
│   └── SKILL.md
├── code-execution/
│   └── SKILL.md
├── image-generation/
│   └── SKILL.md
├── data-analysis/
│   └── SKILL.md
├── pdf-reader/
│   └── SKILL.md
├── document-writer/
│   └── SKILL.md
├── email-composer/
│   └── SKILL.md
├── calendar-manager/
│   └── SKILL.md
├── file-manager/
│   └── SKILL.md
├── terminal/
│   └── SKILL.md
├── browser-automation/
│   └── SKILL.md
├── database-query/
│   └── SKILL.md
├── api-caller/
│   └── SKILL.md
├── memory/
│   └── SKILL.md
├── research-assistant/
│   └── SKILL.md
└── code-reviewer/
    └── SKILL.md
```

### 1.2 SKILL.md File Format — Complete Schema

A `SKILL.md` file has two parts: a YAML frontmatter block and a Markdown body.

#### Open Standard Fields (agentskills.io — cross-client portable)

```yaml
---
name: web-search                          # required; ≤64 chars, kebab-case
description: |                            # required; ≤1024 chars; used for trigger matching
  Search the web for current information.
  Use when the user asks about recent events, news, or needs
  up-to-date information not in training data.
license: MIT                              # optional; SPDX identifier
compatibility:                            # optional; client compatibility hints
  clients: [claude-code, cursor, gemini-cli]
  min_version: "2.1.0"
metadata:                                 # optional; arbitrary key-value
  author: anthropic
  version: "1.0.0"
  tags: [web, search, internet]
allowed-tools:                            # optional (EXPERIMENTAL); grant extra tool access
  - computer_use_20250124
  - bash
---
```

#### Claude Code Extension Fields (not in the open standard)

```yaml
---
# ... open standard fields above ...

when_to_use: |                            # additional trigger hint shown to Claude
  Invoke this skill when the user asks about current events,
  prices, weather, or any time-sensitive data.
argument-hint: "search query"             # shown in the slash-command autocomplete
arguments:                                # typed parameter declarations
  - name: query
    description: "The search query"
    required: true
  - name: max_results
    description: "Maximum results (default 5)"
    required: false
    default: "5"
model: claude-sonnet-4-6                  # override model for this skill's turn
effort: high                              # override effort level (low/medium/high)
context: fork                             # fork a new context instead of sharing
disable-model-invocation: true            # run shell steps only, no LLM turn
user-invocable: true                      # whether user can invoke via /skill-name
disallowed-tools:                         # tools to block during skill execution
  - bash
agent: custom-agent-name                  # route to a named subagent
hooks:                                    # shell commands run at lifecycle events
  pre: "echo 'Starting skill'"
  post: "echo 'Skill complete'"
paths:                                    # file path patterns skill is scoped to
  - "**/*.py"
  - "src/**"
shell: |                                  # shell script to run; stdout injected into context
  #!/bin/bash
  echo "Current date: $(date)"
  echo "Git status: $(git status --short)"
---
```

#### Markdown Body

The body is the prompt template injected into context when the skill activates. It can reference:

- `$ARGUMENTS` — the full argument string passed by the user
- `${CLAUDE_SKILL_DIR}` — absolute path to the skill's directory
- `` !`command` `` — inline shell execution; stdout replaces the expression at load time
- Named args from the `arguments` array as `$ARG_NAME` or `${arg_name}`

Example body:

```markdown
## Web Search Skill

You have access to real-time web search. When searching:

1. Use specific, targeted queries
2. Cite sources with URLs
3. Prefer recent results (last 30 days)
4. Current date: !`date +"%Y-%m-%d"`

## Search Query
$ARGUMENTS

## Instructions
Search for the above query and provide a comprehensive answer with citations.
```

### 1.3 Progressive Disclosure — Three Tiers

**Tier 1: Catalog** (loaded at startup, always in context)
- Only `name` + `description` from frontmatter
- Exposed as a meta-tool called `Skill` in the `tools` array
- Capped at ~1% of the context window across all skills
- Enables Claude to decide *whether* to invoke a skill

**Tier 2: Full body** (injected on activation)
- The complete `SKILL.md` content injected as a hidden `isMeta: true` message
- Shell preprocessing runs at this point (`` !`cmd` `` expressions evaluated)
- `allowed-tools` grants take effect for this turn
- Model/effort overrides applied if specified

**Tier 3: Resources** (on demand)
- Additional files referenced from `SKILL.md` loaded as needed
- Assets, reference documents, schemas fetched lazily
- Keeps initial context load minimal

### 1.4 Invocation Mechanisms

**Slash command:** `/skill-name [args]` — direct user invocation if `user-invocable: true`

**Natural language trigger:** Claude reads the `description` and `when_to_use` fields and decides to invoke when the user's request semantically matches. This is the "contextual" behavior. **Known limitation:** description matching is weak — short, vague descriptions cause under-triggering. Best practice: write `description` as explicit "use this when..." sentences.

**Programmatic (API):**
```python
import anthropic

client = anthropic.Anthropic()

# Upload a skill
skill = client.beta.skills.create(
    name="web-search",
    description="Search the web for current information",
    content=open("skills/web-search/SKILL.md").read(),
)

# Use in a message
response = client.beta.messages.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What happened in Kenya yesterday?"}],
    container={"skills": [skill.id]},  # max 8 per request
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],  # required
    betas=["skills-2025-10-02"],
    max_tokens=4096,
)
```

**Constraints:**
- Max 8 skills per request
- Max file size: 30 MB
- Name: ≤64 chars
- Description: ≤1024 chars
- Beta header `skills-2025-10-02` required
- `code_execution_20250824` tool must be present in `tools`

### 1.5 Security Model

- Skills are loaded at trust — the documentation says "audit them like installing software"
- `allowed-tools` grants additional tool access (additive, not restrictive)
- `disallowed-tools` blocks specific tools
- Skills declaring `allowed-tools` or `hooks` require first-use approval (Claude Code ≥2.1.19)
- Project-level skills (`.claude/skills/`) require workspace-trust acceptance
- Shell scripts in `shell:` or `` !`cmd` `` run as the current user — full system access
- The skill's source body is injected into context; scripts run in Bash but their source text does NOT appear in context (only stdout does)

### 1.6 Skill Authoring Patterns (Observed Across 17 Official Skills)

| Pattern | Description | Example |
|---------|-------------|---------|
| **Router** | Reads context, routes to different sub-tools | `research-assistant` — picks web/kb/code based on query type |
| **Workflow** | Ordered steps, each building on prior | `document-writer` — outline → draft → review → finalize |
| **Judgment** | Applies domain expertise rules | `code-reviewer` — security, performance, style rubrics |
| **Meta-skill** | Orchestrates other skills | `data-analysis` — invokes code-execution + file-manager |
| **Black-box wrapper** | Hides complex tool setup behind simple UX | `pdf-reader` — handles extraction/formatting details |

### 1.7 Skill Composition

**Skills can reference MCP servers** — if the platform exposes tools via MCP, a skill body can instruct Claude to call those tools. This is the primary composition primitive.

**Skills do NOT have a formal "call another skill" primitive.** The body can instruct Claude to invoke a slash command, but this is a text instruction, not a typed call.

**Skills + subagents:** The `agent` frontmatter field routes execution to a named subagent. The subagent gets the skill body as its system prompt and inherits the `allowed-tools` grants.

---

## Part 2: Thuon Current Architecture — Gaps for Skills Integration

### 2.1 What Exists

| Component | Status | Notes |
|-----------|--------|-------|
| Capability registry | ✅ Two (thuon.py + web_app.py) | **Hardcoded dicts, not discoverable** |
| Capability invocation | ✅ Python class + method | Structural typing, no ABC enforcement |
| YAML pipeline runner | ✅ core/pipeline_runner.py | String-key resolution, template substitution |
| Progress callbacks | ⚠️ Long-form engine only | Not platform-wide |
| Context/session threading | ⚠️ MemoryStore + SessionStore exist | Not injected into capabilities |
| Pre/post hooks | ❌ None | No `before_step`/`after_step` |
| Plugin/skill loading | ❌ None | No filesystem discovery, no manifest |
| Natural language routing | ⚠️ `Thuon._route()` exists | Routes to capabilities but no skill matching |
| MCP server | ❌ None | No MCP exposure of capabilities |

### 2.2 Critical Gaps

1. **Two divergent registries** — `thuon.py:_REGISTRY` (16 caps) and `web_app.py:CAPABILITY_REGISTRY` (~50 caps) are hand-maintained separately. Any new capability requires two edits. A skills system needs a single source of truth.

2. **No filesystem discovery** — capabilities only exist if manually added to both dicts. A skill that drops a directory into `capabilities/skills/` cannot self-register.

3. **No context object** — capabilities receive only the kwargs they declare. There is no `ctx.memory`, `ctx.session`, `ctx.user_preferences` that a skill could query without bespoke DI wiring.

4. **No lifecycle hooks** — cannot instrument capability execution (logging, telemetry, rate-limiting, caching) without modifying each capability.

5. **No MCP exposure** — Claude cannot call Thuon capabilities as tools from within a skill body unless they are exposed via MCP.

---

## Part 3: Integration Architecture Proposal

### 3.1 Core Concept — Skills as First-Class Thuon Objects

A **Thuon Skill** is a directory under `thuon_platform/skills/` (or user-space `~/.thuon/skills/`) containing:

```
skills/
└── daily-brief-sports/          # skill name = directory name
    ├── SKILL.md                 # standard-compatible manifest
    └── assets/                  # optional: data files, templates
        └── rugby_teams.json
```

`SKILL.md` is **100% compatible with the Anthropic open standard** (agentskills.io) with Thuon-specific extension fields in the frontmatter under a `thuon:` namespace:

```yaml
---
name: daily-brief-sports
description: |
  Extend the daily brief with live sports results. Use when the user asks
  for today's sports news, match results, or wants to add sports to their
  morning brief.
when_to_use: |
  Invoke when user asks about sports results, World Cup, rugby, polo,
  or wants sports added to their daily brief.
argument-hint: "sport or competition name"
arguments:
  - name: sport
    description: "Sport to focus on (rugby, football, polo, or all)"
    required: false
    default: "all"

thuon:
  capability: daily_brief           # links to an existing Thuon capability
  method: generate                  # method to call on the capability
  pipeline: daily_brief_sports      # OR a YAML pipeline to run instead
  deps: [ai_engine, search_engine, calendar_store]
  params:                           # fixed params merged with runtime args
    include_sections: [sports]
  output_format: markdown           # how to render the result
  category: intelligence            # UI grouping
  tier: 1                           # no-auth tier
---

## Daily Brief — Sports Extension

You are adding a sports results section to the daily brief for a
Nairobi-based executive. Focus on:
- FIFA World Cup 2026 results
- Kenya Simbas rugby
- World Rugby international tests
- Polo championships

Sport requested: $ARGUMENTS

Retrieve the latest results and summarize in 3-4 bullets per sport
with scores, standings impact, and next fixture dates.
```

### 3.2 SkillRegistry — Replaces the Two Hardcoded Registries

```python
# core/skill_registry.py

from __future__ import annotations
import importlib
import threading
from pathlib import Path
import yaml

_SKILL_DIRS = [
    Path(__file__).parent.parent / 'skills',           # bundled skills
    Path(__file__).parent.parent / 'capabilities',    # existing caps as auto-skills
    Path.home() / '.thuon' / 'skills',                 # user skills
]

class SkillManifest:
    """Parsed SKILL.md — open standard + thuon: namespace."""
    name: str
    description: str
    when_to_use: str
    argument_hint: str
    arguments: list[dict]
    thuon: dict          # thuon-namespace extensions
    body: str            # markdown body (prompt template)
    path: Path

class SkillRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._skills: dict[str, SkillManifest] = {}
        self._reload()

    def _reload(self):
        """Walk skill dirs and parse all SKILL.md files."""
        discovered = {}
        for skill_dir in _SKILL_DIRS:
            if not skill_dir.is_dir():
                continue
            for manifest_path in skill_dir.rglob('SKILL.md'):
                try:
                    manifest = self._parse(manifest_path)
                    discovered[manifest.name] = manifest
                except Exception as e:
                    logger.warning(f'Failed to load skill {manifest_path}: {e}')
        with self._lock:
            self._skills = discovered

    def get(self, name: str) -> SkillManifest | None: ...
    def all(self) -> list[SkillManifest]: ...
    def search(self, query: str, top_k: int = 5) -> list[SkillManifest]:
        """BM25 search over name + description + when_to_use fields."""
        ...

    def register_capability_as_skill(self, cap_name: str, cap_meta: dict):
        """Auto-generate a SkillManifest from an existing registry entry.
        Enables zero-migration path: existing capabilities become skills automatically."""
        ...
```

**Key design:** existing capabilities are **auto-promoted** to skills by reading their registry metadata. No manual `SKILL.md` authoring required for existing capabilities. New capabilities that want richer trigger behavior author a `SKILL.md`.

### 3.3 SkillRouter — Contextual Invocation

```python
# core/skill_router.py

class SkillRouter:
    """Routes natural-language requests to the best Thuon skill.

    Two-stage matching:
    1. BM25 keyword match over skill descriptions (fast, no LLM)
    2. LLM rerank if BM25 returns multiple high-scoring candidates
    """

    def __init__(self, registry: SkillRegistry, ai_engine: AIModel):
        self._registry = registry
        self._ai       = ai_engine

    def route(self, instruction: str, context: SkillContext) -> RouteResult:
        """Return the best skill + extracted args for an instruction."""

        # Stage 1: BM25 candidate shortlist
        candidates = self._registry.search(instruction, top_k=5)
        if not candidates:
            return RouteResult(skill=None, confidence=0.0)
        if len(candidates) == 1 or candidates[0].score > 0.8:
            return RouteResult(skill=candidates[0].manifest, confidence=candidates[0].score)

        # Stage 2: LLM disambiguation (only when needed)
        catalog = '\n'.join(
            f'{i+1}. {c.manifest.name}: {c.manifest.description[:200]}'
            for i, c in enumerate(candidates)
        )
        prompt = (
            f'User request: "{instruction}"\n\n'
            f'Available skills:\n{catalog}\n\n'
            'Which skill number best matches the request? '
            'Reply with just the number, or 0 if none match.'
        )
        raw = self._ai.generate_text(prompt).strip()
        idx = int(raw) - 1 if raw.isdigit() else -1
        if 0 <= idx < len(candidates):
            return RouteResult(skill=candidates[idx].manifest, confidence=0.9)
        return RouteResult(skill=None, confidence=0.0)

    def execute(self, instruction: str, context: SkillContext) -> dict:
        """Route + execute in one call. Used by /api/do endpoint."""
        result = self.route(instruction, context)
        if result.skill is None:
            return {'status': 'unrouted', 'instruction': instruction}
        return self._invoke_skill(result.skill, instruction, context)

    def _invoke_skill(self, skill: SkillManifest, args: str, context: SkillContext) -> dict:
        thuon_cfg = skill.thuon or {}

        if thuon_cfg.get('pipeline'):
            # Run a YAML pipeline
            from core.pipeline_runner import PipelineRunner
            runner = PipelineRunner(context.platform)
            return runner.run(thuon_cfg['pipeline'], {'input': args, **context.as_dict()})

        elif thuon_cfg.get('capability'):
            # Direct capability invocation
            cap     = getattr(context.platform, thuon_cfg['capability'])
            params  = {**thuon_cfg.get('params', {})}
            if args:
                params[thuon_cfg.get('args_param', 'query')] = args
            return cap(**params)

        else:
            # Pure LLM skill — render body as prompt, call LLM
            prompt = _render_body(skill.body, args, context)
            return {'content': context.ai_engine.generate_text(prompt)}
```

### 3.4 SkillContext — The Missing Context Object

```python
# core/skill_context.py

@dataclass
class SkillContext:
    """Injected into every skill/capability execution. Opt-in access to platform state."""
    ai_engine:       AIModel
    search_engine:   SearchEngine | None
    memory_store:    MemoryStore
    session_store:   SessionStore
    calendar_store:  CalendarStore
    notification_bus: NotificationBus
    platform:        Any           # Thuon facade reference
    session_id:      str
    user_prefs:      dict          # from MemoryStore.read_user()

    def as_dict(self) -> dict:
        """Serializable subset for pipeline template resolution."""
        return {
            'session_id': self.session_id,
            'user_location': self.user_prefs.get('location', 'Nairobi'),
            'today': date.today().isoformat(),
        }

    def memory(self, query: str, top_k: int = 5) -> str:
        return self.memory_store.get_context_block(query, top_k)

    def recent_sessions(self, n: int = 5) -> list[dict]:
        return self.session_store.get_context(self.session_id, max_entries=n)
```

The `PipelineRunner` and `SkillRouter` construct a `SkillContext` once per request and pass it through. Capabilities that want context declare it as an optional `__init__` kwarg: `context: SkillContext | None = None`.

### 3.5 Lifecycle Hooks — Pipeline Instrumentation

```python
# core/pipeline_runner.py addition

class PipelineHooks:
    def before_step(self, step_name: str, cap_name: str, params: dict, ctx: SkillContext): pass
    def after_step(self, step_name: str, result: dict, elapsed_ms: int): pass
    def on_error(self, step_name: str, exc: Exception): pass

class LoggingHooks(PipelineHooks):
    def before_step(self, step_name, cap_name, params, ctx):
        logger.info(f'[pipeline] → {step_name} ({cap_name})')
    def after_step(self, step_name, result, elapsed_ms):
        logger.info(f'[pipeline] ✓ {step_name} in {elapsed_ms}ms')

class NotificationHooks(PipelineHooks):
    def __init__(self, bus: NotificationBus): self._bus = bus
    def after_step(self, step_name, result, elapsed_ms):
        self._bus.emit('pipeline_step', {'step': step_name, 'elapsed_ms': elapsed_ms})
```

### 3.6 MCP Exposure — Skills Callable from Claude

To allow Claude to call Thuon capabilities from *within* a skill body (the most powerful integration), expose the `SkillRegistry` as an MCP server:

```python
# core/mcp_server.py

from mcp.server import Server

app = Server("thuon")

@app.list_tools()
async def list_tools():
    registry = get_skill_registry()
    return [
        Tool(
            name=skill.name,
            description=skill.description[:500],
            inputSchema={
                'type': 'object',
                'properties': {
                    arg['name']: {'type': 'string', 'description': arg['description']}
                    for arg in skill.arguments
                },
            }
        )
        for skill in registry.all()
        if skill.thuon.get('expose_via_mcp', True)
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    context = get_global_skill_context()
    router  = get_skill_router()
    result  = router._invoke_skill(registry.get(name), arguments.get('query', ''), context)
    return [TextContent(type='text', text=json.dumps(result))]
```

Register in `config.yaml`:
```yaml
mcp:
  thuon_server:
    command: uv
    args: [run, python, -m, thuon_platform.core.mcp_server]
    transport: stdio
```

This enables a skill body to say: "Call the Thuon `daily_brief` capability via MCP" and Claude executes it directly, returning structured data into the skill's context.

---

## Part 4: How Contextual Skill Selection Works

### 4.1 The Trigger Chain

```
User input
    │
    ▼
1. Exact slash command match (/skill-name)
    │ no match
    ▼
2. BM25 keyword match (description + when_to_use + tags)
    │ multiple high-scoring candidates
    ▼
3. LLM disambiguation (1 LLM call, ~100ms)
    │
    ▼
4. Skill body rendered with $ARGUMENTS + SkillContext
    │
    ▼
5. thuon.capability / thuon.pipeline / pure LLM dispatch
    │
    ▼
6. Result formatted per thuon.output_format
    │
    ▼
7. SkillContext.session_store.save(session_id, skill_name, args, result)
```

### 4.2 Description Writing for Strong Trigger Recall

The most common failure mode is **under-triggering** — Claude (or BM25) doesn't match the user's request to the right skill because the description is too vague.

**Weak description (will miss requests):**
```
description: "Daily brief capability"
```

**Strong description (explicit trigger examples):**
```
description: |
  Generate the morning daily brief. Use when the user says:
  "give me my brief", "what happened today", "morning briefing",
  "daily summary", "FX rates today", "what's on my calendar".
  Returns FX rates, weather, news, todos, and schedule.
```

### 4.3 Contextual Enrichment at Match Time

The `SkillRouter` enriches the `instruction` string with context before BM25 matching:

```python
def _enrich(self, instruction: str, context: SkillContext) -> str:
    """Add temporal and user context to improve matching accuracy."""
    enriched = instruction
    if context.user_prefs.get('location'):
        enriched += f' [location: {context.user_prefs["location"]}]'
    enriched += f' [date: {date.today().isoformat()}]'
    recent = context.recent_sessions(3)
    if recent:
        last_caps = [s.get('capability') for s in recent if s.get('capability')]
        enriched += f' [recent: {", ".join(last_caps[:3])}]'
    return enriched
```

---

## Part 5: Authoring and Registering New Skills

### 5.1 Three Registration Paths

| Path | When | How |
|------|------|-----|
| **Auto-promote** | Existing capability, no new behaviour | Already in `CAPABILITY_REGISTRY` → auto-generated manifest |
| **SKILL.md only** | Existing capability, richer trigger/UX | Add `skills/<name>/SKILL.md` with `thuon.capability` pointer |
| **Full skill** | New behaviour, no existing capability | `SKILL.md` + new `capabilities/<name>.py` + SKILL.md |

### 5.2 Scaffolding Script

```bash
# thuon_platform/new_skill.sh
#!/bin/bash
NAME=$1
mkdir -p "thuon_platform/skills/$NAME"
cat > "thuon_platform/skills/$NAME/SKILL.md" << EOF
---
name: $NAME
description: |
  TODO: Describe when to use this skill (write as "use when user asks...").
when_to_use: |
  TODO: More detail on trigger conditions.
argument-hint: "main argument"
arguments:
  - name: query
    description: "The user's request"
    required: true

thuon:
  capability: TODO_capability_name
  method: TODO_method_name
  deps: [ai_engine, search_engine]
  params: {}
  output_format: markdown
  category: TODO_category
  tier: 1
---

## $NAME

You are executing the $NAME skill. The user asked:
\$ARGUMENTS

Complete the task using the Thuon platform tools available.
EOF
echo "Created thuon_platform/skills/$NAME/SKILL.md"
echo "Now either:"
echo "  1. Point thuon.capability at an existing capability, OR"
echo "  2. Create thuon_platform/capabilities/$NAME.py"
```

### 5.3 Minimal SKILL.md for an Existing Capability

```yaml
---
name: competitive-intelligence
description: |
  Run a competitive intelligence sweep on a company or market. Use when
  the user asks: "research competitor X", "who competes with us in Y",
  "competitive landscape for Z", "how does X compare to Y".
when_to_use: |
  Invoke for competitive research, market analysis, or company profiling.
argument-hint: "company or market name"
arguments:
  - name: company_name
    description: "Company or market to research"
    required: true
  - name: industry
    description: "Industry context"
    required: false
    default: "professional services"

thuon:
  capability: competitive_intelligence_operative
  method: analyze_competitive_landscape
  deps: [ai_engine, search_engine, rag_engine]
  params:
    depth: deep
  output_format: report
  category: strategy
  tier: 1
---

## Competitive Intelligence Analysis

Perform a deep competitive sweep on: $ARGUMENTS

Focus on:
- Market positioning and differentiation
- Recent strategic moves
- East Africa / Kenya presence
- Pricing signals
- Win/loss patterns

Format as an executive briefing with actionable implications.
```

### 5.4 Pure LLM Skill (No Existing Capability)

```yaml
---
name: rfp-go-nogo
description: |
  Quick bid/no-bid decision for an RFP. Use when the user pastes an RFP
  summary or says "should we bid on this", "is this RFP worth pursuing",
  "quick bid evaluation".
argument-hint: "RFP summary or title"
arguments:
  - name: rfp_text
    description: "RFP title, scope, or full text"
    required: true

thuon:
  output_format: markdown
  category: strategy
  tier: 1
---

## RFP Bid/No-Bid Evaluation

**RFP:** $ARGUMENTS

Today's date: !`date +"%Y-%m-%d"`

Evaluate this RFP against our bid criteria:
- Revenue floor: >$50K
- We must have directly relevant past performance
- Deadline must be ≥14 days away
- No conflict with existing clients

Score on:
1. **Strategic fit** (0-10)
2. **Win probability** (0-10)
3. **Resource availability** (0-10)

Return:
- Overall score (0-30)
- **Recommendation: BID / NO BID / INVESTIGATE**
- Top 3 reasons
- Key risks
- Next action if BID
```

---

## Part 6: Implementation Roadmap for Thuon

### Phase 0 (1 day) — Foundation
1. Create `thuon_platform/skills/` directory
2. Write `core/skill_registry.py` — filesystem discovery + SKILL.md parser
3. Auto-generate manifests from existing `CAPABILITY_REGISTRY` entries

### Phase 1 (2 days) — Context + Router
4. Write `core/skill_context.py` — SkillContext dataclass
5. Wire SkillContext into `PipelineRunner` (pass through, opt-in)
6. Write `core/skill_router.py` — BM25 + optional LLM disambiguation
7. Update `/api/do` endpoint to use SkillRouter

### Phase 2 (1 day) — Hooks + Observability
8. Add `PipelineHooks` to `PipelineRunner`
9. Wire `LoggingHooks` and `NotificationHooks` by default
10. Add `/api/skills` endpoint — list all discovered skills with metadata

### Phase 3 (2 days) — MCP Exposure
11. Write `core/mcp_server.py` using the `mcp` Python SDK
12. Register in `config.yaml` and `create_app()`
13. Expose all Tier 1 skills as MCP tools

### Phase 4 (ongoing) — Skill Authoring
14. Author `SKILL.md` files for the 10 most-used capabilities
15. Add `new_skill.sh` scaffolding script
16. Write `/skills` UI page (catalog + test interface)

### Effort Estimate

| Phase | Effort | Risk |
|-------|--------|------|
| 0 — Foundation | ~4h | Low — read-only registry |
| 1 — Context + Router | ~1d | Medium — needs careful registry unification |
| 2 — Hooks | ~4h | Low — additive only |
| 3 — MCP | ~1d | Medium — new dep, new protocol |
| 4 — Skill authoring | Ongoing | Low — YAML files |

---

## Part 7: Gaps and Limitations

### 7.1 Skills Framework Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| No formal skill-calls-skill primitive | Skills cannot compose cleanly | Use YAML pipelines + MCP as the composition layer |
| Description matching is fragile | Under-triggering common | Write explicit "use when user says..." examples in description |
| 8-skill limit per API request | Limits catalog size for API users | Use BM25 pre-filtering to send only relevant skills |
| `skills-2025-10-02` beta header | May change or graduate | Pin to the header, handle API version upgrade |
| `code_execution` tool required | Odd dependency for non-code skills | Always include it; the overhead is minor |
| Shell `` !`cmd` `` at load time | Runs at skill activation, not invocation | Keep shell steps stateless; don't read dynamic state here |
| Open standard has no `output_format` | Cross-client output is untyped | Use `thuon:` namespace for Thuon-specific fields |

### 7.2 Thuon-Specific Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| Registry fragmentation | Two existing registries diverge further if not unified | Phase 0 must be blocking — unify before adding skills |
| SkillContext over-injection | Passing context through every call adds complexity | Make it optional kwarg with `None` default; capabilities opt in |
| BM25 false positives | Unrelated queries match skill descriptions | Tune description writing; add confidence threshold |
| MCP security surface | Exposing all capabilities via MCP without auth | Add bearer token auth to MCP server; configure allowed-capabilities list |
| No versioning | Skills can change without notice | Add `metadata.version` to all SKILL.md files; use semver |

### 7.3 Open Questions

1. **Should skills replace or augment capabilities?** The proposal keeps them as two layers (skills as discovery/routing, capabilities as execution). An alternative: migrate all capabilities to skills-only, eliminating the Python registry. This would be a larger refactor but cleaner long-term.

2. **User-space skill installation:** Should users be able to drop a `SKILL.md` into `~/.thuon/skills/` and have it auto-load? This is in the design but requires a security review (shell preprocessing runs arbitrary code).

3. **Skill versioning and hot-reload:** The SkillRegistry reloads on startup. Should it watch for filesystem changes (watchdog) and reload live? Useful during authoring but adds complexity.

4. **Skills via the Anthropic API vs local Ollama:** The `thuon:` namespace extensions are Thuon-local. If a skill is intended to run against the Anthropic API (not just Ollama), the `model:` frontmatter field should be set explicitly. Currently all LLM calls in Thuon go to Ollama; the API skill upload endpoint (`client.beta.skills.create`) is only relevant if Thuon migrates to using the Anthropic API directly.

5. **Skill marketplace:** The agentskills.io open standard defines a `marketplace.json` catalog format. Should Thuon expose a `GET /skills/marketplace.json` endpoint to become a skill source that other Claude Code users can discover? This would make Thuon skills portable to Cursor, VS Code, Gemini CLI, etc.

---

## All Sources

### Primary Sources — Fetched

| Title | URL |
|-------|-----|
| Anthropic Skills GitHub Repository | https://github.com/anthropics/skills |
| Agent Skills Specification (agentskills.io) | https://agentskills.io/specification |
| Agent Skills Client Implementation Guide | https://agentskills.io/client-implementation/adding-skills-support.md |
| Agent Skills Best Practices for Creators | https://agentskills.io/skill-creation/best-practices.md |
| Agent Skills Client Showcase (~40 clients) | https://agentskills.io/clients.md |
| Anthropic API Skills Guide | https://platform.claude.com/docs/en/api/skills-guide |
| Anthropic Engineering Blog: Equipping Agents | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills |
| Claude Code Documentation | https://docs.anthropic.com/en/docs/claude-code |
| Claude Code Skills Documentation | https://docs.anthropic.com/en/docs/claude-code/skills |
| Anthropic Python SDK — beta.skills | https://github.com/anthropics/anthropic-sdk-python |

### Skills — Individual SKILL.md Files Fetched

| Skill | URL |
|-------|-----|
| web-search/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/web-search/SKILL.md |
| computer-use/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/computer-use/SKILL.md |
| code-execution/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/code-execution/SKILL.md |
| image-generation/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/image-generation/SKILL.md |
| data-analysis/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/data-analysis/SKILL.md |
| pdf-reader/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/pdf-reader/SKILL.md |
| document-writer/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/document-writer/SKILL.md |
| research-assistant/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/research-assistant/SKILL.md |
| code-reviewer/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/code-reviewer/SKILL.md |
| memory/SKILL.md | https://raw.githubusercontent.com/anthropics/skills/main/memory/SKILL.md |
| marketplace.json | https://raw.githubusercontent.com/anthropics/skills/main/marketplace.json |

### Reference — Thuon Platform Files Read

| File | Purpose |
|------|---------|
| thuon_platform/thuon.py | Python facade + _REGISTRY |
| thuon_platform/interfaces/web_app.py | Flask routes + CAPABILITY_REGISTRY |
| thuon_platform/core/pipeline_runner.py | YAML pipeline execution |
| thuon_platform/core/pipeline.py | Callable-based pipeline |
| thuon_platform/core/ai_engine.py | AIModel ABC |
| thuon_platform/core/knowledge_ingestion.py | BM25 knowledge store |
| thuon_platform/core/settings_manager.py | Config system |
| thuon_platform/core/memory_store.py | Episodic memory |
| thuon_platform/core/session_store.py | Session state |
| thuon_platform/capabilities/daily_brief.py | Complex capability example |
| thuon_platform/capabilities/long_form_document_engine.py | Multi-stage pipeline example |
| thuon_platform/data/pipelines/*.yaml | 7 pipeline definitions |

### Secondary Sources

| Title | URL |
|-------|-----|
| agentskills.io specification (full) | https://agentskills.io |
| MCP vs Skills comparison | https://modelcontextprotocol.io |
| oh-my-claudecode plugin skills format | https://github.com/anthropics/claude-code-plugins |
| rank-bm25 Python library | https://github.com/dorianbrown/rank_bm25 |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |

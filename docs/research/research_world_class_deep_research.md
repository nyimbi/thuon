# Research: World-Class Deep Research Architecture for Thuon

**Date**: 2026-06-13  
**Purpose**: Design foundation for Thuon's consulting-grade research engine — rivaling McKinsey/BCG output quality using Ollama models through orchestration

---

## Part 1: What Makes Consulting Research World-Class

### 1.1 The Pyramid Principle (Barbara Minto — McKinsey Standard)

Present top-down, think bottom-up. Architecture:
- **Top**: Governing Recommendation (single most important takeaway)
- **Middle**: 3–5 Supporting Arguments (why the recommendation is correct)
- **Bottom**: Data, Evidence, Analysis (how we know)

**Elevator test**: Governing thought expressible in 30 seconds to a CEO. If it needs qualifiers, it's not synthesized enough.

**Inductive vs. Deductive**:
- Consulting *analysis* is inductive (evidence → conclusion)
- Consulting *communication* is deductive (conclusion → evidence)
- Always invert for presentation

### 1.2 SCQA Structure (Report Opening)

| Component | Purpose |
|---|---|
| **Situation** | Agreed current state the audience accepts |
| **Complication** | What changed, what's at risk |
| **Question** | Natural question arising from the complication |
| **Answer** | Governing thought — top of the pyramid |

SCQA must fit in 2–3 slides maximum. Function: create cognitive buy-in before the recommendation.

### 1.3 Action Titles (The Core Discipline)

Every section title is a complete declarative sentence with a specific claim:

| Weak (Topic Title) | Strong (Action Title) |
|---|---|
| "Market Overview" | "German market growing at 12% annually, 3× North America's rate" |
| "Financial Analysis" | "Acquisition generates 15% IRR under conservative synergy assumptions" |
| "Competitor Comparison" | "We outperform competitors on 4 of 6 key purchase criteria" |

Rules:
1. Complete declarative sentence — subject + verb + specific claim
2. Include a number wherever possible
3. State the conclusion, not the analysis performed
4. Maximum 15–20 words

**Titles Test**: Read all titles sequentially, skipping body content. If the complete argument is legible, the structure is correct.

### 1.4 MECE Principle

At every decomposition level: Mutually Exclusive (no overlap) + Collectively Exhaustive (no gaps).

**MECE failure modes**:
- Overlap: "Growth opportunity" and "market potential" as separate arguments
- Gap: analyzing cost without revenue when the problem is profitability
- False exhaustiveness: "Other" as a catch-all

### 1.5 "So What" Discipline

Every data point must answer: "So what does this mean for the decision?"

**Linguistic markers of failure**: "This shows that...", "As we can see...", passive voice, hedged language ("may suggest," "could potentially")

**Linguistic markers of success**: Active verbs with specific claims: "X reduces costs by Y," "X is the primary driver of Z"

### 1.6 Hypothesis-Driven Process

MBB process is fundamentally hypothesis-driven, not collect-all-then-conclude:
1. Form a hypothesis about the answer
2. Determine: What data would falsify this hypothesis?
3. Collect and analyze that data
4. Update — confirm, refine, or reject
5. Form next hypothesis on remaining questions

**Issue tree**: MECE decomposition where each branch is an open hypothesis. Priority → highest impact × lowest cost to test.

**Competing hypotheses protocol**: A world-class report explicitly addresses alternatives and explains why they were rejected.

### 1.7 Two-Layer Output Architecture

| Layer | Format | Audience | Purpose |
|---|---|---|---|
| Board summary | 2–5 slides/pages | CEO, board | Drive the decision |
| Full analysis | 50–100+ pages | Operating team | Evidence and methodology |

These are synchronized projections of the same pyramid. Every board-layer item corresponds to a full-layer section.

### 1.8 A-Tier vs B-Tier Quality Markers

**A-Tier**:
- Answer-first (recommendation in first 2 slides)
- Specific and quantified ("14% CAGR" not "strong growth")
- Titles test passes
- Every key number triangulated from 3 sources
- Competing hypotheses addressed and ruled out
- Active, committed language throughout
- MECE decomposition at every level

**B-Tier failures**:
- Bottom-up narrative (conclusion at the end)
- Topic titles ("Market Overview")
- Redundant arguments (three bullets restating one idea)
- Vague quantification ("significant", "considerable")
- Missing implications (data presented without strategic consequence)
- Passive voice throughout

---

## Part 2: LLM Orchestration Techniques That Actually Work

### 2.1 Claims Verified from Research

**KILLED**: "Think step by step" improves small models — FALSE for <13B params. CoT hurts models below ~13B (legal reasoning: -37.2pp; medical: -5.16pp).

**KILLED**: Self-refine loops improve quality — FALSE without external feedback signal. LLMs cannot reliably detect their own errors. Self-bias causes score inflation while correctness stagnates.

**KILLED**: Multi-agent debate always helps — FALSE. Majority pressure creates echo chambers. Eloquent-but-wrong agents sway others. Use role specialization instead.

### 2.2 Self-Consistency Sampling (Highest ROI Technique)

Sample N outputs at temperature 0.7–0.9, majority-vote or aggregate:
- For Ollama: N=3–5 for most tasks
- Stop early at 80% agreement threshold
- Correct reasoning paths recur more reliably than incorrect ones
- Equivalent to ~30–40% quality gap closure with larger models

```python
# Pattern
answers = [generate(prompt, temperature=0.8) for _ in range(N)]
final = majority_vote(answers)
```

Temperature guidance: analytical/factual=0.6–0.7, creative/synthesis=0.8–1.0.

### 2.3 Evidence-First (RAG) Architecture

Without retrieval: small LLMs hallucinate ~21% of factual steps.
With hybrid BM25+dense retrieval + cross-encoder reranking: <7.5%.

**Evidence-first pattern**:
1. Retrieve top-k evidence chunks before generating
2. Generate with constraint: "Answer using ONLY the evidence below"
3. Hallucination check: verify each claim against source text

### 2.4 Five-Role Research Pipeline

The most effective multi-agent structure uses specialized, non-overlapping roles:

```
PLANNER:    decompose query into 4-6 MECE sub-questions
RESEARCHER: per sub-question, search + extract evidence (run in parallel)
SYNTHESIZER: merge findings, resolve contradictions, mark [CONFLICT:]
CRITIC:     external signal — identify unsupported claims, gaps, contradictions
REVISER:    fix each issue raised by critic, or explain why no fix needed
```

**Critical insight**: Critic provides EXTERNAL signal, not self-critique. This is the mechanism that bypasses the intrinsic self-correction failure.

### 2.5 Stopping Criteria for Refinement

Never use fixed iteration counts. Use:
- Score improvement < 5% vs previous → stop
- Revision introduces new contradictions → revert and stop
- Maximum 3 refinement rounds (beyond round 3, marginal returns → 0)
- "Three specific issues" rule: if critic can't find 3 issues, document is ready

### 2.6 Structured Output as Cognitive Scaffold

Forcing structured output makes models commit to explicit claims before generating prose:

```
CLAIM: [restate in one sentence]
EVIDENCE FOR (3 points max): [...]
EVIDENCE AGAINST (3 points max): [...]
CONFIDENCE: HIGH/MEDIUM/LOW
VERDICT: [one sentence conclusion]
CAVEAT: [one sentence most important limitation]
```

Structure forces evidence-gathering before verdict → reduces hallucination.

### 2.7 Context Management for Small Models

Effective context limits far below nominal window:
- 7B models: ~8K tokens practical limit
- 30B models: ~20K tokens practical limit
- Use hierarchical chunking: chunk → summaries → combine
- Map-Reduce: each sub-agent handles one chunk, synthesizer combines

### 2.8 G-Eval Quality Scoring

Correlation with human judgment: 0.514 Spearman (best available method).

Five dimensions (1-5 each):
1. **Factual Accuracy**: Claims grounded in evidence? Speculation labeled?
2. **Reasoning Quality**: Conclusions logically derived from evidence?
3. **Completeness**: All aspects of question addressed?
4. **Precision**: Claims specific rather than vague?
5. **Uncertainty Calibration**: Appropriate hedging on uncertain claims?

Rules:
- Always request justification alongside score (improves alignment with human judgment)
- Use different model/system prompt as judge (mitigates self-preference bias)
- Require 5% improvement before accepting revision

### 2.9 Priority Stack for Ollama Deployment

| Priority | Technique | Quality Gain | Cost |
|---|---|---|---|
| 1 | Evidence-first RAG with hybrid retrieval | Very High | Medium setup |
| 2 | Self-consistency sampling (N=3–5) | High | High compute |
| 3 | Structured output format forcing | Medium-High | Zero |
| 4 | Five-role multi-agent pipeline | High | High code |
| 5 | G-Eval quality gating | Medium | Medium |
| 6 | Hierarchical context compression | Medium | Low |
| 7 | CoT (30B+ only) | Medium (size-gated) | Zero |
| 8 | Debate (adversarial, not echo-chamber) | Low (failure-prone) | High |

---

## Part 3: Architecture Design — ConsultingResearchEngine

### 3.1 Pipeline Overview

```
Stage 1: SCQA Framing
  Input: research question
  Output: Situation, Complication, Question, governing thought hypothesis
  LLM calls: 1

Stage 2: MECE Issue Tree
  Input: question + SCQA
  Output: 4-6 MECE branches (each a testable hypothesis)
  MECE validation: check semantic overlap between branches
  LLM calls: 1 + 1 validation

Stage 3: Parallel Evidence Gathering
  For each branch:
    - Generate 2-3 search queries
    - Search web + BM25 knowledge base
    - Extract relevant evidence chunks
    - Self-consistency: synthesize evidence N=3 times, majority-vote key claims
  LLM calls: 4-6 × 2 = 8-12 (can be batched)

Stage 4: Competing Hypotheses Testing
  For each branch hypothesis:
    - Collect evidence FOR and AGAINST
    - Apply adversarial test: prompted to REFUTE
    - Classify: confirmed / refined / rejected
  LLM calls: 1 per branch + 1 summary = 5-7

Stage 5: Pyramid Assembly
  Input: branch findings + hypothesis tests
  - Synthesize governing thought (elevator test)
  - Order 3-5 supporting arguments by persuasive impact
  - Self-consistency: N=3 synthesis attempts, vote on claims
  LLM calls: 3 (self-consistency)

Stage 6: Action Title Generation
  Input: pyramid structure
  Output: action titles for every section
  - Validate: complete sentence, includes specific claim, <20 words
  LLM calls: 1

Stage 7: Quality Gate (G-Eval)
  Input: draft structure
  Output: quality scores 1-5 on 5 dimensions + issues list
  LLM calls: 1

Stage 8: Report Writing
  Input: validated structure + all evidence
  - Write executive summary (2-page layer)
  - Write full analysis (section by section)
  LLM calls: 2-3

Total: ~20-25 LLM calls
Estimated time: 5-15 minutes depending on model and depth
```

### 3.2 Report Structure

**Executive Layer (governs decisions)**:
```
[SCQA OPENING]
Situation: [1-2 sentences]
Complication: [1-2 sentences]
Question: [the central question]
Answer: [governing thought]

[KEY FINDINGS]
1. [Action title 1 — specific, quantified claim]
2. [Action title 2]
3. [Action title 3]

[RECOMMENDED NEXT STEPS]
1. [Specific action with owner + timeline]
2. [...]
3. [...]
```

**Full Analysis Layer (supports decisions)**:
```
1. [Context & Situation Assessment]
   Action title: [declarative sentence]
   Evidence: [...]

2. [Problem Diagnosis]
   Action title: [declarative sentence]
   Evidence: [...]

3-5. [One section per key finding]
   Action title: [declarative sentence]
   Evidence: [triangulated from 2+ sources]
   Confidence: HIGH/MEDIUM/LOW

6. [Alternatives Considered and Rejected]
   [Alternative 1]: rejected because [specific reason]
   [Alternative 2]: rejected because [specific reason]

7. [Recommendation & Rationale]
   [Governing thought expanded]
   [3-5 supporting arguments]

8. [Implementation Roadmap]
   [Phase 1 / Phase 2 / Phase 3 with milestones]

9. [Risks & Mitigations]
   [Risk 1]: probability X, impact Y, mitigation Z
```

### 3.3 Consulting Framework Selection by Report Type

| Report Type | Primary Framework | Secondary |
|---|---|---|
| `market` | Porter's 5 Forces + TAM/SAM/SOM | Industry lifecycle |
| `competitive` | 3C Analysis + capability benchmarking | Competitor mapping |
| `strategy` | BCG Matrix / Ansoff + scenario planning | SCQA + issue tree |
| `operational` | Value chain + process maturity (CMMI) | Benchmarking |
| `technology` | Build/Buy/Partner + capability maturity | NTIV |
| `ma` | Synergy analysis + ODD | 7S model |

---

## Part 4: Implementation in Thuon

### 4.1 New Capability: `consulting_research_engine.py`

Implements the 8-stage pipeline above. Key methods:
- `research(question, industry, report_type, output_format)` → main entry point
- `_frame_scqa(question)` → structured SCQA output
- `_build_issue_tree(question, scqa)` → MECE branches with hypotheses
- `_gather_evidence(branch, search_queries)` → evidence-first with self-consistency
- `_test_hypothesis(branch, evidence)` → adversarial verification
- `_mece_validate(branches, findings)` → overlap/gap check
- `_pyramid_synthesize(question, findings)` → self-consistency N=3 synthesis
- `_generate_action_titles(sections)` → declarative title generation
- `_quality_gate(draft)` → G-Eval scoring
- `_write_report(...)` → two-layer output

### 4.2 Integration with Existing System

- Adds `consulting` depth level to `research_assistant.py`
- Registers in `CAPABILITY_REGISTRY` in `web_app.py`
- Uses existing `search_engine`, `ai_engine`, `rag_engine` deps
- Output includes `report_md` field for export to neditor

### 4.3 What Makes This Different from Existing DeepResearcher

| Dimension | `DeepResearcher` | `ConsultingResearchEngine` |
|---|---|---|
| Structure | Bottom-up summary | Pyramid Principle (answer first) |
| Decomposition | Sequential sub-questions | MECE issue tree with hypothesis testing |
| Evidence | Single-pass synthesis | Evidence-first + self-consistency N=3 |
| Verification | None | Adversarial hypothesis testing + external critic |
| Quality gate | None | G-Eval 5-dimension scoring |
| Report format | JSON blob | Two-layer (executive + full analysis) |
| Action titles | None | Every section has a declarative title |
| Alternatives | None | Competing hypotheses explicitly ruled out |
| MECE check | None | Semantic overlap validation before synthesis |
| Frameworks | None | Consulting frameworks matched to report type |

---

## Key Sources

**Consulting methodology**:
- Minto, B. — The Pyramid Principle
- StrategyU — SCQA and Pyramid Principle integration
- SlideWorks — McKinsey action titles guide
- Deckary — Executive summary architecture
- FourWeekMBA — 43 consulting frameworks
- McKinsey, BCG, Oliver Wyman public methodology documents

**LLM orchestration**:
- Wei et al. 2022 — Chain-of-Thought Prompting (arXiv:2201.11903)
- Mind Your Step — CoT failure modes in small models (OpenReview)
- Kamoi et al. TACL 2024 — LLM self-correction limitations
- Huang et al. ICLR 2024 — SELF-REFINE analysis
- Talk Isn't Always Cheap — Multi-agent debate failure modes (arXiv:2509.05396)
- Buffer of Thoughts — NeurIPS 2024
- MEGA-RAG — Hallucination mitigation (PMC:12540348)
- Confident AI — LLM-as-a-Judge complete guide
- PROTEA — Offline evaluation for multi-agent workflows (arXiv:2605.18032)

**AI deep research architectures**:
- Zylos AI — Deep research agent architectures survey (2026)
- ByteByteGo — OpenAI/Gemini/Claude deep research comparison
- Stanford STORM — Structured Online Research for Multi-perspective reports

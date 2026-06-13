# Small LLM Optimization: Techniques That Work

**Date**: 2026-06-13  
**Context**: Findings from building `ConsultingResearchEngine` — producing McKinsey-grade output from Ollama models (7B–70B) through orchestration rather than model upgrades.

---

## What Actually Works

### 1. Self-Consistency Sampling (Highest ROI)

Run the same synthesis prompt N=3 times at temperature 0.7–0.9, then majority-vote or aggregate key claims. Correct reasoning paths recur more reliably than incorrect ones.

- Closes ~30–40% of the quality gap vs larger models
- Stop early at 80% agreement threshold
- N=3–5 for Ollama; beyond N=5 marginal returns drop sharply
- Temperature guidance: analytical/factual = 0.6–0.7, creative/synthesis = 0.8–1.0

**Where used**: `_pyramid_synthesize()` and `_gather_evidence()` in `consulting_research_engine.py`.

### 2. Evidence-First (RAG Before Generation)

Retrieve search results *before* any LLM call. Pass chunks as grounded context with an explicit constraint: `"Answer using ONLY the evidence below"`.

- Without retrieval: small LLMs hallucinate ~21% of factual steps
- With hybrid BM25+dense retrieval + cross-encoder reranking: <7.5%
- Never ask a small model to recall facts from weights — give it the evidence

**Where used**: Every `_gather_evidence()` call searches first, then synthesizes over the retrieved chunks.

### 3. Structured Output as Cognitive Scaffold

Force the model to fill explicit fields before generating prose. Structure forces evidence-gathering *before* verdict, which reduces hallucination.

Effective schema shape:
```
CLAIM:           [one sentence]
EVIDENCE_FOR:    [3 points max]
EVIDENCE_AGAINST:[3 points max]
CONFIDENCE:      HIGH / MEDIUM / LOW
VERDICT:         [one sentence conclusion]
CAVEAT:          [most important limitation]
```

- Zero cost to implement
- Eliminates vague hedged output ("may suggest", "could potentially")
- Works where CoT fails — model commits to structure before reasoning

### 4. Decomposed Pipeline — One Tight Scope Per Call

Instead of one large "write a consulting report" prompt, break into 20–25 focused calls. Each fits in the model's practical context window (~8K tokens for 7B, ~20K for 30B).

The 8-stage pipeline in `consulting_research_engine.py`:
```
Stage 1:  SCQA framing           (1 LLM call)
Stage 2:  MECE issue tree        (2 calls: generate + validate)
Stage 3:  Evidence gathering     (4–6 calls, one per branch)
Stage 4:  Hypothesis testing     (1 call per branch)
Stage 5:  Pyramid synthesis      (3 calls: self-consistency N=3)
Stage 6:  Action title generation(1 call)
Stage 7:  Quality gate (G-Eval)  (1 call)
Stage 8:  Report writing         (2–3 calls)
```

Each call receives only what it needs. Context never accumulates across stages.

### 5. No Chain-of-Thought for Small Models

CoT provably *hurts* models below ~13B parameters:
- Legal reasoning: **−37.2 percentage points**
- Medical reasoning: **−5.16 percentage points**

Source: "Mind Your Step" (OpenReview). The model lacks the internal capacity to maintain a coherent reasoning chain — the scaffold becomes noise.

**Use instead**: Structured output (above) + self-consistency sampling.

### 6. External Critic Role (Not Self-Refine)

Self-refine loops don't work — LLMs cannot reliably detect their own errors, and self-bias causes score inflation while correctness stagnates (Kamoi et al. TACL 2024, Huang et al. ICLR 2024).

The mechanism that actually works: a separate critic with a *different system prompt* as an external signal. The critic is prompted to find issues, not to evaluate quality — an asymmetric adversarial role.

**Where used**: `_quality_gate()` uses a distinct system prompt from the rest of the pipeline.

### 7. Robust JSON Extraction

Small models frequently wrap JSON in prose or markdown code fences. A greedy regex `re.search(r'\{.*\}', text, re.DOTALL)` silently returns garbage when the response contains any trailing `{}` after the main object (e.g. a code example).

Use balanced-brace depth-counting instead:

```python
def _extract_span(text, open_ch, close_ch):
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == open_ch:
            if start is None: start = i
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i+1]
    return None
```

This is implemented in `core/llm_utils.py` as `extract_json()` and `extract_json_array()` and used across all 18+ new capability files.

### 8. Hierarchical Context Compression

Effective context limits are far below nominal window sizes:
- 7B models: ~8K tokens practical limit
- 30B models: ~20K tokens practical limit

Pattern: chunk → per-chunk summary → combine summaries for synthesis. Never pass the full corpus to the synthesis call.

---

## What We Explicitly Killed

| Technique | Why It Fails |
|---|---|
| "Think step by step" (CoT) | Hurts <13B models; −37pp on legal reasoning |
| Self-refine loops | LLMs can't detect own errors; self-bias inflates scores, correctness stagnates |
| Multi-agent debate | Eloquent-but-wrong agents sway others; majority pressure creates echo chambers, not accuracy |
| Single large prompt | Exceeds practical context window; model loses coherence across long contexts |
| Greedy regex JSON extraction | Silently returns wrong object when response has trailing braces |

---

## Priority Stack for Ollama Deployment

| Priority | Technique | Quality Gain | Cost |
|---|---|---|---|
| 1 | Evidence-first RAG with retrieval | Very High | Medium setup |
| 2 | Self-consistency sampling (N=3–5) | High | ~3× compute |
| 3 | Structured output format forcing | Medium-High | Zero |
| 4 | Decomposed pipeline (one scope per call) | High | Medium code |
| 5 | External critic (G-Eval quality gate) | Medium | Medium |
| 6 | Hierarchical context compression | Medium | Low |
| 7 | CoT (30B+ only) | Medium (size-gated) | Zero |
| 8 | Debate (adversarial, not echo-chamber) | Low (failure-prone) | High |

---

## Sources

- Wei et al. 2022 — Chain-of-Thought Prompting (arXiv:2201.11903)
- Mind Your Step — CoT failure modes in small models (OpenReview)
- Kamoi et al. TACL 2024 — LLM self-correction limitations
- Huang et al. ICLR 2024 — SELF-REFINE analysis
- MEGA-RAG — Hallucination mitigation (PMC:12540348)
- Confident AI — LLM-as-a-Judge complete guide

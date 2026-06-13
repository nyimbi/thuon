# Long-Form Document Generation with LLMs: Research Findings

**Date**: 2026-06-13
**Purpose**: Inform implementation of 200+ page document generation in Thuon platform
**Summary**: Synthesizes five parallel research tracks into an actionable architecture

---

## Table of Contents

- [Key Constraints](#key-constraints)
- [Hierarchical Planning Techniques](#hierarchical-planning-techniques)
- [Context Management Architecture](#context-management-architecture)
- [Consistency Enforcement](#consistency-enforcement)
- [Cross-References, ToC, and Indexing](#cross-references-toc-and-indexing)
- [Visual Elements: Tables, Charts, Diagrams](#visual-elements-tables-charts-diagrams)
- [PDF and DOCX Rendering](#pdf-and-docx-rendering)
- [qwen3.5 and Ollama Integration](#qwen35-and-ollama-integration)
- [Recommended Implementation Stack](#recommended-implementation-stack)
- [References](#references)

---

## Key Constraints

### Output token ceilings are a training data problem, not architecture

The 2K-word ceiling in instruction-tuned models is an SFT data artifact. **LongWriter** (ICLR 2025, arXiv:2408.07055) proved this: fine-tuning a 9B model on 6K examples of 2K–32K word outputs unlocks coherent 32K-word generation. That fine-tuned 9B model scores 84.0 on LongBench-Write vs. Claude 3.5 Sonnet's 80.7.

**Implication for Thuon**: Use word-count targets in section prompts (`"Target: 1500 words"`) and decomposed serial generation, not single-call generation. Frontier output limits are now 128K–384K tokens, so the mechanical ceiling is gone — coherence is the remaining problem.

### "Lost in the middle" is real and severe

Liu et al. (TACL 2024): >30% accuracy drop when relevant content moves from position 1 to a middle position in a 20-document context. Llama 3.1-70B drops from 96.5 to 66.6 on RULER over 128K tokens (−30 pts).

**Mitigation**: Front-load and back-load critical instructions. Never bury constraints in the middle of the context.

### 256K context window enables editing, not single-shot generation

200 pages ≈ 80K–100K tokens of output. A 256K window fits the whole document for reading tasks. For generation, single-pass coherence collapses without a planning phase. **Treat 256K as enabling context-aware multi-pass continuation and editing, not one-shot synthesis.**

---

## Hierarchical Planning Techniques

All high-performing systems use the same decomposition:

```
Topic → Outline (H1/H2/H3) → Section plan (key points + dependencies)
→ Paragraph plan (claim + word-count target) → Text
```

### Best Systems (Ranked by Performance)

**1. RaPID** (ACL 2025, arXiv:2503.00751) — Current SOTA for research-style documents
- Extracts "attributes" (indivisible concepts) from the outline
- Generates targeted retrieval queries per attribute
- Constructs a **DAG of inter-section dependencies**
- Generates sections in topological order (each section receives prerequisite sections as live context)
- Significantly better than STORM on outline recall, factuality, and API efficiency

**2. DOME** (NAACL 2025, arXiv:2412.13575) — Best consistency enforcement
- Maintains a rough outline fixed at start + a detailed outline updated after each section
- Backed by a **temporal knowledge graph** that flags consistency violations before each new section
- Most sophisticated consistency enforcement at the planning level

**3. STORM** (NAACL 2024, arXiv:2402.14207) — Widely-used baseline
- Multi-perspective Q&A → outline → parallel section writing pipeline
- Primary failure mode: "red herring over-association" (retrieves and embeds unrelated facts)
- Still useful but RaPID dominates for factual documents

**4. AgentWrite / LongWriter** (ICLR 2025) — Best for coherence
- Decompose task into N subtasks with explicit per-section word-count targets
- Execute serially with all prior sections as context
- Expensive but produces superior coherence

**5. ConvergeWriter** (arXiv:2509.12811) — Best coverage
- Retrieve exhaustively first → cluster retrieved docs → let clusters define structure
- 80.14% coverage vs. STORM's 24.91% on WildSeek
- Optimal when corpus fidelity matters more than narrative coherence

### Practical Design for Thuon

Use **AgentWrite pattern** (serial generation, all prior sections as context) combined with **DOME outline updating** (refresh detailed outline after each section):

```
Phase 1: Generate hierarchical outline (H1/H2/H3) with word targets per section
Phase 2: Pre-assign all exhibit numbers (LaTeX-style two-pass)
Phase 3: Generate sections serially:
         - Each section receives: rolling summaries + entity state + RefRegistry
         - After each section: update entity state, check consistency
Phase 4: Post-processing: resolve cross-reference tokens, generate ToC
Phase 5: Optional: PDF render via Pandoc
```

---

## Context Management Architecture

Five-layer memory stack for 100+ page generation:

| Layer | Implementation | Scope |
|:------|:--------------|:------|
| Short-term | Last N paragraphs verbatim | Current section |
| Working summary | Compressed chapter summary in-prompt | Current chapter |
| Long-term semantic | FAISS VectorDB (optional) | Cross-chapter |
| Structured state | Entity/world-state JSON | Document lifetime |
| Outline | Dynamic 2-level plan | Document lifetime |

**RecurrentGPT** (arXiv:2305.13304) is the canonical implementation of this pattern.

**InftyThink** (arXiv:2503.06692) adds sawtooth compression — but requires SFT on 540K examples; zero-shot degrades quality. Use rolling summaries instead.

### Practical Rolling Context

Keep last 3 section summaries (≤600 chars each) + full text of immediate predecessor (≤1500 chars) in the prompt for each new section. Cap total rolling context at ≤4000 chars.

---

## Consistency Enforcement

Ranked by verified impact:

### 1. Entity/World-State JSON (highest leverage, zero cost)

Model entity states as absorbing Markov states (active → mentioned → established, no reversal). Inject into every generation pass:

```json
{
  "defined_terms": {"Total Addressable Market": "global potential revenue opportunity"},
  "key_statistics": ["market grows at 12% CAGR", "$45B TAM by 2030"],
  "entities_mentioned": ["Acme Corp", "AWS", "ISO 27001"],
  "claims_made": ["enterprise segment drives 67% of revenue"]
}
```

### 2. Tell + Show Prompting

Combine explicit style directives + 2–3 concrete examples in every generation pass. Either alone drifts.

### 3. Iterative Self-Contradiction Removal

ChatProtect (arXiv:2305.15852): every ~1K tokens, prompt the model to find and rewrite contradictory sentence pairs. Reduces contradictions 76–89% depending on model. Black-box compatible.

### 4. Contrastive Search Decoding

Use `penalty_alpha` + `top_k` for repetition prevention. Also prepend each section:
> *"The following section introduces new information not already covered. Previously covered: [summary]."*

### 5. Atomic Self-Consistency (ACPO)

Sample 3–5 times, keep only facts appearing in ≥2/3 samples. +1.95 factual precision, no fine-tuning, but 3–5× inference cost. Apply only to key sections (executive summary, conclusions).

---

## Cross-References, ToC, and Indexing

### The Two-Pass Pattern (LaTeX-style)

LaTeX compiles twice: first pass writes `.aux` (labels → numbers), second pass substitutes. Replicate exactly:

1. **Pre-pass**: build `RefRegistry` from `DocumentPlan` before any LLM call — assigns all section numbers and exhibit numbers upfront
2. **Generation**: LLM writes tokens `[[SEC:id]]` and `[[EX:id]]`, never bare numbers
3. **Post-pass**: resolve all tokens, audit for leakage (bare numbers = generation error)

```python
# Pre-generation: assign all numbers upfront
class RefRegistry:
    sections: dict[str, str]   # "intro" → "1", "methods" → "2.1"
    exhibits: dict[str, str]   # "revenue_chart" → "Exhibit 1"

# LLM prompt injection
PROMPT_BLOCK = """
REFERENCE REGISTRY (use ONLY these tokens — NEVER write bare numbers):
  [[SEC:executive_summary]] → Section 1
  [[SEC:market_overview]] → Section 2
  [[EX:revenue_chart]] → Exhibit 1
  [[EX:cost_matrix]] → Exhibit 2
"""

# Post-processing resolver
def resolve_tokens(text: str, reg: RefRegistry) -> str:
    def sub(m):
        kind, key = m.group(1), m.group(2)
        if kind == 'SEC': return reg.sections.get(key, f'[§{key}]')
        if kind == 'EX':  return reg.exhibits.get(key, f'[Exhibit:{key}]')
        return m.group(0)
    return re.sub(r'\[\[([A-Z]+):([a-z_0-9]+)\]\]', sub, text)
```

### Exhibit Numbering: McKinsey Convention

Single flat counter for all visual elements: `Exhibit 1` (chart), `Exhibit 2` (table), `Exhibit 3` (matrix). Not separate Figure N / Table N counters. Rationale: slide decks and reports get printed/shuffled; a single sequence is unambiguous.

### Auto-ToC from Heading Structure

```python
def _github_slug(text: str) -> str:
    text = normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s]+', '-', text).strip('-')

def parse_headings(markdown: str) -> list[dict]:
    headings, seen = [], {}
    for line in markdown.splitlines():
        m = re.match(r'^(#{1,6})\s+(.+?)(?:\s+\{#([\w-]+)\})?$', line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            anchor = m.group(3) or _github_slug(text)
            if anchor in seen:
                seen[anchor] += 1
                anchor = f'{anchor}-{seen[anchor]}'
            else:
                seen[anchor] = 0
            headings.append({'level': level, 'text': text, 'anchor': anchor})
    return headings
```

Page numbers in pageless markdown: use section numbers + `#anchor` links. If hard page numbers needed, render to PDF with WeasyPrint/Pandoc first, extract via PyMuPDF.

### Index Building: Three-Tier Pipeline

```python
# Tier 1: YAKE (statistical, fast) — candidate generation
import yake
extractor = yake.KeywordExtractor(n=3, top=50, dedupLim=0.7)

# Tier 2: KeyBERT (semantic reranking + diversity)
from keybert import KeyBERT
kw_model = KeyBERT('all-MiniLM-L6-v2')
keywords = kw_model.extract_keywords(text, use_mmr=True, diversity=0.5)

# Tier 3: LLM normalization pass — canonical forms, hierarchy, see-also
```

### pandoc-crossref (best off-the-shelf)

For pipelines ending in Pandoc: `pandoc-crossref` handles all cross-references natively.

```yaml
# Pandoc metadata block
figureTitle: "Exhibit"
figPrefix: "Exhibit"
tblPrefix: "Exhibit"
cref: true
```

LLM writes `@fig:revenue_chart`; pandoc resolves to `Exhibit 1`.

---

## Visual Elements: Tables, Charts, Diagrams

### Markdown Tables (GFM)

Best practices for LLM-generated tables:
- Pad cells with spaces for visual alignment (aids model self-checking)
- Hard limit: 5–6 columns; beyond that split or use HTML `<table>`
- Never leave cells blank — use `N/A` or `—`
- Always include a `Source` column in financial tables
- Action titles on exhibit captions (McKinsey/BCG style): "Enterprise segment drove 12% revenue beat" not "Q3 Results"

### Mermaid Diagrams

Mermaid 11.x supports: `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `pie`, `quadrantChart`, `gantt`, `timeline`, `erDiagram`, `classDiagram`, `xychart-beta`, `sankey-beta`.

Renders natively in: GitHub, GitLab, Notion, Obsidian, Quarto, Typora.

**BCG 2×2 pattern** via `quadrantChart`:
```
quadrantChart
    title Strategic Priority Matrix
    x-axis Low Effort --> High Effort
    y-axis Low Impact --> High Impact
    quadrant-1 Quick Wins
    quadrant-2 Major Projects
    Auth Redesign: [0.3, 0.8]
    API v2: [0.7, 0.9]
```

**LLM reliability**: GPT-4o and Claude 3.5+ generate valid Mermaid for flowchart/sequence reliably. Complex types (C4, sankey) need explicit node declarations and CoT in the prompt.

### ASCII Charts (Terminal / Code Blocks)

Use **`plotext`** — zero dependencies, matplotlib-like API, actively maintained:

```python
import plotext as plt, io, sys

def ascii_bar_chart(labels, values, title) -> str:
    old_stdout, sys.stdout = sys.stdout, io.StringIO()
    plt.bar(labels, values)
    plt.title(title)
    plt.show()
    result, sys.stdout = sys.stdout.getvalue(), old_stdout
    return f"```\n{result}\n```"
```

### Vega-Lite: Recommended for Agent Pipelines

LLM generates declarative JSON spec; renderer produces chart. Separation of data from visualization prevents hallucinated numbers:

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "data": {"values": [{"segment": "Enterprise", "revenue": 45.2}]},
  "mark": "bar",
  "encoding": {
    "x": {"field": "segment", "type": "nominal"},
    "y": {"field": "revenue", "type": "quantitative"}
  }
}
```

### Preventing Hallucinated Numbers (Multi-Layer)

| Layer | Technique |
|:------|:----------|
| Prompt | "Use only the provided data. Mark any missing values N/A." |
| Structured output | JSON schema with `type: number`, `minimum`, `maximum` |
| RAG | Retrieve exact figures before generation |
| Architecture | LLM generates structure/labels only; numbers come from verified DB query |
| Post-gen | Check row/column sums; flag implausible YoY deltas (>200% = verify) |

---

## PDF and DOCX Rendering

### Recommended Stack (2025-2026)

**Tier 1: Typst via Pandoc 3** (recommended for new pipelines)
- Single ~40 MB binary vs. 3–5 GB TeX install — CI/CD friendly
- 27× faster than XeLaTeX (357 ms vs. 9.65 s on 4-page doc)
- Template syntax: clean scripting (conditionals, loops, native JSON ingestion)
- Headers/footers/page numbers are first-class

```bash
pandoc report.md --to=typst --pdf-engine=typst --template=corporate.typ -o report.pdf
```

From Python:
```python
import pypandoc
pypandoc.convert_file(
    'report.md', 'pdf',
    outputfile='report.pdf',
    extra_args=['--to=typst', '--pdf-engine=typst', '--template=corporate.typ']
)
```

**Tier 2: Pandoc + Eisvogel + Tectonic** (maximum typographic quality)
- Tectonic is ~40 MB and auto-downloads packages — the "3–5 GB TeX" objection disappears
- YAML frontmatter for widow/orphan control: `\widowpenalty=10000`
- Best output quality

**Tier 3: WeasyPrint** (CSS-first, pure Python)
```python
from weasyprint import HTML
HTML(string=html, base_url='file:///assets/').write_pdf('report.pdf')
```

CSS for print:
```css
@page {
  size: A4;
  margin: 25mm 20mm;
  @top-right  { content: string(chapter-title); font-size: 8pt; }
  @bottom-center { content: counter(page) " / " counter(pages); }
}
h1 { string-set: chapter-title content(text); break-before: page; }
p  { orphans: 3; widows: 3; }
```

**DOCX** (client deliverables):
```python
pypandoc.convert_file('report.md', 'docx', outputfile='report.docx',
                      extra_args=['--reference-doc=corporate-template.docx'])
```

### Mermaid Pre-rendering (all pipelines)

Always pre-render Mermaid blocks before PDF step:
- `mmdc` (official, Node.js): `npm install -g @mermaid-js/mermaid-cli`
- Python-native: `pip install mmdc` (no Node.js required)
- SVG output preferred over PNG — resolution-independent, scales cleanly

---

## qwen3.5 and Ollama Integration

### Model Specs (as of Feb 2026)

Ollama sizes: `0.8b`, `2b`, `4b`, `9b`, `27b`, `35b` (MoE), `122b` (MoE)
All variants: **256K context window** (GDN hybrid architecture)

Source: https://ollama.com/library/qwen3.5

### Context Window in Practice

- 256K tokens ≈ 190,000 words / 700 pages — sufficient for any document generation task
- Throughput: 19× faster than Qwen3-Max at 256K context (GDN architecture)
- Coherence degrades with model size: 4B-class fails ~37% at 200K tokens; 27B+ stays >95%
- "Lost in the middle" confirmed — content at 20–70% depth gets lower retrieval accuracy in smaller models

**Recommended model selection**:
| Scenario | Model | Context |
|:---------|:------|:--------|
| Default | `qwen3.5:9b` | 64K ctx | 24GB GPU |
| Long-doc mode | `qwen3.5:27b` | 128K ctx | 32–40GB |
| Low-resource | `gemma3:12b` | 64K ctx | 8GB |
| Quality ceiling (English) | `llama3.3:70b` | 128K ctx | 48GB+ |

### Critical: num_ctx Default is 4,096

**Ollama silently truncates context to 4,096 tokens by default on GPUs under 24GB VRAM.**

Must be set explicitly via:
```json
{"options": {"num_ctx": 131072}}
```

Or in a Modelfile:
```
PARAMETER num_ctx 131072
```

Source: https://github.com/ollama/ollama/issues/12463

### Thinking Mode: Disable for Document Generation

qwen3.5 has a "thinking" mode (`/think` prefix). **Disable for prose generation** — it adds latency and token cost with no coherence benefit for narrative writing.

Disable via `/no_think` prefix in the prompt, or `enable_thinking=False` in the chat template.

**Re-enable only for**: structural planning/outline generation (where analytical reasoning benefits).

Source: https://www.alibabacloud.com/help/en/model-studio/deep-thinking

---

## Recommended Implementation Stack

Based on research synthesis, the optimal stack for Thuon:

### Generation Architecture

```
1. Plan (1 LLM call, /think enabled):
   - Full hierarchical outline (H1/H2/H3)
   - Word targets per section
   - Exhibit specs (type, title, description)

2. Pre-number (0 LLM calls):
   - RefRegistry assigns all section/exhibit numbers
   - Builds token→number mapping

3. Generate sections serially (/no_think):
   - Rolling context: last 3 summaries + prev section excerpt
   - Entity state JSON injected each call
   - RefRegistry prompt block injected each call
   - Word target enforced in prompt
   - Key sections: self-consistency N=3, pick longest

4. Post-process (0 LLM calls):
   - Resolve [[SEC:*]] / [[EX:*]] tokens
   - Audit for bare number leakage
   - Generate ToC from heading structure
   - Assemble final document

5. Optional PDF (subprocess):
   - pandoc with --to=typst (recommended)
   - Fallback: WeasyPrint HTML pipeline
```

### Visual Element Pipeline

```
For tables:    LLM generates GFM markdown table with source column
For diagrams:  LLM generates Mermaid fenced code block
For charts:    LLM generates Vega-Lite JSON spec → altair → SVG embed
              (or matplotlib → base64 SVG for simple bar/line)
```

### Anti-Hallucination Stack

```
1. Entity state JSON: prevents drift from established statistics
2. Structured output for tables: JSON schema with min/max on numeric fields
3. Source material in prompt context (when available)
4. Row/column sum validation for financial tables
5. Post-generation audit: regex for implausible numbers
```

---

## References

| Paper/Resource | URL | Key Finding |
|:--------------|:----|:------------|
| LongWriter (ICLR 2025) | arXiv:2408.07055 | Fine-tuning unlocks 32K-word coherent output; 9B beats Claude 3.5 |
| RaPID (ACL 2025) | arXiv:2503.00751 | DAG-based section dependencies, best recall/factuality |
| DOME (NAACL 2025) | arXiv:2412.13575 | Dynamic outline + temporal knowledge graph for consistency |
| STORM (NAACL 2024) | arXiv:2402.14207 | Multi-perspective Q&A → outline pipeline; red herring failure mode |
| ConvergeWriter | arXiv:2509.12811 | 80% coverage vs. STORM 25% on WildSeek |
| SurveyGen-I (IJCNLP-AACL 2025) | arXiv:2508.14317 | Memory module tracking terminology across sections |
| RAPTOR (ICLR 2024) | arXiv:2401.18059 | Recursive chunk clustering; +20% on QuALITY benchmark |
| ChatProtect | arXiv:2305.15852 | Self-contradiction removal; 76–89% reduction |
| RecurrentGPT | arXiv:2305.13304 | Canonical 5-layer memory stack for long-form generation |
| "Lost in the Middle" (TACL 2024) | Liu et al. | >30% accuracy drop for middle-position context |
| RIKER benchmark | arXiv:2601.08847 | Coherence degradation at long context by model size |
| Mind Your Step | OpenReview | CoT hurts <13B models: −37pp on legal reasoning |
| Qwen3.5 on Ollama | https://ollama.com/library/qwen3.5 | 256K context, all sizes |
| Ollama num_ctx issue | https://github.com/ollama/ollama/issues/12463 | Default 4096 tokens, must set explicitly |
| Typst automated PDF | https://typst.app/blog/2025/automated-generation/ | 27× faster than XeLaTeX |
| WeasyPrint Tips | https://doc.courtbouillon.org/weasyprint/v52.5/tips-tricks.html | CSS Paged Media support |
| Mermaid CLI | https://github.com/mermaid-js/mermaid-cli | mmdc for SVG/PNG rendering |
| Pandoc + Typst guide | https://slhck.info/software/2025/10/25/typst-pdf-generation-xelatex-alternative.html | Recommended pipeline |
| Spheron qwen3.5 guide | https://www.spheron.network/blog/deploy-qwen-3-5-gpu-cloud/ | Deployment specs |

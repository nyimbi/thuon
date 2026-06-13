# Qwen3.5 + Ollama: Practical Guide for Thuon's Document Engine

*Research date: June 2026*

---

## 1. Model Family — What Actually Exists

"Qwen3.5" is **not** a rescaled Qwen3. It is a distinct architecture released February–March 2026 using **Gated DeltaNet (GDN) hybrid attention** — 75% GDN layers, 25% standard attention — combined with sparse MoE. It is natively multimodal (text + image + video) and far more throughput-efficient than Qwen3 at long context.

### Sizes Available on Ollama (`ollama pull qwen3.5:<tag>`)

| Tag | Disk (Ollama) | Architecture | Active Params | Context |
|-----|--------------|-------------|--------------|---------|
| `0.8b` | 1.0 GB | Dense | 0.8B | 256K |
| `2b` | 2.7 GB | Dense | 2B | 256K |
| `4b` | 3.4 GB | Dense | 4B | 256K |
| `9b` / `latest` | 6.6 GB | Dense | 9B | 256K |
| `27b` | 17 GB | Dense | 27B | 256K |
| `35b` | 24 GB | MoE (35B/3B active) | 3B active | 256K |
| `122b` | 81 GB | MoE (122B/10B active) | 10B active | 256K |
| `cloud` / `397b-cloud` | API | MoE (397B/17B active) | 17B active | 256K |

MLX variants (Apple Silicon, `-mlx` suffix) are text-only; all others support vision input.

**Consumer hardware sweet spots:**
- **8 GB VRAM / M-series unified memory:** `0.8b`, `2b`, `4b` — capable for short-to-medium documents, limited coherence at long context
- **16–24 GB VRAM (RTX 4090, M3 Max 36GB):** `9b` — best local single-GPU option for document generation
- **32–40 GB unified (M3 Ultra / M4 Max 48GB):** `27b` — recommended for long, complex documents
- **48–80 GB (A100/H100):** `35b` (MoE, 24 GB on disk but needs full 35B in VRAM) or `122b`

---

## 2. 256K Context in Practice

### Capacity
At Ollama's default of 3–4 tokens/word:
- **256K tokens ≈ 190,000 words ≈ 700–750 pages** of dense prose
- A typical 50-page technical report ≈ 35K tokens; a 200-page book ≈ 140K tokens
- At 256K you can fit the entire Thuon platform codebase + a large context document simultaneously

### Performance at Long Context
Qwen3.5's GDN architecture was explicitly designed to solve throughput collapse at long contexts:
- At 32K context: **8.6× faster** than Qwen3-Max
- At 256K context: **19× faster** than Qwen3-Max

**Coherence degradation is model-size dependent** (RIKER benchmark data):
- `Qwen3-4B` equivalent: coherence failure rate goes from **0.3% at 32K → 37% at 200K** (123× increase)
- Large models (27B+): coherence failure remains low even at 200K+
- "Lost in the middle" is a real phenomenon — retrieval accuracy drops for content at 20–70% depth in the context, affecting smaller models more severely

**Practical ceiling for document generation:**
- `9b`: Reliable up to ~64K, degrading above 128K
- `27b+`: Reliable across the full 256K range for structured generation tasks
- Thinking mode (`<think>` blocks) slightly degrades long-context recall; disable it for generation tasks (see §4)

---

## 3. Ollama Configuration for 256K Context

### Default Behavior — Silent Truncation Risk
Ollama's default `num_ctx` depends on VRAM:
- Under 24 GB VRAM: **4,096 tokens** (silently truncates)
- 24–48 GB VRAM: **32,768 tokens**
- 48 GB+ VRAM: **262,144 tokens**

**This is critical:** Ollama silently drops content exceeding `num_ctx` from the start of context with no error. A document engine must explicitly set this parameter.

### Method 1: Modelfile (Recommended for Thuon)

```
FROM qwen3.5:9b
PARAMETER num_ctx 131072
PARAMETER temperature 0.7
PARAMETER top_p 0.8
PARAMETER top_k 20
SYSTEM "You are a precise technical document writer. Output structured, factually grounded content only."
```

```bash
ollama create thuon-docgen -f Modelfile
ollama run thuon-docgen
```

Use `num_ctx 131072` (128K) for the 9b on 24GB VRAM as a practical ceiling; use `num_ctx 262144` (256K) for 27b on 48GB+.

### Method 2: Per-Request API Option (Programmatic)

```python
import httpx

async def generate_document(prompt: str, context_tokens: int = 131072) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": [{"role": "user", "content": prompt}],
                "options": {
                    "num_ctx": context_tokens,
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 20,
                },
                "stream": False,
            },
            timeout=600.0,
        )
        return response.json()["message"]["content"]
```

### Method 3: Environment Variable (Server-Wide)

```bash
OLLAMA_CONTEXT_LENGTH=131072 ollama serve
```

---

## 4. Thinking Mode — Enable/Disable for Document Generation

Qwen3.5 has **thinking enabled by default**. It generates a `<think>...</think>` block before the response, consuming tokens on internal chain-of-thought reasoning.

### For Document Generation: Disable Thinking

Thinking mode adds latency and token cost with **minimal benefit** for structured prose generation (it helps with math/code reasoning, not narrative coherence). Disable it.

**Via chat template kwargs (transformers/vLLM):**
```python
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False
)
```

**Via Ollama system prompt (soft disable):**
Add `/no_think` to the system prompt or prepend it to user messages. Note: the official `/no_think` soft switch is a Qwen3 feature; Qwen3.5 support varies by deployment — test before relying on it.

**Via Modelfile (hardest, most reliable via Ollama):**
```
FROM qwen3.5:9b
PARAMETER num_ctx 131072
SYSTEM "/no_think You are a document writer..."
```

**Sampling parameters:**
- Non-thinking mode: `temperature=0.7`, `top_p=0.8`, `top_k=20`
- Thinking mode (when needed for outlines/planning): `temperature=0.6`, `top_p=0.95`, `top_k=20`
- Never use greedy decoding (`temperature=0`) — causes repetition loops

**When to use thinking mode:** Generating a document *outline* or *structural plan* from a complex brief. Then disable it for section-by-section prose generation.

---

## 5. Coherence Across 100K+ Token Contexts

Key findings from benchmarks:

| Model | At 32K | At 128K | At 200K+ |
|-------|--------|---------|----------|
| 4B-class | ~99.7% | ~70% | ~63% |
| 9B-class | ~99.8% | ~85% | ~75% |
| 27B+ | ~99.9% | ~97%+ | ~95%+ |

**Mitigation strategies for Thuon:**

1. **Chunked generation:** Don't generate a 200-page document in a single call. Generate section-by-section with a rolling summary injected as context. Keeps each call under 32K tokens.

2. **Structured prompting:** Use explicit section markers in system prompt (`## Section 3: Technical Architecture`) — structured generation outperforms free-form at long context.

3. **Context compression:** Summarize completed sections before appending to context. A 5K-word section compresses to ~500 tokens of key points without losing continuity.

4. **Positional anchoring:** Re-state key facts and constraints at the *end* of the context window, not just the beginning. Models attend better to recent tokens — exploit this.

---

## 6. Alternative Models for Long-Form Document Generation

| Model | Context | Best VRAM | Strengths | Weaknesses |
|-------|---------|-----------|-----------|------------|
| `qwen3.5:9b` | 256K native | 16GB | Best context/VRAM ratio, multimodal | Coherence degrades >64K |
| `qwen3.5:27b` | 256K native | 32–40GB | Reliable at 256K, fast MoE throughput | Needs substantial hardware |
| `llama3.3:70b` | 128K | 48GB+ | Best overall quality for English docs | No 256K, large footprint |
| `gemma3:27b` | 128K | 24–32GB | Strong instruction following, multilingual | 128K ceiling |
| `gemma3:12b` | 128K | 8–12GB | QAT variants: near-BF16 quality at Q4 | 128K ceiling |
| `mistral-small3.2` | varies | 14GB | Fast, near-70B quality for drafting | Less depth on complex docs |

**Recommendation for Thuon's document engine:**
- **Default model:** `qwen3.5:9b` with `num_ctx 65536` — covers 95% of document generation tasks, runs on a single 24GB GPU
- **Long-document mode:** `qwen3.5:27b` with `num_ctx 131072` when generating reports > 50 pages
- **Fallback / low-resource:** `gemma3:12b` at `num_ctx 65536` on 8GB VRAM
- **Thinking disabled** across all generation calls; **thinking enabled** only for structural planning/outline generation phase

---

## 7. Integration Sketch for Thuon

```python
from enum import StrEnum

class DocGenMode(StrEnum):
	PLAN = "plan"       # thinking ON, short context
	WRITE = "write"     # thinking OFF, full context
	REVISE = "revise"   # thinking OFF, full context

OLLAMA_MODELS = {
	"small": "qwen3.5:9b",
	"large": "qwen3.5:27b",
	"fallback": "gemma3:12b",
}

CONTEXT_SIZES = {
	"small": 65_536,
	"large": 131_072,
	"fallback": 65_536,
}

async def doc_engine_call(
	prompt: str,
	mode: DocGenMode = DocGenMode.WRITE,
	tier: str = "small",
) -> str:
	options: dict = {
		"num_ctx": CONTEXT_SIZES[tier],
		"temperature": 0.6 if mode == DocGenMode.PLAN else 0.7,
		"top_p": 0.95 if mode == DocGenMode.PLAN else 0.8,
		"top_k": 20,
	}
	# Soft-disable thinking for write/revise modes
	if mode != DocGenMode.PLAN:
		prompt = "/no_think\n\n" + prompt

	async with httpx.AsyncClient() as client:
		resp = await client.post(
			"http://localhost:11434/api/chat",
			json={
				"model": OLLAMA_MODELS[tier],
				"messages": [{"role": "user", "content": prompt}],
				"options": options,
				"stream": False,
			},
			timeout=600.0,
		)
	return resp.json()["message"]["content"]
```

---

## Sources

- [Ollama qwen3.5 library page](https://ollama.com/library/qwen3.5)
- [Deploy Qwen 3.5 on GPU Cloud — Spheron Blog](https://www.spheron.network/blog/deploy-qwen-3-5-gpu-cloud/)
- [Qwen 3.5 Review 2026 — ComputerTech](https://computertech.co/qwen-3-5-review/)
- [Ollama 256K context issue #12463](https://github.com/ollama/ollama/issues/12463)
- [Ollama num_ctx configuration guide — Serverman](https://www.serverman.co.uk/ai/ollama/ollama-context-window/)
- [Qwen3.5 thinking mode — Alibaba Cloud docs](https://www.alibabacloud.com/help/en/model-studio/deep-thinking)
- [Disable thinking mode — GitHub discussion](https://github.com/QwenLM/Qwen3/discussions/1300)
- [Qwen3 Technical Report (arXiv)](https://arxiv.org/pdf/2505.09388)
- [RIKER benchmark — coherence at long context](https://arxiv.org/pdf/2601.08847)
- [Best Ollama Models 2026 — Morph](https://www.morphllm.com/best-ollama-models)
- [Qwen3.5-35B-A3B model card — HuggingFace](https://huggingface.co/Qwen/Qwen3.5-35B-A3B)

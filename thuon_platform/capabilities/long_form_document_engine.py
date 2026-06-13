# capabilities/long_form_document_engine.py
"""
Long-form document engine (v2) — generates 50,000–200,000-word (100–400+ page)
documents of consulting-grade quality from Ollama models.

Research basis (docs/research/long-document-generation.md):
  RaPID (ACL 2025), DOME (NAACL 2025), LongWriter (ICLR 2025),
  ChatProtect (arXiv:2305.15852), RAPTOR (ICLR 2024), ConvergeWriter (2025).

Full pipeline:
  Plan (/think) → topological sort by dependency →
  pre-number exhibits (LaTeX two-pass) →
  pre-generate all exhibits (dedicated calls: JSON→GFM table, focused Mermaid) →
  serial section generation (rolling context + entity state + optional RAG) →
  word-count enforcement (retry if <50% of target) →
  executive summary refinement (post-generation self-consistency N=3) →
  contradiction sweep (ChatProtect) →
  back-matter index (LLM term extraction) →
  ToC assembly → optional PDF (Pandoc Typst) / DOCX render

Key techniques:
  - RefRegistry: all section/exhibit numbers pre-assigned before any LLM call
  - Entity state: injected every section call — prevents statistical drift
  - Tokens [[SEC:id]] / [[EX:id]]: LLM never writes bare numbers
  - Self-consistency N=3 for is_key sections
  - Two-step tables: LLM → structured JSON → validated GFM markdown
  - Focused Mermaid: dedicated call, code-only, no prose
  - Word count enforcement: expansion retry on short output
  - Contradiction sweep: final cross-document consistency pass
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field

from core.ai_engine import AIModel


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SELF_CONSISTENCY_N     = 3
_ROLLING_SUMMARY_LIMIT  = 3
_MAX_CONTEXT_CHARS      = 4_000
_SUMMARY_MAX_CHARS      = 500
_DEFAULT_WORD_TARGET    = 50_000
_WORD_COUNT_MIN_RATIO   = 0.50    # retry if actual < 50% of target
_MAX_EXPAND_RETRIES     = 2
_INDEX_TERMS_TARGET     = 40
_OUTPUT_DIR             = Path(__file__).parent.parent / 'data' / 'long_documents'

_DOCUMENT_TYPE_GUIDES: dict[str, str] = {
	'report': (
		'Structure: Executive Summary → Introduction → Background → '
		'Analysis (3–5 major sections) → Findings → Recommendations → '
		'Conclusion → Appendices → Index. '
		'Data-driven. Each section has specific findings, not generic commentary.'
	),
	'whitepaper': (
		'Structure: Abstract → Problem Statement → Current State → '
		'Proposed Framework → Implementation → Case Studies → Conclusion → References. '
		'Thought-leadership tone. Position paper, not a description.'
	),
	'proposal': (
		'Structure: Executive Summary → Understanding of Requirements → '
		'Technical Approach → Management Plan → Team Qualifications → '
		'Past Performance → Pricing Rationale → Risk Management → Conclusion. '
		'Compliance-oriented. Address all requirements explicitly.'
	),
	'strategy': (
		'Structure: Situation Assessment → Market/Competitive Analysis → '
		'Strategic Options (≥3) → Recommended Strategy → Implementation Roadmap → '
		'Financial Model → Risk Analysis → Governance & KPIs → Conclusion. '
		'BCG/McKinsey style. Each option needs pros/cons and selection rationale.'
	),
}

_MERMAID_KEYWORD_MAP = {
	'flow':        'flowchart LR',
	'process':     'flowchart TD',
	'timeline':    'gantt',
	'roadmap':     'gantt',
	'gantt':       'gantt',
	'2x2':         'quadrantChart',
	'matrix':      'quadrantChart',
	'quadrant':    'quadrantChart',
	'sequence':    'sequenceDiagram',
	'interaction': 'sequenceDiagram',
	'pie':         'pie',
	'share':       'pie',
	'breakdown':   'pie',
	'bar':         'xychart-beta',
	'revenue':     'xychart-beta',
	'trend':       'xychart-beta',
	'class':       'classDiagram',
	'entity':      'erDiagram',
	'state':       'stateDiagram-v2',
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ExhibitSpec(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	id:          str
	type:        str              # "table" | "mermaid" | "chart"
	title:       str
	description: str = ''
	data:        dict | None = None

class SectionSpec(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	id:           str
	title:        str
	level:        int = 1
	parent_id:    str | None = None
	key_points:   list[str] = Field(default_factory=list)
	word_target:  int = 500
	exhibits:     list[ExhibitSpec] = Field(default_factory=list)
	dependencies: list[str] = Field(default_factory=list)
	is_key:       bool = False

class DocumentPlan(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	title:                   str
	subtitle:                str = ''
	document_type:           str = 'report'
	target_audience:         str = ''
	executive_summary_brief: str = ''
	sections:                list[SectionSpec]
	total_word_target:       int = _DEFAULT_WORD_TARGET

class GeneratedSection(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	spec:       SectionSpec
	content:    str
	raw:        str
	word_count: int
	summary:    str
	issues:     list[str] = Field(default_factory=list)

class LongDocResult(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	title:           str
	markdown:        str
	toc:             str
	index:           str = ''
	word_count:      int
	section_count:   int
	exhibit_count:   int
	issues:          list[str] = Field(default_factory=list)
	elapsed_seconds: float = 0.0
	output_path:     str | None = None
	pdf_path:        str | None = None
	docx_path:       str | None = None
	status:          str = 'ok'


# ---------------------------------------------------------------------------
# Reference registry
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\[\[([A-Z]+):([a-z_0-9\-]+)\]\]')


class RefRegistry:
	"""Pre-assigns all section and exhibit numbers before any LLM call."""

	def __init__(self, plan: DocumentPlan):
		self.sections: dict[str, str] = {}
		self.exhibits: dict[str, str] = {}
		self._build(plan)

	def _build(self, plan: DocumentPlan) -> None:
		counters = [0, 0, 0, 0]
		ex_counter = 0
		for sec in plan.sections:
			depth = max(0, min(sec.level - 1, 3))
			counters[depth] += 1
			for i in range(depth + 1, len(counters)):
				counters[i] = 0
			parts = [str(counters[i]) for i in range(depth + 1) if counters[i] > 0]
			self.sections[sec.id] = '.'.join(parts)
			for exhibit in sec.exhibits:
				ex_counter += 1
				self.exhibits[exhibit.id] = f'Exhibit {ex_counter}'

	def to_prompt_block(self) -> str:
		lines = ['REFERENCE REGISTRY (use ONLY these tokens — NEVER write bare numbers like "Section 3"):']
		if self.sections:
			lines.append('Sections:')
			for sid, num in list(self.sections.items())[:20]:
				lines.append(f'  [[SEC:{sid}]] → Section {num}')
		if self.exhibits:
			lines.append('Exhibits:')
			for eid, label in self.exhibits.items():
				lines.append(f'  [[EX:{eid}]] → {label}')
		return '\n'.join(lines)

	def resolve(self, text: str) -> str:
		def sub(m: re.Match) -> str:
			kind, key = m.group(1), m.group(2)
			if kind == 'SEC':
				num = self.sections.get(key)
				return f'Section {num}' if num else f'[§{key}]'
			if kind == 'EX':
				return self.exhibits.get(key, f'[Exhibit:{key}]')
			return m.group(0)
		return _TOKEN_RE.sub(sub, text)

	def audit(self, raw_text: str) -> list[str]:
		"""Audit raw LLM output for bare number leakage."""
		bare = re.findall(r'(?:Section|Exhibit|Figure|Table)\s+\d+[\.\d]*', raw_text)
		if bare:
			return [f'Bare number leakage (LLM bypassed token system): {bare[:5]}']
		return []


# ---------------------------------------------------------------------------
# ToC utilities
# ---------------------------------------------------------------------------

def _github_slug(text: str) -> str:
	text = normalize('NFKD', text).encode('ascii', 'ignore').decode()
	text = text.lower()
	text = re.sub(r'[^\w\s-]', '', text)
	return re.sub(r'\s+', '-', text).strip('-')


def _parse_headings(markdown: str) -> list[dict]:
	headings: list[dict] = []
	seen: dict[str, int] = {}
	for line in markdown.splitlines():
		m = re.match(r'^(#{1,6})\s+(.+?)(?:\s+\{#([\w-]+)\})?$', line)
		if m:
			level  = len(m.group(1))
			text   = m.group(2).strip()
			anchor = m.group(3) or _github_slug(text)
			if anchor in seen:
				seen[anchor] += 1
				anchor = f'{anchor}-{seen[anchor]}'
			else:
				seen[anchor] = 0
			headings.append({'level': level, 'text': text, 'anchor': anchor})
	return headings


def _build_toc(headings: list[dict]) -> str:
	lines = ['## Table of Contents\n']
	for h in headings:
		indent = '  ' * (h['level'] - 1)
		lines.append(f"{indent}- [{h['text']}](#{h['anchor']})")
	return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class LongFormDocumentEngine:
	"""
	Generates 50,000–200,000-word documents via hierarchical planning + serial
	section generation with rolling context and entity state consistency.

	Args:
	    ai_engine:     AIModel (Ollama wrapper)
	    search_engine: Optional search backend for evidence-first RAG

	Usage:
	    engine = LongFormDocumentEngine(ai_engine, search_engine)
	    result = engine.generate(
	        topic='Digital Transformation Strategy for Mid-Market Manufacturers',
	        document_type='strategy',
	        target_pages=150,
	        on_progress=lambda stage, i, n: print(f'{stage} {i}/{n}'),
	    )
	"""

	def __init__(self, ai_engine: AIModel, search_engine=None):
		self.ai_engine    = ai_engine
		self.search_engine = search_engine

	# ── Public API ─────────────────────────────────────────────────────────────

	def generate(
		self,
		topic:           str,
		document_type:   str = 'report',
		target_audience: str = '',
		context:         str = '',
		target_pages:    int = 50,
		sections_hint:   str = '',
		render_pdf:      bool = False,
		render_docx:     bool = False,
		save_output:     bool = True,
		on_progress:     object = None,   # callable(stage, i, n) or None
	) -> dict:
		"""
		Generate a long-form document.

		Args:
		    topic:           Central topic or question
		    document_type:   'report' | 'whitepaper' | 'proposal' | 'strategy'
		    target_audience: Reader profile
		    context:         Source material, background, data to draw from
		    target_pages:    Length in pages (250 words/page)
		    sections_hint:   Optional comma-separated section titles to include
		    render_pdf:      If True, attempt Pandoc PDF rendering
		    render_docx:     If True, attempt Pandoc DOCX rendering
		    save_output:     If True, save .md to data/long_documents/
		    on_progress:     callback(stage: str, i: int, n: int) for progress

		Returns dict with: title, markdown, toc, index, word_count, section_count,
		    exhibit_count, issues, elapsed_seconds, output_path, pdf_path, docx_path
		"""
		def _progress(stage, i, n):
			if callable(on_progress):
				on_progress(stage, i, n)

		start  = time.time()
		issues: list[str] = []

		# Stage 1 — Plan
		_progress('planning', 0, 1)
		target_words = target_pages * 250
		plan = self._plan_document(topic, document_type, target_audience, context, target_words, sections_hint)
		if not plan.sections:
			return {'status': 'error', 'error': 'Planning produced no sections', 'topic': topic}
		_progress('planning', 1, 1)

		# Stage 2 — Topological sort by dependencies
		plan = DocumentPlan(
			**{**plan.model_dump(), 'sections': self._sort_by_dependencies(plan.sections)}
		)

		# Stage 3 — Pre-number exhibits (LaTeX two-pass)
		registry = RefRegistry(plan)

		# Stage 4 — Entity state
		entity_state = self._init_entity_state(topic, plan)

		# Stage 5 — Pre-generate all exhibit content (dedicated calls)
		n_exhibits = sum(len(s.exhibits) for s in plan.sections)
		_progress('exhibits', 0, n_exhibits)
		pre_exhibits: dict[str, str] = {}
		ex_done = 0
		for sec in plan.sections:
			for ex in sec.exhibits:
				pre_exhibits[ex.id] = self._generate_exhibit(ex, sec.title)
				ex_done += 1
				_progress('exhibits', ex_done, n_exhibits)

		# Stage 6 — Generate sections serially
		n_sections = len(plan.sections)
		generated: list[GeneratedSection] = []
		summaries: list[str] = []
		exec_summary_idx: int | None = None

		for i, sec in enumerate(plan.sections):
			_progress('writing', i, n_sections)
			is_exec = sec.id in ('executive_summary', 'exec_summary', 'summary')
			if is_exec:
				exec_summary_idx = i

			rolling_ctx = self._build_rolling_context(summaries, generated)
			evidence    = self._retrieve_section_evidence(sec) if self.search_engine else ''
			gs = self._generate_section(
				sec, plan, registry, rolling_ctx, entity_state, context, evidence, pre_exhibits
			)
			generated.append(gs)
			summaries.append(gs.summary)
			self._update_entity_state(entity_state, gs.content)
			issues.extend(gs.issues)

		_progress('writing', n_sections, n_sections)

		# Stage 7 — Refine executive summary (written after full document)
		if exec_summary_idx is not None:
			_progress('refining', 0, 1)
			refined = self._refine_executive_summary(
				generated[exec_summary_idx], generated, plan, registry
			)
			generated[exec_summary_idx] = refined
			_progress('refining', 1, 1)

		# Stage 8 — Contradiction sweep
		_progress('consistency', 0, 1)
		sweep_issues = self._contradiction_sweep(generated, plan)
		issues.extend(sweep_issues)
		_progress('consistency', 1, 1)

		# Stage 9 — Back-matter index
		_progress('index', 0, 1)
		index_md = self._generate_back_index(generated, registry)
		_progress('index', 1, 1)

		# Stage 10 — Assemble
		body_md     = '\n\n'.join(gs.content for gs in generated)
		if index_md:
			body_md = body_md + '\n\n' + index_md
		headings    = _parse_headings(body_md)
		toc_md      = _build_toc(headings)
		document_md = self._build_final_document(plan, toc_md, body_md)

		# Counts
		total_words   = sum(len(gs.content.split()) for gs in generated)
		exhibit_count = sum(len(gs.spec.exhibits) for gs in generated)

		# Stage 11 — Save + render
		output_path: str | None = None
		pdf_path:    str | None = None
		docx_path:   str | None = None

		if save_output:
			output_path = self._save_markdown(plan.title, document_md)

		if render_pdf and output_path:
			pdf_path = self._render_pdf(output_path)

		if render_docx and output_path:
			docx_path = self._render_docx(output_path)

		result = LongDocResult(
			title           = plan.title,
			markdown        = document_md,
			toc             = toc_md,
			index           = index_md,
			word_count      = total_words,
			section_count   = len(generated),
			exhibit_count   = exhibit_count,
			issues          = issues[:20],
			elapsed_seconds = round(time.time() - start, 1),
			output_path     = output_path,
			pdf_path        = pdf_path,
			docx_path       = docx_path,
			status          = 'ok',
		)
		return result.model_dump()

	# ── Stage 1: Document Planning ─────────────────────────────────────────────

	def _plan_document(
		self,
		topic: str, document_type: str, audience: str,
		context: str, word_target: int, sections_hint: str,
	) -> DocumentPlan:
		page_target = word_target // 250
		type_guide  = _DOCUMENT_TYPE_GUIDES.get(document_type, _DOCUMENT_TYPE_GUIDES['report'])
		hint_block  = f'\nPreferred sections (include these): {sections_hint}' if sections_hint else ''
		ctx_block   = f'\nContext/background:\n{context[:2000]}' if context else ''

		prompt = f"""/think
You are an expert document architect. Design a comprehensive hierarchical outline for a {document_type}.

Topic: {topic}
Target audience: {audience or 'business professionals'}
Target: {word_target:,} words (~{page_target} pages)
Document type: {type_guide}{hint_block}{ctx_block}

Requirements:
- 3 hierarchy levels (level=1 H1 sections, level=2 H2, level=3 H3)
- 6–12 H1 sections for a {page_target}-page document; each H1 with 3–6 H2 subsections
- word_target values MUST sum to approximately {word_target:,}
- Include exhibits (type: "table"|"mermaid"|"chart") where data adds value
- Mark is_key=true for: executive_summary, main_findings, recommendations, conclusion
- Set dependencies: if section B references section A, put A's id in B's dependencies[]
- Use snake_case IDs, make them unique and descriptive

Return ONLY valid JSON:
{{
  "title": "Full document title",
  "subtitle": "Optional subtitle",
  "document_type": "{document_type}",
  "target_audience": "{audience or 'business professionals'}",
  "executive_summary_brief": "One sentence central conclusion",
  "total_word_target": {word_target},
  "sections": [
    {{
      "id": "executive_summary",
      "title": "Executive Summary",
      "level": 1,
      "parent_id": null,
      "key_points": ["key finding 1", "core recommendation"],
      "word_target": 1000,
      "is_key": true,
      "exhibits": [],
      "dependencies": []
    }},
    {{
      "id": "market_size_and_growth",
      "title": "Market Size and Growth Trajectory",
      "level": 2,
      "parent_id": "market_analysis",
      "key_points": ["TAM/SAM/SOM", "5-year CAGR by segment"],
      "word_target": 2500,
      "is_key": false,
      "exhibits": [
        {{
          "id": "market_size_table",
          "type": "table",
          "title": "Market Size by Segment 2024–2030 ($B)",
          "description": "Revenue by segment with CAGR, indexed to 2024",
          "data": null
        }},
        {{
          "id": "growth_mermaid",
          "type": "mermaid",
          "title": "Revenue Growth Trajectory by Segment",
          "description": "xychart-beta bar chart showing 5-year projection",
          "data": null
        }}
      ],
      "dependencies": ["market_analysis"]
    }}
  ]
}}"""

		raw = self._llm_json(prompt, {})
		if not raw or 'sections' not in raw:
			return self._minimal_plan(topic, document_type, audience, word_target)

		try:
			sections: list[SectionSpec] = []
			for s in raw.get('sections', []):
				if not isinstance(s, dict) or not s.get('id') or not s.get('title'):
					continue
				exhibits = [
					ExhibitSpec(
						id=e['id'], type=e['type'], title=e['title'],
						description=e.get('description', ''), data=e.get('data'),
					)
					for e in (s.pop('exhibits', []) or [])
					if isinstance(e, dict) and e.get('id') and e.get('type') and e.get('title')
				]
				sections.append(SectionSpec(
					id          = str(s.get('id', '')),
					title       = str(s.get('title', '')),
					level       = int(s.get('level', 1)),
					parent_id   = s.get('parent_id'),
					key_points  = list(s.get('key_points') or []),
					word_target = int(s.get('word_target', 500)),
					exhibits    = exhibits,
					dependencies= list(s.get('dependencies') or []),
					is_key      = bool(s.get('is_key', False)),
				))
			if not sections:
				return self._minimal_plan(topic, document_type, audience, word_target)
			return DocumentPlan(
				title                   = str(raw.get('title', topic)),
				subtitle                = str(raw.get('subtitle', '')),
				document_type           = document_type,
				target_audience         = audience,
				executive_summary_brief = str(raw.get('executive_summary_brief', '')),
				sections                = sections,
				total_word_target       = word_target,
			)
		except Exception:
			return self._minimal_plan(topic, document_type, audience, word_target)

	def _minimal_plan(
		self, topic: str, doc_type: str, audience: str, words: int
	) -> DocumentPlan:
		n_body = max(4, words // 3_000)
		sections = [
			SectionSpec(id='executive_summary', title='Executive Summary', level=1, word_target=1_000, is_key=True),
			SectionSpec(id='introduction', title='Introduction and Background', level=1, word_target=800),
		]
		for i in range(1, n_body + 1):
			sections.append(SectionSpec(
				id=f'chapter_{i}', title=f'Chapter {i}: Analysis',
				level=1, word_target=words // n_body,
			))
		sections.append(SectionSpec(
			id='conclusions', title='Conclusions and Recommendations',
			level=1, word_target=1_000, is_key=True,
		))
		return DocumentPlan(
			title=topic, document_type=doc_type, target_audience=audience,
			sections=sections, total_word_target=words,
		)

	# ── Stage 2: Topological Sort ──────────────────────────────────────────────

	def _sort_by_dependencies(self, sections: list[SectionSpec]) -> list[SectionSpec]:
		"""Kahn's algorithm: generate sections in dependency order (RaPID pattern)."""
		id_to_sec   = {s.id: s for s in sections}
		# Build adjacency and in-degree maps
		in_degree:  dict[str, int] = {s.id: 0 for s in sections}
		dependents: dict[str, list[str]] = defaultdict(list)  # dep → [sections that need it]

		for sec in sections:
			for dep in sec.dependencies:
				if dep in id_to_sec:
					in_degree[sec.id] += 1
					dependents[dep].append(sec.id)

		# Kahn's BFS — maintain original order within same level
		queue = [s.id for s in sections if in_degree[s.id] == 0]
		result: list[SectionSpec] = []
		while queue:
			sid = queue.pop(0)
			result.append(id_to_sec[sid])
			for nxt in dependents[sid]:
				in_degree[nxt] -= 1
				if in_degree[nxt] == 0:
					queue.append(nxt)

		# Append any cycles (shouldn't happen in practice)
		seen = {s.id for s in result}
		for sec in sections:
			if sec.id not in seen:
				result.append(sec)

		return result

	# ── Stage 5: Exhibit Generation ───────────────────────────────────────────

	def _generate_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		"""Dedicated exhibit generation call. Returns formatted markdown content."""
		if exhibit.type == 'table':
			return self._generate_table_exhibit(exhibit, section_title)
		if exhibit.type in ('mermaid', 'chart'):
			return self._generate_mermaid_exhibit(exhibit, section_title)
		return ''

	def _generate_table_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		"""Two-step: LLM → structured JSON → validated GFM markdown table."""
		prompt = f"""/no_think
Generate structured data for a table exhibit.

Section: {section_title}
Exhibit title: {exhibit.title}
Description: {exhibit.description}

Return ONLY valid JSON:
{{
  "headers": ["Column 1", "Column 2", "Column 3"],
  "rows": [
    ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
    ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"]
  ],
  "source": "Source attribution (Year)"
}}

Rules:
- Include 5–10 data rows unless the exhibit clearly needs fewer
- Use realistic, specific values — no placeholders like "X" or "TBD"
- Add a source row citing where this data would come from
- Financial data: use consistent units (all $M or all $B)
- Include a CAGR or growth rate column when relevant"""

		data = self._llm_json(prompt, {})
		if not data or 'headers' not in data or 'rows' not in data:
			return ''

		return self._render_gfm_table(data)

	def _render_gfm_table(self, data: dict) -> str:
		headers = data.get('headers', [])
		rows    = data.get('rows', [])
		source  = data.get('source', '')
		if not headers:
			return ''

		n_cols = len(headers)
		lines  = []
		lines.append('| ' + ' | '.join(str(h) for h in headers) + ' |')
		lines.append('|' + '|'.join(' :--- ' for _ in headers) + '|')
		for row in rows:
			# Pad/truncate row to n_cols
			padded = list(row) + [''] * n_cols
			lines.append('| ' + ' | '.join(str(c) for c in padded[:n_cols]) + ' |')
		if source:
			lines.append(f'\n*Source: {source}*')
		return '\n'.join(lines)

	def _generate_mermaid_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		"""Focused Mermaid diagram generation. Returns fenced mermaid block."""
		# Infer diagram type from description
		desc_lower = exhibit.description.lower()
		chart_type = next(
			(v for k, v in _MERMAID_KEYWORD_MAP.items() if k in desc_lower),
			'flowchart LR',
		)

		type_guidance = {
			'flowchart LR':    'Use clear node labels (avoid special chars). Declare all nodes before edges.',
			'flowchart TD':    'Use top-down layout. Group related nodes. Declare all nodes before edges.',
			'gantt':           'Use dateFormat YYYY-MM. Organize with sections by phase.',
			'quadrantChart':   'Set x-axis and y-axis labels. Label all four quadrants. Place 5–8 items.',
			'sequenceDiagram': 'Show 3–5 actors. Use clear, specific message labels.',
			'pie':             'Use title. Limit to 6–8 slices. Values must sum to 100 or be raw counts.',
			'xychart-beta':    'Set title and axis labels. Use "bar" or "line" marks.',
			'classDiagram':    'Show relationships (--|>, ..|>, --*). Include key attributes.',
			'erDiagram':       'Use correct cardinality notation (||--||, etc.). Label relationships.',
			'stateDiagram-v2': 'Show states and transitions with labels.',
		}.get(chart_type, '')

		prompt = f"""/no_think
Generate a Mermaid diagram for this exhibit.

Section: {section_title}
Exhibit: {exhibit.title}
Description: {exhibit.description}
Chart type to use: {chart_type}
{type_guidance}

Return ONLY the raw Mermaid diagram code (no markdown fences, no explanation).
The code must be syntactically valid Mermaid {chart_type} syntax.
Use realistic, specific labels — no placeholders."""

		code = self.ai_engine.generate_text(prompt).strip()
		# Strip any accidental fences the model may have added
		code = re.sub(r'^```(?:mermaid)?\s*', '', code, flags=re.MULTILINE)
		code = re.sub(r'```\s*$', '', code, flags=re.MULTILINE).strip()
		if not code:
			return ''
		return f'```mermaid\n{code}\n```'

	# ── Stage 6: Section Generation ───────────────────────────────────────────

	def _generate_section(
		self,
		spec:           SectionSpec,
		plan:           DocumentPlan,
		registry:       RefRegistry,
		rolling_ctx:    str,
		entity_state:   dict,
		source_context: str,
		evidence:       str,
		pre_exhibits:   dict[str, str],
	) -> GeneratedSection:
		heading_mark = '#' * spec.level
		entity_block = self._build_entity_block(entity_state)
		src_block    = f'\nSOURCE MATERIAL:\n{source_context[:1_200]}' if source_context else ''
		evi_block    = f'\nRETRIEVED EVIDENCE (use facts from this):\n{evidence[:1_200]}' if evidence else ''

		prompt = f"""/no_think
Writing section {registry.sections.get(spec.id, '?')} of {plan.document_type}: "{plan.title}"
Audience: {plan.target_audience or 'business professionals'}
Central conclusion: {plan.executive_summary_brief}

{rolling_ctx}
{entity_block}
{registry.to_prompt_block()}

RULES:
1. Use [[SEC:id]] / [[EX:id]] tokens — NEVER write bare numbers like "Section 3"
2. Do NOT contradict established statistics above
3. Write ONLY this section's content — no meta-commentary
4. Target: {spec.word_target} words. Be specific, substantive, and analytical.
5. **Bold** new key terms on first use. Use markdown lists and tables naturally.
6. End section with a clear transition or summary sentence.
{src_block}{evi_block}

WRITE SECTION NOW:
{heading_mark} {spec.title}

Key points:
{chr(10).join(f'- {p}' for p in spec.key_points) if spec.key_points else '- Cover comprehensively and specifically'}

Write the section content directly (do not repeat the heading):"""

		if spec.is_key:
			candidates = [self.ai_engine.generate_text(prompt) for _ in range(_SELF_CONSISTENCY_N)]
			raw_text = max(candidates, key=lambda t: len(t.split()))
		else:
			raw_text = self.ai_engine.generate_text(prompt)

		# Word count enforcement — retry if too short
		raw_text = self._enforce_word_count(raw_text, spec, prompt)

		# Append pre-generated exhibits
		exhibit_blocks: list[str] = []
		for ex in spec.exhibits:
			label   = registry.exhibits.get(ex.id, ex.id)
			content = pre_exhibits.get(ex.id, '')
			if content:
				exhibit_blocks.append(f'\n\n**{label}: {ex.title}**\n\n{content}')

		full_raw  = f'{heading_mark} {spec.title}\n\n{raw_text.strip()}{"".join(exhibit_blocks)}'
		issues    = registry.audit(full_raw)
		resolved  = registry.resolve(full_raw)
		summary   = self._summarize_section(spec.title, resolved)

		return GeneratedSection(
			spec       = spec,
			content    = resolved,
			raw        = full_raw,
			word_count = len(resolved.split()),
			summary    = summary,
			issues     = issues,
		)

	def _enforce_word_count(self, raw: str, spec: SectionSpec, original_prompt: str) -> str:
		"""Retry with expansion prompt if output is less than 50% of target."""
		for _ in range(_MAX_EXPAND_RETRIES):
			word_count = len(raw.split())
			if word_count >= spec.word_target * _WORD_COUNT_MIN_RATIO:
				break
			expansion = f"""/no_think
The section draft is {word_count} words but needs ~{spec.word_target} words.

EXPAND significantly by adding:
- Concrete examples, case studies, and real-world illustrations
- Deeper analysis of each key point (not just bullets — develop each)
- Specific data, statistics, and quantified insights
- Implementation considerations and practical implications
- Risk factors, tradeoffs, or nuances

Previous draft (EXPAND upon this, do not repeat preamble):
{raw}

Write the complete expanded section ({spec.word_target} words target):"""
			raw = self.ai_engine.generate_text(expansion)
		return raw

	# ── Stage 7: Executive Summary Refinement ─────────────────────────────────

	def _refine_executive_summary(
		self,
		exec_sec:  GeneratedSection,
		all_sections: list[GeneratedSection],
		plan:      DocumentPlan,
		registry:  RefRegistry,
	) -> GeneratedSection:
		"""Rewrite exec summary after full doc is written — it can now be authoritative."""
		other_summaries = [
			f'- {gs.summary}' for gs in all_sections
			if gs.spec.id != exec_sec.spec.id
		]
		spec = exec_sec.spec
		heading_mark = '#' * spec.level

		prompt = f"""/no_think
Rewrite the executive summary for "{plan.title}" — the full document is now written.

Document sections and their key findings:
{chr(10).join(other_summaries)}

Current executive summary (IMPROVE upon this — do not just copy):
{exec_sec.content[:2_000]}

Write a definitive executive summary that:
1. Opens with the governing conclusion in the first sentence (Pyramid Principle)
2. Summarizes each major section's single key finding (2–3 sentences each)
3. States 3–5 clear, actionable recommendations
4. Ends with the critical path or next step
5. Target: {spec.word_target} words

Write directly (heading will be added separately):"""

		candidates = [self.ai_engine.generate_text(prompt) for _ in range(_SELF_CONSISTENCY_N)]
		best_raw   = max(candidates, key=lambda t: len(t.split()))
		best_raw   = self._enforce_word_count(best_raw, spec, prompt)

		full_raw = f'{heading_mark} {spec.title}\n\n{best_raw.strip()}'
		resolved = registry.resolve(full_raw)

		return GeneratedSection(
			spec       = spec,
			content    = resolved,
			raw        = full_raw,
			word_count = len(resolved.split()),
			summary    = self._summarize_section(spec.title, resolved),
			issues     = registry.audit(full_raw),
		)

	# ── Stage 8: Contradiction Sweep ──────────────────────────────────────────

	def _contradiction_sweep(
		self,
		generated: list[GeneratedSection],
		plan:      DocumentPlan,
	) -> list[str]:
		"""ChatProtect pattern: find contradictory claims across the document."""
		# Collect all key statistics and claims from entity state
		all_content_sample = '\n\n'.join(
			f'[{gs.spec.title}]: {gs.summary}' for gs in generated
		)

		prompt = f"""/no_think
Review this document outline for logical contradictions or inconsistencies.

Document: {plan.title}
Section summaries:
{all_content_sample[:3_000]}

Identify ONLY concrete contradictions: cases where one section states X and another states not-X,
or where statistics are incompatible.

Return JSON:
{{
  "contradictions": [
    {{
      "section_a": "section title",
      "section_b": "section title",
      "issue": "one sentence describing the contradiction"
    }}
  ]
}}

Return {{"contradictions": []}} if no contradictions found."""

		result = self._llm_json(prompt, {'contradictions': []})
		issues: list[str] = []
		for c in result.get('contradictions', []):
			if isinstance(c, dict) and c.get('issue'):
				issues.append(
					f'Contradiction: [{c.get("section_a","?")}] vs [{c.get("section_b","?")}] — {c["issue"]}'
				)
		return issues

	# ── Stage 9: Back-Matter Index ─────────────────────────────────────────────

	def _generate_back_index(
		self,
		generated: list[GeneratedSection],
		registry:  RefRegistry,
	) -> str:
		"""Alphabetical back-matter index: key terms → section numbers."""
		# Build section number lookup
		section_nums = {
			gs.spec.id: registry.sections.get(gs.spec.id, '?')
			for gs in generated
		}
		section_listing = '\n'.join(
			f'  Section {num}: {gs.spec.title}'
			for gs, num in zip(generated, section_nums.values())
		)

		prompt = f"""/no_think
Extract an alphabetical index for this document.

Section list:
{section_listing}

Identify the {_INDEX_TERMS_TARGET} most important terms, concepts, frameworks, and proper nouns.
For each, list the section numbers where it appears.

Return JSON:
{{
  "entries": [
    {{
      "term": "Artificial Intelligence",
      "sections": ["1", "2.3", "4.1"],
      "see_also": ["Machine Learning", "Neural Networks"]
    }}
  ]
}}

Rules:
- Alphabetical order
- Only include terms that appear in ≥2 sections (they are index-worthy)
- Proper nouns, frameworks (BCG, Porter's), and technical terms are high priority
- "See also" should point to related terms in the same index"""

		result = self._llm_json(prompt, {'entries': []})
		entries = result.get('entries', [])
		if not entries:
			return ''

		# Render as markdown
		lines = ['## Index\n']
		for entry in sorted(entries, key=lambda e: e.get('term', '').lower()):
			if not isinstance(entry, dict) or not entry.get('term'):
				continue
			term     = entry['term']
			sections = ', '.join(entry.get('sections', []))
			see_also = entry.get('see_also', [])
			line     = f'**{term}** — {sections}'
			if see_also:
				line += f' *(see also: {", ".join(see_also)})*'
			lines.append(line)

		return '\n'.join(lines)

	# ── Entity State ───────────────────────────────────────────────────────────

	def _init_entity_state(self, topic: str, plan: DocumentPlan) -> dict:
		return {
			'topic':              topic,
			'document_title':     plan.title,
			'defined_terms':      {},
			'key_statistics':     [],
			'entities_mentioned': [],
			'claims_made':        [],
		}

	def _update_entity_state(self, state: dict, content: str) -> None:
		stats = re.findall(
			r'[\$£€]?\s*\d+(?:\.\d+)?\s*(?:%|percent|million|billion|trillion|bn|mn|M|B|T)',
			content, re.I,
		)
		combined = list(dict.fromkeys(state['key_statistics'] + stats))
		state['key_statistics'] = combined[-25:]
		for t in re.findall(r'\*\*([A-Z][^*]{3,60})\*\*', content):
			if t not in state['defined_terms']:
				state['defined_terms'][t] = ''

	def _build_entity_block(self, entity_state: dict) -> str:
		parts: list[str] = []
		if entity_state['key_statistics']:
			parts.append(
				f'ESTABLISHED STATISTICS (do NOT contradict): '
				f'{"; ".join(entity_state["key_statistics"][-12:])}'
			)
		if entity_state['defined_terms']:
			terms = list(entity_state['defined_terms'].keys())[:10]
			parts.append(f'DEFINED TERMS (use consistently): {", ".join(terms)}')
		return '\n'.join(parts)

	# ── Rolling Context ────────────────────────────────────────────────────────

	def _build_rolling_context(
		self,
		summaries:  list[str],
		generated:  list[GeneratedSection],
	) -> str:
		parts: list[str] = []
		recent = summaries[-_ROLLING_SUMMARY_LIMIT:]
		if recent:
			parts.append('PRIOR SECTIONS (maintain consistency):')
			offset = max(0, len(summaries) - _ROLLING_SUMMARY_LIMIT)
			for i, s in enumerate(recent):
				parts.append(f'  {offset + i + 1}. {s}')
		if generated:
			parts.append(f'\nPREVIOUS SECTION (for smooth transition):\n{generated[-1].content[:1_200]}')
		return '\n'.join(parts)[:_MAX_CONTEXT_CHARS]

	# ── RAG Integration ────────────────────────────────────────────────────────

	def _retrieve_section_evidence(self, spec: SectionSpec) -> str:
		"""Evidence-first RAG: retrieve before generating each section."""
		if not self.search_engine:
			return ''
		queries = [spec.title] + spec.key_points[:2]
		results: list[dict] = []
		for q in queries[:2]:
			try:
				r = self.search_engine.search(q, max_results=3)
				if isinstance(r, list):
					results.extend(r)
			except Exception:
				pass
		return self._format_evidence(results[:6])

	def _format_evidence(self, results: list[dict]) -> str:
		lines: list[str] = []
		for r in results:
			title   = r.get('title', 'Source')
			url     = r.get('href', r.get('url', ''))
			snippet = r.get('body', r.get('snippet', ''))[:350]
			lines.append(f'[{title}]({url})\n{snippet}')
		return '\n\n'.join(lines)

	# ── Section Summary ────────────────────────────────────────────────────────

	def _summarize_section(self, title: str, content: str) -> str:
		lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith('#')]
		if lines:
			return f'{title}: {lines[0][:_SUMMARY_MAX_CHARS]}'
		return title

	# ── Assembly ───────────────────────────────────────────────────────────────

	def _build_final_document(
		self, plan: DocumentPlan, toc: str, body: str
	) -> str:
		parts: list[str] = [f'# {plan.title}']
		if plan.subtitle:
			parts.append(f'*{plan.subtitle}*')
		if plan.target_audience:
			parts.append(f'*Prepared for: {plan.target_audience}*')
		if plan.executive_summary_brief:
			parts.append(f'\n> {plan.executive_summary_brief}')
		parts.extend(['', '---', '', toc, '', '---', '', body])
		return '\n'.join(parts)

	# ── Save & Render ──────────────────────────────────────────────────────────

	def _save_markdown(self, title: str, content: str) -> str:
		_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
		slug = re.sub(r'[^\w\-]', '_', title.lower())[:60].strip('_')
		ts   = time.strftime('%Y%m%d_%H%M%S')
		path = _OUTPUT_DIR / f'{slug}_{ts}.md'
		path.write_text(content, encoding='utf-8')
		return str(path)

	def _render_pdf(self, md_path: str) -> str | None:
		"""Pandoc PDF rendering: Typst → xelatex → default."""
		out_path = md_path.replace('.md', '.pdf')
		for extra in (
			['--to=typst', '--pdf-engine=typst'],
			['--pdf-engine=xelatex', '--variable=mainfont=DejaVu Serif'],
			[],
		):
			try:
				r = subprocess.run(
					['pandoc', md_path, '-o', out_path,
					 '--toc', '--number-sections',
					 '--variable=geometry:margin=2.5cm',
					 '--variable=fontsize=11pt', *extra],
					capture_output=True, timeout=180,
				)
				if r.returncode == 0:
					return out_path
			except (FileNotFoundError, subprocess.TimeoutExpired):
				continue
		return None

	def _render_docx(self, md_path: str) -> str | None:
		"""Pandoc DOCX rendering with reference template if available."""
		out_path  = md_path.replace('.md', '.docx')
		template  = Path(__file__).parent.parent / 'data' / 'templates' / 'corporate-template.docx'
		extra = ['--reference-doc', str(template)] if template.exists() else []
		try:
			r = subprocess.run(
				['pandoc', md_path, '-o', out_path, '--toc', *extra],
				capture_output=True, timeout=120,
			)
			return out_path if r.returncode == 0 else None
		except (FileNotFoundError, subprocess.TimeoutExpired):
			return None

	# ── Utilities ──────────────────────────────────────────────────────────────

	@staticmethod
	def _extract_json_span(text: str, open_ch: str, close_ch: str) -> str | None:
		depth, start = 0, None
		for i, ch in enumerate(text):
			if ch == open_ch:
				if start is None:
					start = i
				depth += 1
			elif ch == close_ch:
				depth -= 1
				if depth == 0 and start is not None:
					return text[start:i + 1]
		return None

	def _llm_json(self, prompt: str, fallback: dict) -> dict:
		try:
			response = self.ai_engine.generate_text(prompt)
			span = self._extract_json_span(response, '{', '}')
			if span:
				return json.loads(span)
		except Exception:
			pass
		return dict(fallback)

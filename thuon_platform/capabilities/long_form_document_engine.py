# capabilities/long_form_document_engine.py
"""
Long-form document engine (v2) — generates 50,000–200,000-word (100–400+ page)
documents of consulting-grade quality from Ollama models.

Research basis (docs/research/long-document-generation.md):
  RaPID (ACL 2025), DOME (NAACL 2025), LongWriter (ICLR 2025),
  ChatProtect (arXiv:2305.15852), RAPTOR (ICLR 2024), ConvergeWriter (2025).

Full pipeline:
  Plan (/think) → topological generation order (doc order preserved separately) →
  pre-number exhibits (tree-based, parent_id-aware) →
  pre-generate all exhibits (dedicated calls: JSON→GFM table, focused Mermaid) →
  serial section generation in topo order (rolling context + entity state + optional RAG) →
  word-count enforcement (retain best candidate, max 2 retries) →
  executive summary post-generation refinement (self-consistency N=3, written last) →
  contradiction sweep (ChatProtect) →
  back-matter index (LLM term extraction) →
  ToC + assembly in DOCUMENT ORDER → optional PDF (Pandoc Typst) / DOCX render

Key correctness guarantees:
  - Document order ≠ generation order: topological sort only controls WHEN sections
    are written, not the order they appear in the output or their section numbers.
  - RefRegistry uses parent_id tree walk → correct nested numbers regardless of
    section ordering or topological reordering.
  - _extract_json_span tracks string state → immune to braces inside string literals.
  - _enforce_word_count keeps best candidate, never regresses to a shorter draft.
  - Entity-state stats regex requires currency prefix for bare M/B/T → no ordinal
    false-positives (4th, 5th, 3M, 1B no longer pollute the statistics block).
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

_SELF_CONSISTENCY_N    = 3
_ROLLING_SUMMARY_LIMIT = 3
_MAX_CONTEXT_CHARS     = 4_000
_SUMMARY_MAX_CHARS     = 500
_DEFAULT_WORD_TARGET   = 50_000
_WORD_COUNT_MIN_RATIO  = 0.50     # retry if actual < 50% of target
_MAX_EXPAND_RETRIES    = 2
_INDEX_TERMS_TARGET    = 40
_OUTPUT_DIR            = Path(__file__).parent.parent / 'data' / 'long_documents'

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

_TOKEN_RE = re.compile(r'\[\[([A-Z]+):([\w\-]+)\]\]')


class RefRegistry:
	"""
	Pre-assigns all section and exhibit numbers before any LLM call.

	Section numbering uses a parent_id tree walk — not a linear counter —
	so nested hierarchies are correct regardless of section order in the
	list or topological reordering for generation.
	"""

	def __init__(self, plan: DocumentPlan):
		self.sections: dict[str, str] = {}
		self.exhibits: dict[str, str] = {}
		self._build(plan)

	def _build(self, plan: DocumentPlan) -> None:
		# Tree walk keyed by parent_id — correct for any nesting depth
		children: dict[str | None, list[SectionSpec]] = defaultdict(list)
		for sec in plan.sections:
			children[sec.parent_id].append(sec)

		def walk(parent_id: str | None, prefix: list[int]) -> None:
			for i, sec in enumerate(children[parent_id], start=1):
				num = prefix + [i]
				self.sections[sec.id] = '.'.join(str(n) for n in num)
				walk(sec.id, num)
		walk(None, [])

		# Exhibit flat numbering in document order (preserves plan.sections order)
		ex_counter = 0
		for sec in plan.sections:
			for exhibit in sec.exhibits:
				ex_counter += 1
				self.exhibits[exhibit.id] = f'Exhibit {ex_counter}'

	def to_prompt_block(self) -> str:
		lines = [
			'REFERENCE REGISTRY (use ONLY these tokens — '
			'NEVER write bare numbers like "Section 3"):'
		]
		if self.sections:
			lines.append('Sections:')
			for sid, num in self.sections.items():
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
		"""Audit raw LLM output (pre-resolution) for bare number leakage."""
		bare = re.findall(r'(?:Section|Exhibit|Figure|Table)\s+\d+[\.\d]*', raw_text, re.IGNORECASE)
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

	IMPORTANT: generation order (topological) ≠ document order (planner intent).
	Output body always follows document order; topological ordering only controls
	which section's LLM call fires first.

	Args:
	    ai_engine:     AIModel (Ollama wrapper)
	    search_engine: Optional search backend for evidence-first RAG
	"""

	def __init__(self, ai_engine: AIModel, search_engine=None):
		self.ai_engine     = ai_engine
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
		on_progress:     object = None,
	) -> dict:
		def _progress(stage: str, i: int, n: int) -> None:
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

		# Stage 2 — Topological GENERATION order; plan.sections stays as document order.
		gen_order, topo_issues = self._sort_by_dependencies(plan.sections)
		issues.extend(topo_issues)

		# Stage 3 — Pre-number using document order (tree walk, parent_id-aware)
		registry = RefRegistry(plan)

		# Stage 4 — Entity state
		entity_state = self._init_entity_state(topic, plan)

		# Stage 5 — Pre-generate all exhibit content
		n_exhibits = sum(len(s.exhibits) for s in plan.sections)
		_progress('exhibits', 0, n_exhibits)
		pre_exhibits: dict[str, str] = {}
		ex_done = 0
		for sec in gen_order:
			for ex in sec.exhibits:
				pre_exhibits[ex.id] = self._generate_exhibit(ex, sec.title)
				ex_done += 1
				_progress('exhibits', ex_done, n_exhibits)

		# Stage 6 — Generate sections in generation order; store by id for doc-order assembly
		n_sections      = len(gen_order)
		generated_map:  dict[str, GeneratedSection] = {}
		gen_list:       list[GeneratedSection] = []   # generation order (rolling ctx)
		summaries:      list[str] = []

		for i, sec in enumerate(gen_order):
			_progress('writing', i, n_sections)
			rolling_ctx = self._build_rolling_context(summaries, gen_list)
			evidence    = self._retrieve_section_evidence(sec) if self.search_engine else ''
			gs = self._generate_section(
				sec, plan, registry, rolling_ctx, entity_state, context, evidence, pre_exhibits
			)
			generated_map[sec.id] = gs
			gen_list.append(gs)
			summaries.append(gs.summary)
			self._update_entity_state(entity_state, gs.content)
			issues.extend(gs.issues)

		_progress('writing', n_sections, n_sections)

		# Reconstitute in document order for all downstream stages
		doc_generated = [generated_map[s.id] for s in plan.sections if s.id in generated_map]

		# Stage 7 — Refine executive summary (written last, full doc available)
		exec_sec_id = next(
			(s.id for s in plan.sections
			 if s.id in ('executive_summary', 'exec_summary', 'summary')
			 or 'exec' in s.id.lower()
			 or 'executive' in s.title.lower()),
			None,
		)
		if exec_sec_id and exec_sec_id in generated_map:
			_progress('refining', 0, 1)
			generated_map[exec_sec_id] = self._refine_executive_summary(
				generated_map[exec_sec_id], doc_generated, plan, registry
			)
			doc_generated = [generated_map[s.id] for s in plan.sections if s.id in generated_map]
			_progress('refining', 1, 1)

		# Stage 8 — Contradiction sweep
		_progress('consistency', 0, 1)
		issues.extend(self._contradiction_sweep(doc_generated, plan))
		_progress('consistency', 1, 1)

		# Stage 9 — Back-matter index
		_progress('index', 0, 1)
		index_md = self._generate_back_index(doc_generated, registry)
		_progress('index', 1, 1)

		# Stage 10 — Assemble in document order
		body_md = '\n\n'.join(gs.content for gs in doc_generated)
		if index_md:
			body_md = body_md + '\n\n' + index_md
		headings    = _parse_headings(body_md)
		toc_md      = _build_toc(headings)
		document_md = self._build_final_document(plan, toc_md, body_md)

		total_words   = sum(len(gs.content.split()) for gs in doc_generated)
		exhibit_count = sum(len(gs.spec.exhibits) for gs in doc_generated)

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

		return LongDocResult(
			title           = plan.title,
			markdown        = document_md,
			toc             = toc_md,
			index           = index_md,
			word_count      = total_words,
			section_count   = len(doc_generated),
			exhibit_count   = exhibit_count,
			issues          = issues[:20],
			elapsed_seconds = round(time.time() - start, 1),
			output_path     = output_path,
			pdf_path        = pdf_path,
			docx_path       = docx_path,
			status          = 'ok',
		).model_dump()

	# ── Stage 1: Planning ──────────────────────────────────────────────────────

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
You are an expert document architect. Design a comprehensive hierarchical outline.

Topic: {topic}
Audience: {audience or 'business professionals'}
Target: {word_target:,} words (~{page_target} pages)
Document type: {type_guide}{hint_block}{ctx_block}

Requirements:
- 3 hierarchy levels: level=1 (H1), level=2 (H2), level=3 (H3)
- 6–12 H1 sections; each H1 with 3–6 H2 subsections
- word_target values MUST sum to ~{word_target:,}
- Include exhibits (type:"table"|"mermaid") where data adds value
- Mark is_key=true for: executive_summary, main_findings, recommendations, conclusion
- H2 sections MUST set parent_id to their parent H1's id
- Set dependencies: if section B needs section A, include A's id in B's dependencies[]
- Use snake_case IDs

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
      "key_points": ["key finding", "core recommendation"],
      "word_target": 1000,
      "is_key": true,
      "exhibits": [],
      "dependencies": []
    }},
    {{
      "id": "market_analysis",
      "title": "Market Analysis",
      "level": 1,
      "parent_id": null,
      "key_points": ["market size", "growth trends"],
      "word_target": 3000,
      "is_key": false,
      "exhibits": [
        {{"id": "market_size_table", "type": "table",
          "title": "Market Size 2024-2030 ($B)", "description": "Revenue by segment with CAGR", "data": null}}
      ],
      "dependencies": []
    }},
    {{
      "id": "market_segments",
      "title": "Key Market Segments",
      "level": 2,
      "parent_id": "market_analysis",
      "key_points": ["segment breakdown"],
      "word_target": 1500,
      "is_key": false,
      "exhibits": [],
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
					id           = str(s.get('id', '')),
					title        = str(s.get('title', '')),
					level        = int(s.get('level', 1)),
					parent_id    = s.get('parent_id'),
					key_points   = list(s.get('key_points') or []),
					word_target  = int(s.get('word_target', 500)),
					exhibits     = exhibits,
					dependencies = list(s.get('dependencies') or []),
					is_key       = bool(s.get('is_key', False)),
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

	def _minimal_plan(self, topic: str, doc_type: str, audience: str, words: int) -> DocumentPlan:
		n_body = max(4, words // 3_000)
		sections = [
			SectionSpec(id='executive_summary', title='Executive Summary',
			            level=1, word_target=1_000, is_key=True),
			SectionSpec(id='introduction', title='Introduction and Background',
			            level=1, word_target=800),
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

	def _sort_by_dependencies(
		self, sections: list[SectionSpec]
	) -> tuple[list[SectionSpec], list[str]]:
		"""
		Kahn's algorithm over section dependencies.
		Returns (generation_order, issues).
		Cycle members are appended at end with a warning; plan order otherwise preserved.
		Document order (plan.sections) is NOT modified by this method.
		"""
		id_to_sec   = {s.id: s for s in sections}
		in_degree:  dict[str, int] = {s.id: 0 for s in sections}
		dependents: dict[str, list[str]] = defaultdict(list)

		for sec in sections:
			for dep in sec.dependencies:
				if dep in id_to_sec:
					in_degree[sec.id] += 1
					dependents[dep].append(sec.id)

		queue  = [s.id for s in sections if in_degree[s.id] == 0]
		result: list[SectionSpec] = []
		while queue:
			sid = queue.pop(0)
			result.append(id_to_sec[sid])
			for nxt in dependents[sid]:
				in_degree[nxt] -= 1
				if in_degree[nxt] == 0:
					queue.append(nxt)

		topo_issues: list[str] = []
		seen   = {s.id for s in result}
		cyclic = [sec for sec in sections if sec.id not in seen]
		if cyclic:
			ids = [s.id for s in cyclic]
			topo_issues.append(f'Dependency cycle detected in sections {ids} — appended in declaration order')
			result.extend(cyclic)

		return result, topo_issues

	# ── Stage 5: Exhibit Generation ───────────────────────────────────────────

	def _generate_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		if exhibit.type == 'table':
			return self._generate_table_exhibit(exhibit, section_title)
		if exhibit.type in ('mermaid', 'chart'):
			return self._generate_mermaid_exhibit(exhibit, section_title)
		return ''

	def _generate_table_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		"""Two-step: LLM → structured JSON → validated + pipe-escaped GFM table."""
		prompt = f"""/no_think
Generate structured data for a table exhibit.

Section: {section_title}
Exhibit title: {exhibit.title}
Description: {exhibit.description}

Return ONLY valid JSON:
{{
  "headers": ["Column 1", "Column 2", "Column 3"],
  "rows": [
    ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"]
  ],
  "source": "Source attribution (Year)"
}}

Rules:
- 5–10 data rows with realistic, specific values (no placeholders)
- Consistent financial units (all $M or all $B, not mixed)
- Include CAGR or growth rate column where relevant"""

		data = self._llm_json(prompt, {})
		if not data or 'headers' not in data or not isinstance(data.get('rows'), list):
			return ''
		return self._render_gfm_table(data)

	@staticmethod
	def _escape_cell(s: object) -> str:
		return str(s).replace('|', '\\|').replace('\n', ' ')

	def _render_gfm_table(self, data: dict) -> str:
		headers = data.get('headers', [])
		rows    = data.get('rows', [])
		source  = data.get('source', '')
		if not headers or not isinstance(rows, list):
			return ''
		n_cols = len(headers)
		ec     = self._escape_cell
		lines: list[str] = []
		lines.append('| ' + ' | '.join(ec(h) for h in headers) + ' |')
		lines.append('|' + '|'.join(' :--- ' for _ in headers) + '|')
		for row in rows:
			if not isinstance(row, (list, tuple)):
				continue
			padded = list(row) + [''] * n_cols
			lines.append('| ' + ' | '.join(ec(c) for c in padded[:n_cols]) + ' |')
		if source:
			lines.append(f'\n*Source: {ec(source)}*')
		return '\n'.join(lines)

	def _generate_mermaid_exhibit(self, exhibit: ExhibitSpec, section_title: str) -> str:
		"""Focused Mermaid generation. Extracts code from fences if model added them."""
		desc_lower = exhibit.description.lower()
		chart_type = next(
			(v for k, v in _MERMAID_KEYWORD_MAP.items() if k in desc_lower),
			'flowchart LR',
		)
		type_guidance = {
			'flowchart LR':    'Declare all nodes before edges. Use clear labels.',
			'flowchart TD':    'Top-down. Declare all nodes before edges.',
			'gantt':           'Use dateFormat YYYY-MM. Organise by phase sections.',
			'quadrantChart':   'Set both axis labels. Place 5–8 items.',
			'sequenceDiagram': '3–5 actors, clear message labels.',
			'pie':             'title line first. 6–8 slices max.',
			'xychart-beta':    'title + axis labels. bar or line marks.',
			'classDiagram':    'Show relationships + key attributes.',
			'erDiagram':       'Correct cardinality notation.',
			'stateDiagram-v2': 'States and labelled transitions.',
		}.get(chart_type, '')

		prompt = f"""/no_think
Generate a Mermaid diagram.

Section: {section_title}
Exhibit: {exhibit.title}
Description: {exhibit.description}
Chart type: {chart_type}
{type_guidance}

Return ONLY the raw Mermaid diagram syntax.
Do NOT include markdown fences, prose, or explanation."""

		code = self._llm_text(prompt).strip()
		# Extract content between fences if model added them despite the instruction
		fence_m = re.search(r'```(?:mermaid)?\s*\n(.*?)```', code, re.DOTALL)
		if fence_m:
			code = fence_m.group(1).strip()
		else:
			code = re.sub(r'^```(?:mermaid)?\s*\n?', '', code, flags=re.MULTILINE)
			code = re.sub(r'\n?```\s*$', '', code, flags=re.MULTILINE).strip()
		return f'```mermaid\n{code}\n```' if code else ''

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
		evi_block    = f'\nRETRIEVED EVIDENCE (use facts):\n{evidence[:1_200]}' if evidence else ''

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
4. Target: {spec.word_target} words. Be specific, substantive, analytical.
5. **Bold** new key terms on first use. Use markdown lists and tables naturally.
6. End with a clear transition or summary sentence.
{src_block}{evi_block}

WRITE SECTION:
{heading_mark} {spec.title}

Key points:
{chr(10).join(f'- {p}' for p in spec.key_points) if spec.key_points else '- Cover comprehensively'}

Section content (do not repeat the heading):"""

		if spec.is_key:
			candidates = [self._llm_text(prompt) for _ in range(_SELF_CONSISTENCY_N)]
			raw_text   = max(candidates, key=lambda t: len(t.split()))
		else:
			raw_text = self._llm_text(prompt)

		raw_text = self._enforce_word_count(raw_text, spec, prompt)

		# Strip any leading heading the model prepended — we add our own below
		raw_text = re.sub(r'^#{1,6}\s+[^\n]*\n?', '', raw_text.strip(), count=1).strip()

		exhibit_blocks: list[str] = []
		for ex in spec.exhibits:
			label   = registry.exhibits.get(ex.id, ex.id)
			content = pre_exhibits.get(ex.id, '')
			if content:
				exhibit_blocks.append(f'\n\n**{label}: {ex.title}**\n\n{content}')

		full_raw = f'{heading_mark} {spec.title}\n\n{raw_text.strip()}{"".join(exhibit_blocks)}'
		issues   = registry.audit(full_raw)
		resolved = registry.resolve(full_raw)

		return GeneratedSection(
			spec       = spec,
			content    = resolved,
			raw        = full_raw,
			word_count = len(resolved.split()),
			summary    = self._summarize_section(spec.title, resolved),
			issues     = issues,
		)

	def _enforce_word_count(self, raw: str, spec: SectionSpec, original_prompt: str) -> str:
		"""
		Retry expansion if output < 50% of word target.
		Keeps the best (longest) candidate — never regresses to a shorter draft.
		original_prompt is prepended to the expansion for entity-state / registry continuity.
		"""
		best = raw
		for _ in range(_MAX_EXPAND_RETRIES):
			wc = len(best.split())
			if wc >= spec.word_target * _WORD_COUNT_MIN_RATIO:
				break
			expansion = (
				f'{original_prompt}\n\n'
				f'The previous attempt was only {wc} words (target: {spec.word_target}).\n'
				f'EXPAND significantly — add examples, case studies, data, analysis, implications.\n'
				f'Previous draft:\n{best}\n\n'
				f'Write the complete expanded section ({spec.word_target} words):'
			)
			candidate = self._llm_text(expansion)
			if len(candidate.split()) > len(best.split()):
				best = candidate
		return best

	# ── Stage 7: Executive Summary Refinement ─────────────────────────────────

	def _refine_executive_summary(
		self,
		exec_sec:     GeneratedSection,
		doc_generated: list[GeneratedSection],
		plan:          DocumentPlan,
		registry:      RefRegistry,
	) -> GeneratedSection:
		other_summaries = '\n'.join(
			f'- {gs.summary}' for gs in doc_generated
			if gs.spec.id != exec_sec.spec.id
		)
		spec         = exec_sec.spec
		heading_mark = '#' * spec.level

		prompt = f"""/no_think
Rewrite the executive summary for "{plan.title}" — the full document is now written.

Section findings:
{other_summaries}

Current draft (IMPROVE upon this):
{exec_sec.content[:2_000]}

Requirements:
1. First sentence = governing conclusion (Pyramid Principle)
2. 2–3 sentences per major section's key finding
3. 3–5 clear, actionable recommendations
4. End with critical path / next step
5. Target: {spec.word_target} words

Write directly (heading added separately):"""

		candidates = [self._llm_text(prompt) for _ in range(_SELF_CONSISTENCY_N)]
		best_raw   = max(candidates, key=lambda t: len(t.split()))
		best_raw   = self._enforce_word_count(best_raw, spec, prompt)
		best_raw   = re.sub(r'^#{1,6}\s+[^\n]*\n?', '', best_raw.strip(), count=1).strip()

		# Re-attach any exhibits from the original exec summary section
		exhibit_blocks: list[str] = []
		for ex in spec.exhibits:
			label   = registry.exhibits.get(ex.id, ex.id)
			pattern = re.escape(f'**{label}: {ex.title}**')
			orig_m  = re.search(pattern + r'(.*?)(?=\n\n\*\*|\Z)', exec_sec.content, re.DOTALL)
			if orig_m:
				exhibit_blocks.append(f'\n\n**{label}: {ex.title}**{orig_m.group(1)}')

		full_raw = f'{heading_mark} {spec.title}\n\n{best_raw.strip()}{"".join(exhibit_blocks)}'
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

	def _contradiction_sweep(self, generated: list[GeneratedSection], plan: DocumentPlan) -> list[str]:
		sample = '\n\n'.join(
			f'[{gs.spec.title}]: {gs.summary}' for gs in generated
		)
		result = self._llm_json(
			f"""/no_think
Review these section summaries for contradictions in "{plan.title}".

{sample[:3_000]}

Identify ONLY concrete contradictions — where section A states X and section B states not-X.

Return JSON: {{"contradictions": [{{"section_a":"...", "section_b":"...", "issue":"..."}}]}}
Return {{"contradictions": []}} if none found.""",
			{'contradictions': []},
		)
		return [
			f'Contradiction: [{c.get("section_a","?")}] vs [{c.get("section_b","?")}] — {c["issue"]}'
			for c in result.get('contradictions', [])
			if isinstance(c, dict) and c.get('issue')
		]

	# ── Stage 9: Back-Matter Index ─────────────────────────────────────────────

	def _generate_back_index(self, generated: list[GeneratedSection], registry: RefRegistry) -> str:
		# Build listing in document order (generated is already in doc order)
		section_listing = '\n'.join(
			f'  Section {registry.sections.get(gs.spec.id, "?")}: {gs.spec.title}'
			for gs in generated
		)
		result = self._llm_json(
			f"""/no_think
Extract an alphabetical back-matter index for this document.

Sections:
{section_listing}

Find the {_INDEX_TERMS_TARGET} most important terms (proper nouns, frameworks, technical concepts).
Only include terms appearing in ≥2 sections.

Return JSON: {{"entries": [{{"term": "...", "sections": ["1", "2.3"], "see_also": ["..."]}}]}}""",
			{'entries': []},
		)
		entries = result.get('entries', [])
		if not entries:
			return ''
		lines = ['## Index\n']
		for e in sorted(entries, key=lambda x: x.get('term', '').lower()):
			if not isinstance(e, dict) or not e.get('term'):
				continue
			sections = ', '.join(str(s) for s in e.get('sections', []))
			see_also = e.get('see_also', [])
			line     = f'**{e["term"]}** — {sections}'
			if see_also:
				line += f' *(see also: {", ".join(see_also)})*'
			lines.append(line)
		return '\n'.join(lines)

	# ── Entity State ───────────────────────────────────────────────────────────

	def _init_entity_state(self, topic: str, plan: DocumentPlan) -> dict:
		return {
			'topic':          topic,
			'document_title': plan.title,
			'defined_terms':  {},
			'key_statistics': [],
		}

	def _update_entity_state(self, state: dict, content: str) -> None:
		# Require currency prefix for bare M/B/T to avoid false positives (4th, 5th, 3M, 1B)
		stats = re.findall(
			r'(?:[\$£€]\s?)?\d+(?:\.\d+)?\s*(?:percent\b|million\b|billion\b|trillion\b|bn\b|mn\b)'
			r'|(?:[\$£€]\s?)\d+(?:\.\d+)?\s*[MBT](?!\w)'
			r'|\d+(?:\.\d+)?\s*%',
			content,
		)
		combined = list(dict.fromkeys(state['key_statistics'] + stats))
		state['key_statistics'] = combined[-25:]
		# Exclude newlines in bold term capture to prevent multi-line garbage
		for t in re.findall(r'\*\*([A-Z][^*\n]{3,60})\*\*', content):
			if t not in state['defined_terms']:
				state['defined_terms'][t] = ''

	def _build_entity_block(self, entity_state: dict) -> str:
		parts: list[str] = []
		if entity_state['key_statistics']:
			parts.append(
				'ESTABLISHED STATISTICS (do NOT contradict): '
				+ '; '.join(entity_state['key_statistics'][-12:])
			)
		if entity_state['defined_terms']:
			terms = list(entity_state['defined_terms'].keys())[:10]
			parts.append(f'DEFINED TERMS (use consistently): {", ".join(terms)}')
		return '\n'.join(parts)

	# ── Rolling Context ────────────────────────────────────────────────────────

	def _build_rolling_context(
		self, summaries: list[str], generated: list[GeneratedSection]
	) -> str:
		parts: list[str] = []
		recent = summaries[-_ROLLING_SUMMARY_LIMIT:]
		if recent:
			parts.append('PRIOR SECTIONS (maintain consistency):')
			offset = max(0, len(summaries) - _ROLLING_SUMMARY_LIMIT)
			for i, s in enumerate(recent):
				parts.append(f'  {offset + i + 1}. {s}')
		# Add last section's opening prose for smooth transition.
		# The last summary is already in `recent` — include the raw excerpt separately
		# for prose-level continuity, not as a duplicate summary.
		if generated and summaries:
			parts.append(f'\nLAST SECTION EXCERPT (for prose transition):\n{generated[-1].content[:800]}')
		text = '\n'.join(parts)
		if len(text) > _MAX_CONTEXT_CHARS:
			text = text[:_MAX_CONTEXT_CHARS]
			last_nl = text.rfind('\n')
			if last_nl > _MAX_CONTEXT_CHARS // 2:
				text = text[:last_nl]
		return text

	# ── RAG Integration ────────────────────────────────────────────────────────

	def _retrieve_section_evidence(self, spec: SectionSpec) -> str:
		if not self.search_engine:
			return ''
		results: list[dict] = []
		for q in ([spec.title] + spec.key_points[:2])[:2]:
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
			snippet = (r.get('body') or r.get('snippet') or '')[:350]
			lines.append(f'[{title}]({url})\n{snippet}')
		return '\n\n'.join(lines)

	# ── Section Summary ────────────────────────────────────────────────────────

	def _summarize_section(self, title: str, content: str) -> str:
		lines = [
			l.strip() for l in content.splitlines()
			if l.strip()
			and not l.startswith('#')
			and not l.startswith('|')
			and not l.startswith('*Source:')
			and not l.startswith('```')
		]
		if lines:
			text = ' '.join(lines[:3])[:_SUMMARY_MAX_CHARS]
			return f'{title}: {text}'
		return title

	# ── Assembly ───────────────────────────────────────────────────────────────

	def _build_final_document(self, plan: DocumentPlan, toc: str, body: str) -> str:
		parts = [f'# {plan.title}']
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
		frac = str(time.time()).split('.')[-1][:4]  # sub-second suffix avoids collisions
		path = _OUTPUT_DIR / f'{slug}_{ts}_{frac}.md'
		path.write_text(content, encoding='utf-8')
		return str(path)

	def _render_pdf(self, md_path: str) -> str | None:
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
				p = Path(out_path)
				if r.returncode == 0 and p.exists() and p.stat().st_size > 0:
					return out_path
			except (FileNotFoundError, subprocess.TimeoutExpired):
				continue
		return None

	def _render_docx(self, md_path: str) -> str | None:
		out_path = md_path.replace('.md', '.docx')
		template = Path(__file__).parent.parent / 'data' / 'templates' / 'corporate-template.docx'
		extra    = ['--reference-doc', str(template)] if template.exists() else []
		try:
			r = subprocess.run(
				['pandoc', md_path, '-o', out_path, '--toc', *extra],
				capture_output=True, timeout=120,
			)
			p = Path(out_path)
			if r.returncode == 0 and p.exists() and p.stat().st_size > 0:
				return out_path
		except (FileNotFoundError, subprocess.TimeoutExpired):
			pass
		return None

	# ── Utilities ──────────────────────────────────────────────────────────────

	@staticmethod
	def _extract_json_span(text: str, open_ch: str, close_ch: str) -> str | None:
		"""
		Depth-counting span extractor with string-state tracking.
		Immune to { } inside string literals — a common LLM prose preamble pattern.
		"""
		depth, start = 0, None
		in_str, esc  = False, False
		for i, ch in enumerate(text):
			if in_str:
				if esc:
					esc = False
				elif ch == '\\':
					esc = True
				elif ch == '"':
					in_str = False
				continue
			if ch == '"':
				in_str = True
				continue
			if ch == open_ch:
				if start is None:
					start = i
				depth += 1
			elif ch == close_ch:
				depth -= 1
				if depth == 0 and start is not None:
					return text[start:i + 1]
		return None

	def _llm_text(self, prompt: str) -> str:
		"""
		Call the LLM and strip model-internal reasoning blocks.

		Handles Qwen3/lfm2.5-style <think>...</think> tokens and partial blocks
		where the model never closes the tag.
		Content after the LAST </think> tag is the answer; if no closing tag is
		found, everything from <think> onward is stripped.
		"""
		raw = self.ai_engine.generate_text(prompt)
		return self._clean_response(raw)

	@staticmethod
	def _clean_response(text: str) -> str:
		"""Strip <think>...</think> reasoning blocks from model output."""
		if '<think>' not in text:
			return text
		# Split on </think> — take everything after the LAST closing tag as the answer
		parts = text.split('</think>')
		if len(parts) > 1:
			return parts[-1].strip()
		# Unclosed <think> block — strip from the opening tag to end
		return text[:text.index('<think>')].strip()

	def _llm_json(self, prompt: str, fallback: dict) -> dict:
		try:
			response = self._llm_text(prompt)
			# Try raw parse first — handles models that return clean JSON
			stripped = response.strip()
			if stripped.startswith('{'):
				try:
					return json.loads(stripped)
				except json.JSONDecodeError:
					pass
			# Fall back to span extraction (JSON embedded in prose)
			span = self._extract_json_span(response, '{', '}')
			if span:
				return json.loads(span)
		except Exception:
			pass
		return dict(fallback)

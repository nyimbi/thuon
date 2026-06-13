# capabilities/long_form_document_engine.py
"""
Long-form document engine — generates 50,000–200,000-word (100–400+ page) documents
of consulting-grade quality from Ollama models.

Architecture (RaPID + DOME + LongWriter, 2024-2025 research):
  Plan → pre-number all exhibits (LaTeX two-pass) → serial section generation
  (rolling summaries + entity state JSON) → token resolution → ToC assembly
  → optional Pandoc PDF render

Key techniques:
  - RefRegistry: all section/exhibit numbers assigned BEFORE any LLM call
  - Entity state JSON: tracks defined terms, statistics, claims across all sections
  - Rolling context: last 3 section summaries + immediate predecessor excerpt
  - Token system: [[SEC:id]] / [[EX:id]] — LLM never writes bare numbers, resolved post-hoc
  - Self-consistency N=3: executive summary and conclusions generated 3×, best selected
  - Mermaid: flowchart, quadrantChart, gantt, pie — embedded as fenced code blocks
  - Data-first tables: explicit GFM table instructions per exhibit spec
  - Contradiction prevention: entity state injected into every section call
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field

from core.ai_engine import AIModel


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

_SELF_CONSISTENCY_N     = 3       # redundant generation for key sections
_ROLLING_SUMMARY_LIMIT  = 3       # how many prior summaries to keep in context
_MAX_CONTEXT_CHARS      = 4_000   # total rolling context chars per section call
_SUMMARY_MAX_CHARS      = 500     # max chars per section summary
_DEFAULT_WORD_TARGET    = 50_000  # ~200 pages
_OUTPUT_DIR             = Path(__file__).parent.parent / 'data' / 'long_documents'

_DOCUMENT_TYPE_GUIDES: dict[str, str] = {
	'report': (
		'Structure: Executive Summary → Introduction → Background → '
		'Analysis (3-5 major sections) → Findings → Recommendations → Conclusion → Appendices. '
		'Data-driven exhibits. Each section has specific findings, not generic commentary.'
	),
	'whitepaper': (
		'Structure: Abstract → Problem Statement → Current State → '
		'Proposed Solution/Framework → Implementation → Case Studies → Conclusion → References. '
		'Thought leadership tone. Position paper, not just description.'
	),
	'proposal': (
		'Structure: Executive Summary → Understanding of Requirements → Technical Approach → '
		'Management Plan → Team Qualifications → Past Performance → Pricing Rationale → '
		'Risk Management → Conclusion. Compliance-oriented. Address all requirements explicitly.'
	),
	'strategy': (
		'Structure: Situation Assessment → Market/Competitive Analysis → '
		'Strategic Options (minimum 3) → Recommended Strategy → Implementation Roadmap → '
		'Financial Model → Risk Analysis → Governance & KPIs → Conclusion. '
		'BCG/McKinsey style. Each option needs explicit pros/cons and selection rationale.'
	),
}

_MERMAID_TYPES = ('flowchart', 'sequenceDiagram', 'stateDiagram-v2', 'pie',
                  'quadrantChart', 'gantt', 'timeline', 'erDiagram', 'classDiagram')


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
	level:        int = 1         # 1=H1, 2=H2, 3=H3
	parent_id:    str | None = None
	key_points:   list[str] = Field(default_factory=list)
	word_target:  int = 500
	exhibits:     list[ExhibitSpec] = Field(default_factory=list)
	dependencies: list[str] = Field(default_factory=list)
	is_key:       bool = False    # True → self-consistency N=3

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
	content:    str          # resolved markdown
	raw:        str          # pre-resolution content
	word_count: int
	summary:    str          # brief summary for rolling context
	issues:     list[str] = Field(default_factory=list)

class LongDocResult(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)
	title:           str
	markdown:        str
	toc:             str
	word_count:      int
	section_count:   int
	exhibit_count:   int
	issues:          list[str] = Field(default_factory=list)
	elapsed_seconds: float = 0.0
	output_path:     str | None = None
	pdf_path:        str | None = None
	status:          str = 'ok'


# ---------------------------------------------------------------------------
# Reference registry — LaTeX-style two-pass numbering
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\[\[([A-Z]+):([a-z_0-9\-]+)\]\]')


class RefRegistry:
	"""
	Pre-assigns all section and exhibit numbers before any LLM call.
	LLMs use [[SEC:id]] / [[EX:id]] tokens; this class resolves them post-generation.
	"""

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
			for sid, num in list(self.sections.items())[:20]:  # cap to avoid bloat
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
		"""Audit raw LLM output for bare number leakage (LLM wrote 'Section 3' instead of using tokens)."""
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
	Generates 50,000–200,000-word documents from Ollama models via hierarchical
	planning + serial section generation with rolling context and entity state.

	Usage:
	    engine = LongFormDocumentEngine(ai_engine)
	    result = engine.generate(
	        topic="Digital Transformation Strategy for Mid-Market Manufacturers",
	        document_type="strategy",
	        target_pages=150,
	    )
	    print(result['output_path'])  # path to saved .md file
	"""

	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

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
		save_output:     bool = True,
	) -> dict:
		"""
		Generate a long-form document on the given topic.

		Args:
		    topic:           Central topic or question the document addresses
		    document_type:   'report' | 'whitepaper' | 'proposal' | 'strategy'
		    target_audience: Reader profile (e.g. 'C-suite executives, board members')
		    context:         Source material, background, or data to draw from
		    target_pages:    Approximate length in pages (250 words/page)
		    sections_hint:   Optional comma-separated section titles to include
		    render_pdf:      If True, attempt Pandoc PDF rendering
		    save_output:     If True, save .md to data/long_documents/

		Returns:
		    LongDocResult as dict with keys: title, markdown, toc, word_count,
		    section_count, exhibit_count, issues, elapsed_seconds, output_path, status
		"""
		start  = time.time()
		issues: list[str] = []

		# Stage 1 — Plan
		target_words = target_pages * 250
		plan = self._plan_document(
			topic, document_type, target_audience, context, target_words, sections_hint
		)
		if not plan.sections:
			return {
				'status': 'error',
				'error':  'Planning produced no sections',
				'topic':  topic,
			}

		# Stage 2 — Pre-number all exhibits (LaTeX two-pass)
		registry = RefRegistry(plan)

		# Stage 3 — Initialize entity state
		entity_state = self._init_entity_state(topic, plan)

		# Stage 4 — Generate sections serially with rolling context
		generated: list[GeneratedSection] = []
		summaries: list[str] = []

		for sec in plan.sections:
			rolling_ctx = self._build_rolling_context(summaries, generated)
			gs = self._generate_section(
				sec, plan, registry, rolling_ctx, entity_state, context
			)
			generated.append(gs)
			summaries.append(gs.summary)
			self._update_entity_state(entity_state, gs.content)
			issues.extend(gs.issues)

		# Stage 5 — Assemble body
		body_md = '\n\n'.join(gs.content for gs in generated)

		# Stage 6 — Generate ToC from assembled body
		headings = _parse_headings(body_md)
		toc_md   = _build_toc(headings)

		# Stage 7 — Build full document
		document_md = self._build_final_document(plan, toc_md, body_md)

		# Final audit
		issues += registry.audit(document_md)

		# Counts
		total_words   = sum(len(gs.content.split()) for gs in generated)
		exhibit_count = sum(len(gs.spec.exhibits) for gs in generated)

		# Stage 8 — Save
		output_path: str | None = None
		if save_output:
			output_path = self._save_markdown(plan.title, document_md)

		# Stage 9 — Optional PDF
		pdf_path: str | None = None
		if render_pdf and output_path:
			pdf_path = self._render_pdf(output_path)

		result = LongDocResult(
			title           = plan.title,
			markdown        = document_md,
			toc             = toc_md,
			word_count      = total_words,
			section_count   = len(generated),
			exhibit_count   = exhibit_count,
			issues          = issues[:20],
			elapsed_seconds = round(time.time() - start, 1),
			output_path     = output_path,
			pdf_path        = pdf_path,
			status          = 'ok',
		)
		return result.model_dump()

	# ── Stage 1: Document Planning ─────────────────────────────────────────────

	def _plan_document(
		self,
		topic:         str,
		document_type: str,
		audience:      str,
		context:       str,
		word_target:   int,
		sections_hint: str,
	) -> DocumentPlan:
		page_target = word_target // 250
		type_guide  = _DOCUMENT_TYPE_GUIDES.get(document_type, _DOCUMENT_TYPE_GUIDES['report'])

		hint_block = f'\nPreferred sections (include these): {sections_hint}' if sections_hint else ''
		ctx_block  = f'\nContext/background:\n{context[:2000]}' if context else ''

		prompt = f"""/think
You are an expert document architect. Design a detailed hierarchical outline for a high-quality {document_type}.

Topic: {topic}
Target audience: {audience or 'business professionals'}
Target length: {word_target:,} words (~{page_target} pages)
Document type guidance: {type_guide}{hint_block}{ctx_block}

Requirements:
- Use 3 levels of hierarchy (level 1=H1 main sections, level 2=H2 subsections, level 3=H3)
- 6-10 top-level sections, each with 3-6 subsections for a {page_target}-page document
- Include exhibits (tables, charts, mermaid diagrams) where data visualization adds value
- Mark is_key=true for: executive summary, main findings, recommendations, conclusion
- Word targets must sum to approximately {word_target:,}
- Assign dependencies: if a section references another, list its id in dependencies[]
- Use descriptive snake_case IDs (e.g. "competitive_landscape_analysis")

Return ONLY valid JSON:
{{
  "title": "Full compelling document title",
  "subtitle": "Optional subtitle or edition",
  "document_type": "{document_type}",
  "target_audience": "{audience or 'business professionals'}",
  "executive_summary_brief": "One sentence summarizing the document's central conclusion",
  "total_word_target": {word_target},
  "sections": [
    {{
      "id": "executive_summary",
      "title": "Executive Summary",
      "level": 1,
      "parent_id": null,
      "key_points": ["key finding 1", "key recommendation 1"],
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
      "key_points": ["TAM/SAM/SOM breakdown", "5-year CAGR by segment"],
      "word_target": 2500,
      "is_key": false,
      "exhibits": [
        {{
          "id": "market_size_table",
          "type": "table",
          "title": "Market Size by Segment 2024-2030 ($B)",
          "description": "Revenue by segment with CAGR, indexed to 2024 baseline",
          "data": null
        }},
        {{
          "id": "growth_trajectory_chart",
          "type": "mermaid",
          "title": "Revenue Growth by Segment",
          "description": "xychart-beta bar chart showing 5-year revenue projection",
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
				raw_exhibits = s.pop('exhibits', []) or []
				exhibits = []
				for e in raw_exhibits:
					if isinstance(e, dict) and e.get('id') and e.get('type') and e.get('title'):
						exhibits.append(ExhibitSpec(
							id=e['id'], type=e['type'], title=e['title'],
							description=e.get('description', ''),
							data=e.get('data'),
						))
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
			SectionSpec(id='executive_summary', title='Executive Summary', level=1, word_target=800, is_key=True),
			SectionSpec(id='introduction', title='Introduction and Background', level=1, word_target=600),
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
			title             = topic,
			document_type     = doc_type,
			target_audience   = audience,
			sections          = sections,
			total_word_target = words,
		)

	# ── Entity State ───────────────────────────────────────────────────────────

	def _init_entity_state(self, topic: str, plan: DocumentPlan) -> dict:
		return {
			'topic':             topic,
			'document_title':    plan.title,
			'defined_terms':     {},   # term → brief definition
			'key_statistics':    [],   # "X grows at 12% CAGR" style claims
			'entities_mentioned':[],   # organizations, people, products
			'claims_made':       [],   # key assertions established so far
		}

	def _update_entity_state(self, state: dict, content: str) -> None:
		# Extract percentage / currency statistics
		stats = re.findall(
			r'[\$£€]?\s*\d+(?:\.\d+)?\s*(?:%|percent|million|billion|trillion|bn|mn|M|B|T)',
			content, re.I,
		)
		combined = list(dict.fromkeys(state['key_statistics'] + stats))
		state['key_statistics'] = combined[-25:]

		# Extract bolded terms as potential definitions
		for t in re.findall(r'\*\*([A-Z][^*]{3,60})\*\*', content):
			if t not in state['defined_terms']:
				state['defined_terms'][t] = ''

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
			prev_excerpt = generated[-1].content[:1_500]
			parts.append(f'\nPREVIOUS SECTION EXCERPT (for smooth transition):\n{prev_excerpt}')

		ctx = '\n'.join(parts)
		return ctx[:_MAX_CONTEXT_CHARS]

	# ── Section Generation ─────────────────────────────────────────────────────

	def _generate_section(
		self,
		spec:           SectionSpec,
		plan:           DocumentPlan,
		registry:       RefRegistry,
		rolling_ctx:    str,
		entity_state:   dict,
		source_context: str,
	) -> GeneratedSection:
		heading_mark = '#' * spec.level

		# Exhibit instructions
		exhibit_block = self._build_exhibit_instructions(spec, registry)

		# Entity state context
		entity_block = self._build_entity_block(entity_state)

		# Source context (capped)
		src_block = f'\nSOURCE MATERIAL (draw from this, do not contradict):\n{source_context[:1_500]}' \
		            if source_context else ''

		prompt = f"""/no_think
You are writing one section of a high-quality {plan.document_type} titled "{plan.title}".
Target audience: {plan.target_audience or 'business professionals'}.

{rolling_ctx}
{entity_block}
{registry.to_prompt_block()}

CRITICAL RULES:
1. Use [[SEC:id]] and [[EX:id]] tokens from the registry — NEVER write "Section 3" or "Exhibit 2" directly
2. Do NOT contradict established statistics above
3. Write ONLY this section's content — no meta-commentary like "In this section we will..."
4. Target: {spec.word_target} words. Write with depth and specificity to hit this target.
5. Use **bold** for first introduction of key terms. Use markdown lists and tables where appropriate.
6. Be concrete: use specific numbers, named examples, and actionable insights.
{exhibit_block}{src_block}

WRITE THIS SECTION NOW:
{heading_mark} {spec.title}

Key points to cover:
{chr(10).join(f'- {p}' for p in spec.key_points) if spec.key_points else '- Cover the topic thoroughly and specifically'}

Write the section content directly. Do not repeat the heading."""

		if spec.is_key:
			candidates = [self.ai_engine.generate_text(prompt) for _ in range(_SELF_CONSISTENCY_N)]
			content_raw = max(candidates, key=lambda t: len(t.split()))
		else:
			content_raw = self.ai_engine.generate_text(prompt)

		full_raw  = f'{heading_mark} {spec.title}\n\n{content_raw.strip()}'
		issues    = registry.audit(full_raw)   # audit raw text before resolution
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

	def _build_exhibit_instructions(self, spec: SectionSpec, registry: RefRegistry) -> str:
		if not spec.exhibits:
			return ''
		lines = ['\nINSERT THESE EXHIBITS at natural positions within the section:']
		for ex in spec.exhibits:
			label = registry.exhibits.get(ex.id, ex.id)
			lines.append(f'\n**{label}: {ex.title}**')
			lines.append(f'  Description: {ex.description}')
			if ex.type == 'table':
				lines.append(
					'  → Format as a properly-aligned GFM markdown table with a source row at the bottom. '
					'Use action title (insight, not description) as the exhibit heading.'
				)
			elif ex.type == 'mermaid':
				mermaid_hint = self._mermaid_hint(ex)
				lines.append(f'  → Insert as a ```mermaid fenced code block. {mermaid_hint}')
			elif ex.type == 'chart':
				lines.append(
					'  → Present as a structured data table showing the underlying numbers, '
					'followed by a one-sentence key takeaway. Label as the exhibit above.'
				)
		return '\n'.join(lines)

	@staticmethod
	def _mermaid_hint(ex: ExhibitSpec) -> str:
		desc_lower = ex.description.lower()
		if 'flow' in desc_lower or 'process' in desc_lower:
			return 'Use flowchart LR or TD direction. Declare all nodes before edges.'
		if 'timeline' in desc_lower or 'roadmap' in desc_lower or 'gantt' in desc_lower:
			return 'Use gantt chart with dateFormat YYYY-MM and sections by phase.'
		if '2x2' in desc_lower or 'matrix' in desc_lower or 'quadrant' in desc_lower:
			return 'Use quadrantChart. Label all four quadrants. Place 4-8 items.'
		if 'sequence' in desc_lower or 'interaction' in desc_lower:
			return 'Use sequenceDiagram. Show 3-5 actors with clear message labels.'
		if 'pie' in desc_lower or 'share' in desc_lower or 'breakdown' in desc_lower:
			return 'Use pie chart with title. Limit to 6-8 slices.'
		if 'bar' in desc_lower or 'revenue' in desc_lower or 'trend' in desc_lower:
			return 'Use xychart-beta with bar or line mark. Include axis labels and title.'
		return 'Choose the most appropriate chart type from: flowchart, pie, gantt, quadrantChart, xychart-beta.'

	def _build_entity_block(self, entity_state: dict) -> str:
		parts: list[str] = []
		if entity_state['key_statistics']:
			stats = entity_state['key_statistics'][-12:]
			parts.append(f'ESTABLISHED STATISTICS (do NOT contradict): {"; ".join(stats)}')
		if entity_state['defined_terms']:
			terms = list(entity_state['defined_terms'].keys())[:10]
			parts.append(f'DEFINED TERMS (use consistently, do NOT redefine): {", ".join(terms)}')
		return '\n'.join(parts)

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
		"""Attempt PDF rendering via Pandoc (Typst preferred, pdflatex fallback)."""
		out_path = md_path.replace('.md', '.pdf')
		for engine_args in (
			['--to=typst', '--pdf-engine=typst'],
			['--pdf-engine=xelatex'],
			[],
		):
			try:
				result = subprocess.run(
					['pandoc', md_path, '-o', out_path,
					 '--toc', '--number-sections',
					 '--variable=geometry:margin=2.5cm',
					 '--variable=fontsize=11pt',
					 *engine_args],
					capture_output=True, timeout=180,
				)
				if result.returncode == 0:
					return out_path
			except (FileNotFoundError, subprocess.TimeoutExpired):
				continue
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

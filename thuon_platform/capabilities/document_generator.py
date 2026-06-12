# capabilities/document_generator.py
"""
LLM-powered document generator. Produces real DOCX/PDF/PPTX/XLSX files
from a topic description or structured data.
"""

from __future__ import annotations
import os
import re


class DocumentGenerator:
	def __init__(self, ai_engine, output_dir: str = '/tmp/thuon_docs'):
		self.ai_engine = ai_engine
		self.output_dir = output_dir
		os.makedirs(output_dir, exist_ok=True)

	def generate(
		self,
		topic: str,
		format: str = 'docx',
		doc_type: str = 'report',
		context: str = '',
		output_path: str | None = None,
		rows: list[dict] | None = None,
		slides: list[dict] | None = None,
	) -> dict:
		"""
		Generate a document from a topic description.

		Args:
			topic:       Subject matter or title
			format:      'docx' | 'pdf' | 'pptx' | 'xlsx'
			doc_type:    'report' | 'proposal' | 'memo' | 'presentation' | 'spreadsheet'
			context:     Optional extra context to include in the LLM prompt
			output_path: Override output file path
			rows:        For xlsx — list of dicts (bypasses LLM generation)
			slides:      For pptx — explicit slide list [{title, content}]
		"""
		from core.document_engine import generate_document

		fmt = format.lower().lstrip('.')
		safe = re.sub(r'[^\w\s-]', '', topic)[:50].strip().replace(' ', '_')
		out = output_path or os.path.join(self.output_dir, f'{safe}.{fmt}')

		if fmt == 'xlsx' and rows:
			path = generate_document('xlsx', '', topic, out, rows=rows)
			return {'output_path': path, 'format': 'xlsx', 'topic': topic, 'status': 'ok'}

		content = self.ai_engine.generate_text(self._build_prompt(topic, doc_type, context, fmt))
		title = self._extract_title(content, topic)

		if fmt == 'pptx' and slides is None:
			slides = self._extract_slides(content)

		path = generate_document(fmt, content, title, out, slides=slides)
		return {
			'output_path':  path,
			'format':       fmt,
			'doc_type':     doc_type,
			'title':        title,
			'word_count':   len(content.split()),
			'topic':        topic,
			'status':       'ok',
		}

	def _build_prompt(self, topic: str, doc_type: str, context: str, fmt: str) -> str:
		fmt_hints = {
			'pptx': 'Use ## headings to separate slides. Keep each section concise.',
			'xlsx': 'Return a pipe-delimited table with headers.',
			'pdf':  'Write professional flowing prose suitable for a formal PDF report.',
			'docx': 'Use # for main headings, ## for sections, - for bullet points.',
		}
		return (
			f'You are a senior business analyst. Write a professional {doc_type} about: {topic}.\n'
			+ (f'Context: {context}\n' if context else '')
			+ f'{fmt_hints.get(fmt, "")}\n'
			'Structure: executive summary, key findings/content sections, recommendations/conclusions.\n'
			'Be specific, data-informed, and actionable. Minimum 500 words.\n\nDocument:'
		)

	def _extract_title(self, content: str, fallback: str) -> str:
		for line in content.split('\n'):
			stripped = line.lstrip('#').strip()
			if stripped and len(stripped) < 120:
				return stripped
		return fallback

	def _extract_slides(self, content: str) -> list[dict]:
		slides: list[dict] = []
		current_title = ''
		current_lines: list[str] = []

		def flush():
			if current_title or current_lines:
				slides.append({'title': current_title, 'content': '\n'.join(current_lines)})

		for line in content.split('\n'):
			line = line.rstrip()
			if line.startswith('#'):
				flush()
				current_title = line.lstrip('#').strip()
				current_lines = []
			elif line:
				current_lines.append(line)

		flush()
		return slides

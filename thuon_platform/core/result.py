# core/result.py
"""
ThuonResult — fluent wrapper around every capability's output dict.

Supports:
  result.to_pdf()         → generates PDF from result content
  result.to_docx()        → generates DOCX
  result.to_slides()      → generates PPTX
  result.to_xlsx(rows)    → generates XLSX from tabular data
  result.as_diagram()     → generates Mermaid diagram from result
  result.trace            → execution trace if explain=True was used
  result.explain()        → human-readable trace summary
"""

from __future__ import annotations
import os
import json
import tempfile
from typing import Any


class ThuonResult:
	"""Dict-compatible fluent result wrapper."""

	def __init__(
		self,
		data: dict,
		capability_name: str = '',
		trace: dict | None = None,
	):
		self._data = data
		self.capability_name = capability_name
		self._trace = trace or {}

	# ── Dict-like interface ──────────────────────────────────────────────────

	def __getitem__(self, key: str) -> Any:
		return self._data[key]

	def __setitem__(self, key: str, value: Any) -> None:
		self._data[key] = value

	def __contains__(self, key: str) -> bool:
		return key in self._data

	def __repr__(self) -> str:
		keys = list(self._data.keys())[:6]
		return f'ThuonResult({self.capability_name!r}, keys={keys})'

	def get(self, key: str, default: Any = None) -> Any:
		return self._data.get(key, default)

	def keys(self):
		return self._data.keys()

	def values(self):
		return self._data.values()

	def items(self):
		return self._data.items()

	def to_dict(self) -> dict:
		return dict(self._data)

	# ── Document transforms ──────────────────────────────────────────────────

	def to_pdf(self, output_path: str | None = None) -> 'ThuonResult':
		"""Render result content as a PDF file."""
		path = self._render_doc('pdf', output_path)
		self._data['pdf_path'] = path
		return self

	def to_docx(self, output_path: str | None = None) -> 'ThuonResult':
		"""Render result content as a DOCX file."""
		path = self._render_doc('docx', output_path)
		self._data['docx_path'] = path
		return self

	def to_slides(self, output_path: str | None = None) -> 'ThuonResult':
		"""Render result content as a PowerPoint presentation."""
		path = self._render_doc('pptx', output_path)
		self._data['pptx_path'] = path
		return self

	def to_xlsx(
		self,
		rows: list[dict] | None = None,
		output_path: str | None = None,
		sheet_name: str = 'Results',
	) -> 'ThuonResult':
		"""Render tabular data as an Excel file."""
		from core.document_engine import generate_document
		out = output_path or _tmp_path('xlsx')
		# Try to find rows in result if not provided
		if rows is None:
			rows = self._data.get('rows') or self._data.get('data') or [self._data]
		generate_document('xlsx', '', self.capability_name, out, rows=rows, sheet_name=sheet_name)
		self._data['xlsx_path'] = out
		return self

	def as_diagram(
		self,
		diagram_type: str = 'flowchart',
		output_path: str | None = None,
		ai_engine=None,
	) -> 'ThuonResult':
		"""Generate a Mermaid diagram summarizing this result."""
		if ai_engine is None:
			from core.ai_engine import OllamaModel
			ai_engine = OllamaModel()
		from capabilities.diagram_generator import DiagramGenerator
		gen = DiagramGenerator(ai_engine)
		description = self._content_for_doc()[:500]
		diagram = gen.generate(description, diagram_type=diagram_type, output_path=output_path)
		self._data['diagram'] = diagram
		return self

	# ── Trace & explain (#9) ────────────────────────────────────────────────

	@property
	def trace(self) -> dict:
		return self._trace

	def explain(self) -> str:
		"""Return a human-readable trace of how this result was produced."""
		if not self._trace:
			return f'No trace available for {self.capability_name}. Use explain=True when calling.'
		lines = [f'Execution trace: {self.capability_name}', '']
		for key, val in self._trace.items():
			lines.append(f'  {key}: {val}')
		return '\n'.join(lines)

	# ── Internal ─────────────────────────────────────────────────────────────

	def _render_doc(self, fmt: str, output_path: str | None) -> str:
		from core.document_engine import generate_document
		out = output_path or _tmp_path(fmt)
		content = self._content_for_doc()
		title = (
			self._data.get('title')
			or self._data.get('report_type')
			or self.capability_name
			or 'Thuon Output'
		)
		generate_document(fmt, content, title, out)
		return out

	def _content_for_doc(self) -> str:
		"""Extract the best text content from this result."""
		for key in ('content', 'report', 'analysis', 'result', 'text', 'summary',
					'answer', 'proposal_content', 'brief'):
			val = self._data.get(key)
			if isinstance(val, str) and len(val) > 0:
				return val
		# Fall back to JSON rendering
		return json.dumps(self._data, indent=2, default=str)


def _tmp_path(ext: str) -> str:
	d = '/tmp/thuon_results'
	os.makedirs(d, exist_ok=True)
	fd, path = tempfile.mkstemp(suffix=f'.{ext}', dir=d)
	os.close(fd)
	return path

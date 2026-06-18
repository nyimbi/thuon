# capabilities/rfp_ingester.py
"""
Atomic capability: parse an RFP from URL, file path, or raw text.
Returns structured JSON with title, issuer, deadline, requirements, etc.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class RFPIngester:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def ingest(
		self,
		rfp_source: str,
	) -> dict:
		"""
		Parse an RFP from a URL, file path, or pasted text.

		Args:
			rfp_source: URL, absolute file path (.pdf/.docx/.txt), or raw RFP text.

		Returns:
			{title, issuer, deadline, scope_summary, evaluation_criteria,
			 requirements, page_limits, budget, attachments_required, raw_text}
		"""
		raw_text = self._extract_text(rfp_source)

		prompt = (
			'You are an expert proposal manager. Parse the following RFP document and extract '
			'all key information. Return ONLY a valid JSON object with these exact keys:\n'
			'- title (str): full title of the RFP/solicitation\n'
			'- issuer (str): name of the issuing organization\n'
			'- deadline (str): submission deadline (ISO date or descriptive)\n'
			'- scope_summary (str): 3-5 sentence summary of what is being procured\n'
			'- evaluation_criteria (list of objects with keys: criterion, weight_pct, description)\n'
			'- requirements (list of objects with keys: req_id, text, type [shall/should/may], section)\n'
			'- page_limits (object): {total, technical, management, past_performance, pricing, notes}\n'
			'- budget (str): stated budget or "Not disclosed"\n'
			'- attachments_required (list of str): required forms and attachments\n\n'
			f'RFP TEXT:\n{raw_text[:12000]}'
		)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response)
		if result is not None:
			result['raw_text'] = raw_text[:5000]
			result['source']   = rfp_source
			return result

		return {
			'title':               'Unknown RFP',
			'issuer':              'Unknown',
			'deadline':            'Unknown',
			'scope_summary':       raw_text[:500],
			'evaluation_criteria': [],
			'requirements':        [],
			'page_limits':         {},
			'budget':              'Not disclosed',
			'attachments_required': [],
			'raw_text':            raw_text[:5000],
			'source':              rfp_source,
		}

	# ── Text extraction ───────────────────────────────────────────────────────

	def _extract_text(self, source: str) -> str:
		import os
		if source.startswith('http://') or source.startswith('https://'):
			return self._fetch_url(source)
		if os.path.exists(source):
			return self._read_file(source)
		# Treat as raw text
		return source

	def _fetch_url(self, url: str) -> str:
		try:
			import trafilatura
			downloaded = trafilatura.fetch_url(url)
			if downloaded:
				text = trafilatura.extract(downloaded)
				if text:
					return text
		except ImportError:
			pass
		import requests
		from bs4 import BeautifulSoup
		r = requests.get(url, timeout=20, headers={'User-Agent': 'Thuon RFP Ingester/1.0'})
		r.raise_for_status()
		soup = BeautifulSoup(r.text, 'html.parser')
		for tag in soup(['script', 'style', 'nav', 'footer']):
			tag.decompose()
		return soup.get_text('\n', strip=True)[:20000]

	def _read_file(self, path: str) -> str:
		from pathlib import Path
		ext = Path(path).suffix.lower()
		if ext == '.pdf':
			return self._read_pdf(path)
		if ext in ('.docx', '.doc'):
			from docx import Document
			doc = Document(path)
			return '\n'.join(p.text for p in doc.paragraphs)
		with open(path, encoding='utf-8', errors='replace') as f:
			return f.read()

	def _read_pdf(self, path: str) -> str:
		"""
		Extract text from a PDF. For pages that return < 100 chars (scanned/image),
		fall back to the vision model OCR via pdf2image.
		"""
		from pypdf import PdfReader
		reader = PdfReader(path)
		pages: list[str] = []
		for i, page in enumerate(reader.pages):
			text = page.extract_text() or ''
			if len(text.strip()) >= 100:
				pages.append(text)
			else:
				# Low-text page — attempt vision OCR
				ocr_text = self._vision_ocr_page(path, i)
				pages.append(ocr_text if ocr_text else text)
		return '\n\n'.join(pages)

	def _vision_ocr_page(self, pdf_path: str, page_index: int) -> str:
		"""
		Render one PDF page to a temp PNG via pdf2image and OCR it with OllamaVisionModel.
		Returns empty string if pdf2image or the vision model is unavailable.
		"""
		import logging
		import os
		import tempfile
		try:
			from pdf2image import convert_from_path
		except ImportError:
			logging.warning('pdf2image not installed; skipping vision OCR for page %d of %s', page_index, pdf_path)
			return ''
		try:
			images = convert_from_path(pdf_path, dpi=150, first_page=page_index + 1, last_page=page_index + 1)
			if not images:
				return ''
		except Exception:
			return ''
		tmp_path = None
		try:
			with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
				tmp_path = tmp.name
			images[0].save(tmp_path, 'PNG')
			if not hasattr(self, '_vision'):
				from core.ai_engine import OllamaVisionModel
				self._vision = OllamaVisionModel()
			return self._vision.extract_text(tmp_path)
		except Exception:
			return ''
		finally:
			if tmp_path and os.path.exists(tmp_path):
				os.unlink(tmp_path)

	def analyze_visual_elements(self, pdf_path: str) -> list[dict]:
		"""
		Extract charts, tables, and diagrams from a PDF using vision model.
		Returns list of {page_num, element_type, description, data}
		"""
		import logging
		import os
		import tempfile
		try:
			from pdf2image import convert_from_path
		except ImportError:
			logging.warning('pdf2image not installed; analyze_visual_elements requires it')
			return []
		from pypdf import PdfReader
		try:
			reader = PdfReader(pdf_path)
			page_count = len(reader.pages)
		except Exception:
			return []
		if not hasattr(self, '_vision'):
			from core.ai_engine import OllamaVisionModel
			self._vision = OllamaVisionModel()
		results: list[dict] = []
		for page_num in range(page_count):
			tmp_path = None
			try:
				images = convert_from_path(pdf_path, dpi=150, first_page=page_num + 1, last_page=page_num + 1)
				if not images:
					continue
				with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
					tmp_path = tmp.name
				images[0].save(tmp_path, 'PNG')
				analysis = self._vision.analyze_document_page(tmp_path)
				# Filter for pages containing tables or charts
				element_type = analysis.get('element_type', '')
				if any(kw in str(element_type).lower() for kw in ('table', 'chart', 'diagram', 'graph', 'figure')):
					results.append({
						'page_num':    page_num + 1,
						'element_type': element_type,
						'description': analysis.get('description', ''),
						'data':        analysis.get('data', {}),
					})
			except Exception as exc:
				logging.warning('Vision analysis failed for page %d of %s: %s', page_num + 1, pdf_path, exc)
			finally:
				if tmp_path and os.path.exists(tmp_path):
					os.unlink(tmp_path)
		return results

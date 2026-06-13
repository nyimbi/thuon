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
			from pypdf import PdfReader
			reader = PdfReader(path)
			return '\n\n'.join(p.extract_text() or '' for p in reader.pages)
		if ext in ('.docx', '.doc'):
			from docx import Document
			doc = Document(path)
			return '\n'.join(p.text for p in doc.paragraphs)
		with open(path, encoding='utf-8', errors='replace') as f:
			return f.read()

# core/knowledge_ingestion.py
"""
Knowledge ingestion pipeline: PDF/DOCX/plain text/URL → text chunks → BM25 index.
Deduplicates by SHA-256 content hash. Optionally persists chunk store to JSON.
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path


def _chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
	words = text.split()
	chunks = []
	i = 0
	while i < len(words):
		chunk = ' '.join(words[i:i + size])
		chunks.append(chunk)
		i += size - overlap
	return [c for c in chunks if len(c.strip()) > 50]


def _extract_pdf(path: str) -> str:
	from pypdf import PdfReader
	reader = PdfReader(path)
	return '\n\n'.join(p.extract_text() or '' for p in reader.pages)


def _extract_docx(path: str) -> str:
	from docx import Document
	doc = Document(path)
	return '\n'.join(p.text for p in doc.paragraphs)


def _extract_url(url: str) -> str:
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
	r = requests.get(url, timeout=15, headers={'User-Agent': 'Thuon/1.0'})
	r.raise_for_status()
	soup = BeautifulSoup(r.text, 'html.parser')
	for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
		tag.decompose()
	return soup.get_text('\n', strip=True)[:20000]


class KnowledgeIngestionPipeline:
	"""
	Ingests documents and URLs into a BM25-indexed chunk store.

	Usage:
		pipe = KnowledgeIngestionPipeline(store_path='/tmp/kb.json')
		pipe.ingest_file('report.pdf')
		pipe.ingest_url('https://example.com/article')
		results = pipe.search('AI regulation', top_k=5)
		context = pipe.get_context('AI regulation')
	"""

	def __init__(self, store_path: str | None = None):
		self.store_path = store_path
		self._chunks: list[dict] = []
		self._index = None
		if store_path and os.path.exists(store_path):
			self._load()

	# ── Ingest ───────────────────────────────────────────────────────────────

	def ingest_text(self, text: str, source: str = 'text') -> dict:
		sha = hashlib.sha256(text.encode()).hexdigest()
		if any(c['sha256'] == sha for c in self._chunks):
			return {'status': 'duplicate', 'source': source, 'sha256': sha}
		chunks = _chunk_text(text)
		added = 0
		for i, chunk in enumerate(chunks):
			self._chunks.append({
				'id':     f'{sha[:8]}-{i}',
				'source': source,
				'text':   chunk,
				'sha256': sha,
			})
			added += 1
		if added > 0:
			self._index = None
		if self.store_path:
			self._save()
		return {'status': 'ok', 'source': source, 'chunks_added': added, 'sha256': sha}

	def ingest_file(self, path: str) -> dict:
		ext = Path(path).suffix.lower()
		if ext == '.pdf':
			text = _extract_pdf(path)
		elif ext in ('.docx', '.doc'):
			text = _extract_docx(path)
		else:
			with open(path, encoding='utf-8', errors='replace') as f:
				text = f.read()
		return self.ingest_text(text, source=path)

	def ingest_url(self, url: str) -> dict:
		text = _extract_url(url)
		return self.ingest_text(text, source=url)

	# ── Search ───────────────────────────────────────────────────────────────

	def search(self, query: str, top_k: int = 5) -> list[dict]:
		if not self._chunks:
			return []
		self._ensure_index()
		tokenized_query = query.lower().split()
		scores = self._index.get_scores(tokenized_query)
		ranked = sorted(zip(scores, self._chunks), key=lambda x: -x[0])
		return [
			{'score': float(score), 'source': c['source'], 'text': c['text']}
			for score, c in ranked[:top_k]
			if score > 0
		]

	def get_context(self, query: str, top_k: int = 3) -> str:
		results = self.search(query, top_k=top_k)
		if not results:
			return ''
		parts = [f"[Source: {r['source']}]\n{r['text']}" for r in results]
		return '\n\n---\n\n'.join(parts)

	@property
	def chunk_count(self) -> int:
		return len(self._chunks)

	@property
	def source_count(self) -> int:
		return len({c['source'] for c in self._chunks})

	def clear(self) -> None:
		self._chunks = []
		self._index = None
		if self.store_path and os.path.exists(self.store_path):
			os.remove(self.store_path)

	# ── Internal ─────────────────────────────────────────────────────────────

	def _ensure_index(self) -> None:
		if self._index is None:
			from rank_bm25 import BM25Okapi
			tokenized = [c['text'].lower().split() for c in self._chunks]
			self._index = BM25Okapi(tokenized)

	def _save(self) -> None:
		with open(self.store_path, 'w') as f:
			json.dump(self._chunks, f)

	def _load(self) -> None:
		with open(self.store_path) as f:
			content = f.read().strip()
		if content:
			self._chunks = json.loads(content)

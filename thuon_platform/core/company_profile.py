# core/company_profile.py
"""
Company knowledge base — loads all data/company/*.md files into a BM25 store.
Used by all RFP/content capabilities as company context.
"""

from __future__ import annotations
import threading
from pathlib import Path
from core.knowledge_ingestion import KnowledgeIngestionPipeline
from core.settings_manager import get_settings
from core.bundle import writable_data_dir, app_root


def _default_company_dir() -> Path:
	return writable_data_dir() / 'company'


class CompanyProfile:
	def __init__(self, profile_dir: Path | str | None = None):
		settings = get_settings()
		default = str(_default_company_dir())
		raw = Path(profile_dir or settings.get_setting('company.profile_dir', default))
		resolved = raw if raw.is_absolute() else (app_root().parent / raw)
		self._dir = resolved
		store_path = str(resolved.parent / '_company_kb.json')
		self._kb = KnowledgeIngestionPipeline(store_path=store_path)
		self._lock = threading.Lock()
		self._load_all()

	# ── Public API ────────────────────────────────────────────────────────────

	def get_context(self, topic: str = '', top_k: int = 5) -> str:
		"""BM25 search over company docs; returns formatted context block."""
		with self._lock:
			if not topic:
				# Return all chunks up to top_k when no query
				results = self._kb.search('company capabilities services', top_k=top_k)
			else:
				results = self._kb.search(topic, top_k=top_k)
		if not results:
			return '[Company KB: no documents loaded. Fill in data/company/*.md files.]'
		parts = [f"[{r['source']}]\n{r['text']}" for r in results]
		return '\n\n---\n\n'.join(parts)

	def get_file(self, name: str) -> str:
		"""Return raw markdown of a specific company file (e.g. 'win_themes.md')."""
		if not name.endswith('.md'):
			name = name + '.md'
		path = self._dir / name
		if path.exists():
			return path.read_text(encoding='utf-8')
		return f'[{name} not found in {self._dir}]'

	def list_files(self) -> list[str]:
		if not self._dir.exists():
			return []
		return sorted(p.name for p in self._dir.glob('*.md'))

	def reload(self) -> None:
		"""Re-ingest all company markdown files (called by scheduler hourly)."""
		with self._lock:
			self._kb.clear()
			self._load_all()

	@property
	def chunk_count(self) -> int:
		return self._kb.chunk_count

	# ── Internal ─────────────────────────────────────────────────────────────

	def _load_all(self) -> None:
		if not self._dir.exists():
			return
		for md_file in sorted(self._dir.glob('*.md')):
			try:
				self._kb.ingest_file(str(md_file))
			except Exception as exc:
				import logging
				logging.getLogger('thuon.company_profile').warning('Failed to ingest %s: %s', md_file.name, exc)


# Module-level singleton (created lazily)
_instance: CompanyProfile | None = None
_instance_lock = threading.Lock()


def get_company_profile() -> CompanyProfile:
	global _instance
	if _instance is None:
		with _instance_lock:
			if _instance is None:
				_instance = CompanyProfile()
	return _instance

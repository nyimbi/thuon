# Semantic Scholar Academic Graph API — free, no auth for ≤100 req/5 min
import requests

_BASE = 'https://api.semanticscholar.org/graph/v1'
_FIELDS = 'title,authors,year,abstract,url,citationCount,referenceCount,venue'
_TIMEOUT = 12


def search_papers(query: str, limit: int = 10) -> list[dict]:
	try:
		r = requests.get(
			f'{_BASE}/paper/search',
			params={'query': query, 'limit': min(limit, 100), 'fields': _FIELDS},
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		return r.json().get('data', [])
	except Exception:
		return []


def get_paper(paper_id: str) -> dict:
	try:
		r = requests.get(
			f'{_BASE}/paper/{paper_id}',
			params={'fields': _FIELDS + ',references,citations'},
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		return r.json()
	except Exception:
		return {}


def get_citations(paper_id: str, limit: int = 20) -> list[dict]:
	"""Papers that cite this paper (forward citations)."""
	try:
		r = requests.get(
			f'{_BASE}/paper/{paper_id}/citations',
			params={'limit': limit, 'fields': 'title,year,url,citationCount'},
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		return [c.get('citingPaper', {}) for c in r.json().get('data', [])]
	except Exception:
		return []


def get_references(paper_id: str, limit: int = 20) -> list[dict]:
	"""Papers this paper cites (backward citations)."""
	try:
		r = requests.get(
			f'{_BASE}/paper/{paper_id}/references',
			params={'limit': limit, 'fields': 'title,year,url,citationCount'},
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		return [c.get('citedPaper', {}) for c in r.json().get('data', [])]
	except Exception:
		return []


def format_papers_for_context(papers: list[dict]) -> str:
	lines = []
	for p in papers:
		authors = ', '.join(a.get('name', '') for a in (p.get('authors') or [])[:3])
		abstract = (p.get('abstract') or '')[:300]
		lines.append(
			f"[{p.get('year', '?')}] {p.get('title', 'Untitled')} — {authors}\n"
			f"Citations: {p.get('citationCount', '?')} | {p.get('url', '')}\n"
			f"{abstract}"
		)
	return '\n\n'.join(lines)

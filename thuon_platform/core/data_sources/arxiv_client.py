# arXiv API — completely free, no auth
import requests
import xml.etree.ElementTree as ET

_BASE = 'http://export.arxiv.org/api/query'
_NS = {'atom': 'http://www.w3.org/2005/Atom'}
_TIMEOUT = 15


def search(query: str, max_results: int = 10, sort_by: str = 'relevance') -> list[dict]:
	"""
	sort_by: 'relevance' | 'lastUpdatedDate' | 'submittedDate'
	"""
	try:
		r = requests.get(
			_BASE,
			params={
				'search_query': f'all:{query}',
				'max_results':  max_results,
				'sortBy':       sort_by,
				'sortOrder':    'descending',
			},
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		root = ET.fromstring(r.text)
		results = []
		for entry in root.findall('atom:entry', _NS):
			# PDF/HTML link
			link = ''
			for el in entry.findall('atom:link', _NS):
				if el.get('type') == 'text/html':
					link = el.get('href', '')
			authors = [
				a.findtext('atom:name', '', _NS)
				for a in entry.findall('atom:author', _NS)[:4]
			]
			results.append({
				'title':      entry.findtext('atom:title', '', _NS).strip().replace('\n', ' '),
				'summary':    entry.findtext('atom:summary', '', _NS).strip()[:400],
				'published':  (entry.findtext('atom:published', '', _NS) or '')[:10],
				'url':        link,
				'authors':    authors,
				'categories': [c.get('term', '') for c in entry.findall('atom:category', _NS)[:3]],
			})
		return results
	except Exception:
		return []


def format_papers(papers: list[dict]) -> str:
	lines = []
	for p in papers:
		authors = ', '.join(p.get('authors', []))
		lines.append(
			f"[{p['published']}] {p['title']}\n"
			f"Authors: {authors}\n"
			f"{p['summary']}\n"
			f"{p['url']}"
		)
	return '\n\n'.join(lines)

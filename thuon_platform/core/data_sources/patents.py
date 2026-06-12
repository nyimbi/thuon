# USPTO PatentsView API — free, no auth required
import requests

_BASE    = 'https://search.patentsview.org/api/v1/patent/'
_TIMEOUT = 15
_FIELDS  = [
	'patent_id', 'patent_title', 'patent_abstract',
	'patent_date', 'patent_type',
	'assignees.assignee_organization',
	'inventors.inventor_first_name', 'inventors.inventor_last_name',
]


def search_patents(query: str, limit: int = 10) -> list[dict]:
	payload = {
		'q': {
			'_or': [
				{'_text_any': {'patent_title': query}},
				{'_text_any': {'patent_abstract': query}},
			]
		},
		'f': _FIELDS,
		'o': {'per_page': min(limit, 1000)},
	}
	try:
		r = requests.post(_BASE, json=payload, timeout=_TIMEOUT)
		r.raise_for_status()
		return r.json().get('patents') or []
	except Exception:
		return []


def get_patent(patent_id: str) -> dict:
	payload = {
		'q': {'patent_id': patent_id},
		'f': _FIELDS + ['patent_claims'],
	}
	try:
		r = requests.post(_BASE, json=payload, timeout=_TIMEOUT)
		r.raise_for_status()
		patents = r.json().get('patents') or []
		return patents[0] if patents else {}
	except Exception:
		return {}


def format_patents_for_context(patents: list[dict]) -> str:
	lines = []
	for p in patents:
		title    = p.get('patent_title', 'Untitled')
		date     = p.get('patent_date', '')
		abstract = (p.get('patent_abstract') or '')[:300]
		assignees = ', '.join(
			a.get('assignee_organization', '')
			for a in (p.get('assignees') or [])[:3]
			if a.get('assignee_organization')
		)
		lines.append(
			f"[{p.get('patent_id', '')}] {title} ({date})\n"
			f"Assignee: {assignees}\n"
			f"{abstract}"
		)
	return '\n\n'.join(lines)

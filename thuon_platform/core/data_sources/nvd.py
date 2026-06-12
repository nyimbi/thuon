# NVD (National Vulnerability Database) API 2.0 — free, no key required
# Rate limit: 5 req/30 s without key. With NIST API key: 50 req/30 s.
import requests

_BASE = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
_TIMEOUT = 20


def search_cves(
	keyword: str = '',
	severity: str = '',
	limit: int = 20,
	api_key: str = '',
) -> list[dict]:
	"""
	severity: '' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
	"""
	params: dict = {'resultsPerPage': min(limit, 2000)}
	if keyword:
		params['keywordSearch'] = keyword
	if severity:
		params['cvssV3Severity'] = severity.upper()
	headers = {}
	if api_key:
		headers['apiKey'] = api_key
	try:
		r = requests.get(_BASE, params=params, headers=headers, timeout=_TIMEOUT)
		r.raise_for_status()
		return [_parse(v['cve']) for v in r.json().get('vulnerabilities', [])]
	except Exception:
		return []


def get_cve(cve_id: str, api_key: str = '') -> dict:
	headers = {'apiKey': api_key} if api_key else {}
	try:
		r = requests.get(_BASE, params={'cveId': cve_id}, headers=headers, timeout=_TIMEOUT)
		r.raise_for_status()
		vulns = r.json().get('vulnerabilities', [])
		return _parse(vulns[0]['cve']) if vulns else {}
	except Exception:
		return {}


def _parse(cve: dict) -> dict:
	desc = next(
		(d['value'] for d in cve.get('descriptions', []) if d.get('lang') == 'en'),
		'',
	)
	metrics = cve.get('metrics', {})
	score = severity = vector = None
	for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
		if key in metrics and metrics[key]:
			data = metrics[key][0].get('cvssData', {})
			score    = data.get('baseScore')
			severity = data.get('baseSeverity') or data.get('accessVector')
			vector   = data.get('vectorString', '')
			break
	refs = [ref['url'] for ref in cve.get('references', [])[:4]]
	patch_keywords = {'patch', 'fix', 'advisory', 'update', 'release'}
	return {
		'cve_id':          cve.get('id', ''),
		'description':     desc,
		'score':           score,
		'severity':        severity,
		'vector':          vector,
		'published':       cve.get('published', '')[:10],
		'last_modified':   cve.get('lastModified', '')[:10],
		'references':      refs,
		'patch_available': any(k in r.lower() for r in refs for k in patch_keywords),
	}


def format_cves_for_context(cves: list[dict]) -> str:
	lines = []
	for c in cves:
		lines.append(
			f"[{c['cve_id']}] {c['severity']} (CVSS {c['score']})\n"
			f"{c['description'][:300]}\n"
			f"Patch available: {c['patch_available']}"
		)
	return '\n\n'.join(lines)

# OpenCorporates API — free basic tier, no key required for search
import requests

_BASE    = 'https://api.opencorporates.com/v0.4'
_TIMEOUT = 10


def search_company(name: str, jurisdiction: str = '', limit: int = 5) -> list[dict]:
	params: dict = {'q': name, 'per_page': min(limit, 30)}
	if jurisdiction:
		params['jurisdiction_code'] = jurisdiction.lower()
	try:
		r = requests.get(f'{_BASE}/companies/search', params=params, timeout=_TIMEOUT)
		r.raise_for_status()
		companies = r.json().get('results', {}).get('companies', [])
		return [
			{
				'name':               c['company'].get('name', ''),
				'jurisdiction':       c['company'].get('jurisdiction_code', ''),
				'status':             c['company'].get('current_status', ''),
				'company_number':     c['company'].get('company_number', ''),
				'incorporation_date': c['company'].get('incorporation_date', ''),
				'registered_address': c['company'].get('registered_address_in_full', ''),
				'company_type':       c['company'].get('company_type', ''),
				'opencorporates_url': c['company'].get('opencorporates_url', ''),
			}
			for c in companies
		]
	except Exception:
		return []


def format_companies_for_context(companies: list[dict]) -> str:
	lines = []
	for c in companies:
		lines.append(
			f"{c['name']} ({c['jurisdiction'].upper()}) — {c['status']}\n"
			f"Incorporated: {c['incorporation_date']} | Type: {c['company_type']}\n"
			f"{c['registered_address']}\n"
			f"{c['opencorporates_url']}"
		)
	return '\n\n'.join(lines)

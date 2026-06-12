# SEC EDGAR — completely free, no auth required
# User-Agent header is required by EDGAR fair-use policy.
import requests

_SEARCH  = 'https://efts.sec.gov/LATEST/search-index'
_FACTS   = 'https://data.sec.gov/api/xbrl/companyfacts'
_HEADERS = {'User-Agent': 'ThuonPlatform/0.1 nyimbi@gmail.com', 'Accept': 'application/json'}
_TIMEOUT = 15

_KEY_METRICS = (
	'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
	'NetIncomeLoss', 'Assets', 'StockholdersEquity',
	'OperatingIncomeLoss', 'EarningsPerShareBasic',
	'CashAndCashEquivalentsAtCarryingValue',
)


def search_filings(query: str, form_type: str = '10-K', limit: int = 5) -> list[dict]:
	try:
		r = requests.get(
			_SEARCH,
			params={'q': f'"{query}"', 'forms': form_type},
			headers=_HEADERS,
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		hits = r.json().get('hits', {}).get('hits', [])[:limit]
		return [
			{
				'entity':  h.get('_source', {}).get('entity_name', ''),
				'form':    h.get('_source', {}).get('form_type', ''),
				'filed':   h.get('_source', {}).get('file_date', ''),
				'cik':     h.get('_source', {}).get('entity_id', ''),
				'url':     f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={h.get('_source', {}).get('entity_id', '')}&type={form_type}",
			}
			for h in hits
		]
	except Exception:
		return []


def search_company_cik(company_name: str) -> str | None:
	"""Return the CIK string for a company name, or None."""
	rows = search_filings(company_name, limit=1)
	return rows[0]['cik'] if rows else None


def get_company_facts(cik: str) -> dict:
	"""
	Return structured financial facts for a company using EDGAR XBRL data.
	cik: numeric CIK as string (will be zero-padded to 10 digits).
	"""
	cik_padded = str(cik).zfill(10)
	try:
		r = requests.get(
			f'{_FACTS}/CIK{cik_padded}.json',
			headers=_HEADERS,
			timeout=_TIMEOUT,
		)
		r.raise_for_status()
		data    = r.json()
		us_gaap = data.get('facts', {}).get('us-gaap', {})
		metrics: dict = {}
		for metric in _KEY_METRICS:
			if metric not in us_gaap:
				continue
			usd_vals = us_gaap[metric].get('units', {}).get('USD', [])
			annual   = [v for v in usd_vals if v.get('form') in ('10-K', '20-F')]
			if annual:
				latest = sorted(annual, key=lambda x: x.get('end', ''))[-1]
				metrics[metric] = {
					'value': latest.get('val'),
					'period_end': latest.get('end'),
					'form':  latest.get('form'),
				}
		return {
			'entity':  data.get('entityName', ''),
			'cik':     cik,
			'metrics': metrics,
		}
	except Exception:
		return {}


def format_financials_for_context(facts: dict) -> str:
	if not facts or not facts.get('metrics'):
		return 'No EDGAR financial data available.'
	lines = [f"Company: {facts.get('entity', 'Unknown')} (CIK {facts.get('cik', '')})"]
	for metric, data in facts['metrics'].items():
		val = data.get('value', 'N/A')
		period = data.get('period_end', '')
		if isinstance(val, (int, float)):
			val_str = f'${val:,.0f}' if val > 1000 else str(val)
		else:
			val_str = str(val)
		lines.append(f"  {metric}: {val_str} (period ending {period})")
	return '\n'.join(lines)

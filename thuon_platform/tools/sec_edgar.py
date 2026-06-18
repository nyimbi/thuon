import urllib.parse
from typing import Any

try:
	import requests
except ImportError:
	requests = None

from core.settings_manager import get_settings


_HEADERS = {'User-Agent': 'Thuon research@thuon.ai'}


class SECEdgarTool:

	def search_filings(self, company: str, form_type: str = '10-K', max_results: int = 5) -> dict[str, Any]:
		try:
			if requests is None:
				return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}

			settings = get_settings()
			user_agent = settings.get_setting('tools.sec_edgar.user_agent', _HEADERS['User-Agent'])
			headers = {'User-Agent': user_agent}

			encoded = urllib.parse.quote(f'"{company}"')
			url = f'https://efts.sec.gov/LATEST/search-index?q={encoded}&forms={form_type}'
			resp = requests.get(url, headers=headers, timeout=15)
			resp.raise_for_status()
			data = resp.json()

			hits = data.get('hits', {}).get('hits', [])[:max_results]
			filings: list[dict[str, Any]] = []

			for hit in hits:
				src = hit.get('_source', {})
				# accession number is the doc ID with dashes removed
				accession_raw = hit.get('_id', '')
				accession_no_dashes = accession_raw.replace('-', '')

				# CIK comes from entity_id field or parsed from display_names
				cik = src.get('entity_id', '') or src.get('cik', '')

				# build filing index URL
				if cik and accession_no_dashes:
					filing_url = (
						f'https://www.sec.gov/Archives/edgar/data/{cik}/'
						f'{accession_no_dashes}/{accession_raw}-index.htm'
					)
				else:
					filing_url = f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={urllib.parse.quote(company)}&type={form_type}&dateb=&owner=include&count=40'

				display_names = src.get('display_names', [])
				company_name = display_names[0] if display_names else company

				filings.append({
					'company': company_name,
					'cik': str(cik),
					'form_type': src.get('form_type', form_type),
					'date': src.get('file_date', src.get('period_of_report', '')),
					'url': filing_url,
					'description': src.get('file_num', accession_raw),
				})

			return {
				'status': 'success',
				'company': company,
				'form_type': form_type,
				'filings': filings,
				'count': len(filings),
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

	def get_company_facts(self, cik: str) -> dict[str, Any]:
		try:
			if requests is None:
				return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}

			settings = get_settings()
			user_agent = settings.get_setting('tools.sec_edgar.user_agent', _HEADERS['User-Agent'])
			headers = {'User-Agent': user_agent}

			cik_padded = cik.lstrip('0').zfill(10)
			url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json'
			resp = requests.get(url, headers=headers, timeout=20)
			resp.raise_for_status()
			data = resp.json()

			top_keys = list(data.keys())
			entity_name = data.get('entityName', '')

			# extract a small summary of recent financials from us-gaap facts
			us_gaap = data.get('facts', {}).get('us-gaap', {})
			summary: dict[str, Any] = {}
			# pick a handful of high-value concepts if present
			concepts_of_interest = [
				'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
				'NetIncomeLoss', 'Assets', 'Liabilities', 'StockholdersEquity',
				'CashAndCashEquivalentsAtCarryingValue', 'EarningsPerShareBasic',
			]
			for concept in concepts_of_interest:
				if concept not in us_gaap:
					continue
				units = us_gaap[concept].get('units', {})
				# prefer USD values
				vals = units.get('USD', units.get('shares', []))
				# keep only annual (10-K) filings, take last 3
				annual = [v for v in vals if v.get('form') == '10-K']
				if annual:
					summary[concept] = annual[-3:]

			return {
				'status': 'success',
				'cik': cik,
				'entity_name': entity_name,
				'top_level_keys': top_keys,
				'recent_financials': summary,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

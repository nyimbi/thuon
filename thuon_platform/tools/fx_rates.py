import xml.etree.ElementTree as ET
from typing import Any

try:
	import requests
except ImportError:
	requests = None

from core.settings_manager import get_settings


_ECB_URL = 'https://www.ecb.europa.eu/stats/eurofsd/eurofxref-daily.xml'
_FALLBACK_URL = 'https://api.exchangerate-api.com/v4/latest/{base}'
_ECB_NS = 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'


class FXRatesTool:

	def get_rates(self, base: str = 'USD', currencies: list = [], include_metals: bool = False) -> dict[str, Any]:
		try:
			if requests is None:
				return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}

			settings = get_settings()
			timeout = settings.get_setting('tools.fx_rates.timeout', 15)

			# attempt ECB feed first
			try:
				resp = requests.get(_ECB_URL, timeout=timeout)
				resp.raise_for_status()
				root = ET.fromstring(resp.content)

				# ECB XML: Envelope > Cube > Cube (time) > Cube (currency rate)
				time_cube = root.find(f'.//{{{_ECB_NS}}}Cube[@time]')
				timestamp = time_cube.attrib.get('time', '') if time_cube is not None else ''

				# build EUR-based rates dict
				eur_rates: dict[str, float] = {'EUR': 1.0}
				for cube in root.findall(f'.//{{{_ECB_NS}}}Cube[@currency]'):
					ccy = cube.attrib['currency']
					rate = float(cube.attrib['rate'])
					eur_rates[ccy] = rate

				# cross-rate: if base != EUR, divide every rate by the base's EUR rate
				base_upper = base.upper()
				if base_upper not in eur_rates:
					return {
						'status': 'error',
						'error': f'Base currency {base_upper} not found in ECB feed',
					}

				base_rate = eur_rates[base_upper]
				rates: dict[str, float] = {
					ccy: round(r / base_rate, 6)
					for ccy, r in eur_rates.items()
					if ccy != base_upper
				}

				source = 'ECB'

			except Exception:
				# fallback to exchangerate-api (free, no key)
				fallback_url = _FALLBACK_URL.format(base=base.upper())
				resp = requests.get(fallback_url, timeout=timeout)
				resp.raise_for_status()
				data = resp.json()
				rates = data.get('rates', {})
				timestamp = data.get('date', '')
				source = 'exchangerate-api'

			# filter to requested currencies
			if currencies:
				upper_filter = {c.upper() for c in currencies}
				rates = {k: v for k, v in rates.items() if k in upper_filter}

			result: dict[str, Any] = {
				'status': 'success',
				'base': base.upper(),
				'rates': rates,
				'timestamp': timestamp,
				'source': source,
				'count': len(rates),
			}

			if include_metals:
				result['metals_note'] = 'ECB feed does not include precious metals; use a commodities API (e.g. metals-api.com) for XAU/XAG/XPT rates'

			return result

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

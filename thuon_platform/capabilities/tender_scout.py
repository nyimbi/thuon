# capabilities/tender_scout.py
"""
African procurement tender search across 15 countries.
Uses DuckDuckGo with portal-aware query planning and result deduplication.
"""

from __future__ import annotations
import hashlib
import re
from datetime import datetime


_PORTALS: dict[str, list[str]] = {
	'Kenya':          ['tenders.go.ke', 'ppra.go.ke'],
	'Nigeria':        ['nocopo.gov.ng', 'procurement.gov.ng'],
	'South Africa':   ['etenders.treasury.gov.za'],
	'Ghana':          ['ppa.gov.gh'],
	'Tanzania':       ['ppra.go.tz'],
	'Uganda':         ['ppda.go.ug'],
	'Ethiopia':       ['pppa.gov.et'],
	'Rwanda':         ['rppa.gov.rw'],
	'Zambia':         ['zppa.org.zm'],
	'Zimbabwe':       ['procurement.gov.zw'],
	'Egypt':          ['tenders.gov.eg'],
	'Morocco':        ['marchespublics.gov.ma'],
	'Senegal':        ['dgci.gouv.sn'],
	"Côte d'Ivoire":  ['marchespublics.ci'],
	'Cameroon':       ['armp.cm'],
}

_ALL_DOMAINS = [d for domains in _PORTALS.values() for d in domains]

_DEADLINE_PATTERNS = [
	r'deadline[:\s]+([A-Z][a-z]+ \d{1,2},?\s+\d{4})',
	r'closing date[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
	r'due[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
	r'by (\d{1,2}(?:st|nd|rd|th)? [A-Z][a-z]+ \d{4})',
]


class TenderScout:
	def __init__(self, search_engine, ai_engine=None):
		self.search_engine = search_engine
		self.ai_engine = ai_engine

	def search(
		self,
		sector: str,
		countries: list[str] | None = None,
		keywords: list[str] | None = None,
		max_results: int = 20,
	) -> dict:
		"""
		Search for tenders across African procurement portals.

		Args:
			sector:      Industry sector e.g. 'ICT', 'construction', 'healthcare'
			countries:   Limit to specific countries (None = top 5 by default)
			keywords:    Additional filter keywords
			max_results: Cap on returned results
		"""
		queries = self._build_queries(sector, countries, keywords)
		raw_results: list[dict] = []
		seen: set[str] = set()

		for query in queries:
			try:
				results = self.search_engine.search(query, num_results=10)
				for r in results:
					key = hashlib.md5(
						(r.get('href', '') + r.get('title', '')).encode()
					).hexdigest()
					if key not in seen:
						seen.add(key)
						raw_results.append(self._enrich(r))
			except Exception:
				continue

		ranked = sorted(raw_results, key=lambda r: r.get('is_portal_match', False), reverse=True)
		results_out = ranked[:max_results]

		return {
			'sector':              sector,
			'countries_searched':  countries or list(_PORTALS.keys()),
			'queries_run':         len(queries),
			'total_found':         len(raw_results),
			'results':             results_out,
			'portal_matches':      sum(1 for r in results_out if r.get('is_portal_match')),
			'status':              'ok',
			'searched_at':         datetime.utcnow().isoformat(),
		}

	def _build_queries(
		self,
		sector: str,
		countries: list[str] | None,
		keywords: list[str] | None,
	) -> list[str]:
		target_countries = countries or list(_PORTALS.keys())[:5]
		portal_domains: list[str] = []
		for c in target_countries:
			portal_domains.extend(_PORTALS.get(c, []))

		queries = [f'{sector} tender procurement Africa 2024 2025']

		if portal_domains:
			site_clause = ' OR site:'.join(portal_domains[:4])
			queries.append(f'{sector} government tender site:{site_clause}')

		if countries:
			for country in countries[:3]:
				queries.append(f'{sector} tender {country} government procurement')

		if keywords:
			kw = ' '.join(keywords[:3])
			queries.append(f'{sector} tender {kw} Africa')

		return queries

	def _enrich(self, result: dict) -> dict:
		url     = result.get('href', result.get('url', ''))
		title   = result.get('title', '')
		snippet = result.get('body', result.get('snippet', ''))
		return {
			'title':             title,
			'url':               url,
			'snippet':           snippet[:400],
			'country':           self._detect_country(url + ' ' + title),
			'is_portal_match':   any(d in url for d in _ALL_DOMAINS),
			'detected_deadline': self._extract_deadline(snippet + ' ' + title),
		}

	def _detect_country(self, text: str) -> str:
		text_lower = text.lower()
		for country, domains in _PORTALS.items():
			if country.lower() in text_lower or any(d in text_lower for d in domains):
				return country
		return 'Unknown'

	def _extract_deadline(self, text: str) -> str | None:
		for pattern in _DEADLINE_PATTERNS:
			m = re.search(pattern, text, re.IGNORECASE)
			if m:
				return m.group(1).strip()
		return None

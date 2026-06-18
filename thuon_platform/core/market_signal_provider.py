# core/market_signal_provider.py
"""
MarketSignalProvider — inject live market signals into capability context.

Signals include:
  - Federal Register notices for a given agency
  - Live news via the SearchEngine (SearXNG)
  - Industry price index headlines

Results are TTL-cached (default 4 hours) to avoid hammering external APIs.

Usage::

    from core.market_signal_provider import get_market_signal_provider
    provider = get_market_signal_provider()
    signals = provider.inject_into_context('rfp', issuer='USAF', topic='cloud services')
    # returns {'budget_notices': [...], 'news': [...], 'price_indices': [...], '_note': ''}
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger('thuon.market_signal_provider')

_FR_BASE   = 'https://www.federalregister.gov/api/v1'
_FR_TIMEOUT = 10

# Static alias map: common issuer name fragments → Federal Register agency slug
_AGENCY_ALIASES: dict[str, str] = {
	'dod': 'defense-department',
	'department of defense': 'defense-department',
	'army': 'army-department',
	'navy': 'navy-department',
	'air force': 'air-force-department',
	'usaf': 'air-force-department',
	'marines': 'marine-corps',
	'nasa': 'national-aeronautics-and-space-administration',
	'dhs': 'homeland-security-department',
	'homeland security': 'homeland-security-department',
	'hhs': 'health-and-human-services-department',
	'health and human services': 'health-and-human-services-department',
	'va': 'veterans-affairs-department',
	'veterans affairs': 'veterans-affairs-department',
	'dot': 'transportation-department',
	'transportation': 'transportation-department',
	'doe': 'energy-department',
	'energy': 'energy-department',
	'usda': 'agriculture-department',
	'agriculture': 'agriculture-department',
	'epa': 'environmental-protection-agency',
	'sba': 'small-business-administration',
	'gsa': 'general-services-administration',
	'cia': 'central-intelligence-agency',
	'nsa': 'national-security-agency',
	'fbi': 'federal-bureau-of-investigation',
	'state': 'state-department',
	'treasury': 'treasury-department',
	'commerce': 'commerce-department',
	'labor': 'labor-department',
	'education': 'education-department',
	'interior': 'interior-department',
	'justice': 'justice-department',
	'nist': 'national-institute-of-standards-and-technology',
	'disa': 'defense-information-systems-agency',
	'darpa': 'defense-advanced-research-projects-agency',
	'nih': 'national-institutes-of-health',
	'cdc': 'centers-for-disease-control-and-prevention',
	'cms': 'centers-for-medicare-medicaid-services',
	'nrc': 'nuclear-regulatory-commission',
	'usps': 'postal-service',
	'census': 'census-bureau',
	'bls': 'bureau-of-labor-statistics',
}


def _resolve_agency_slug(issuer: str) -> str | None:
	"""Map an issuer name to a Federal Register agency slug. Returns None when unknown."""
	lower = issuer.lower().strip()

	# Direct alias match
	for fragment, slug in _AGENCY_ALIASES.items():
		if fragment in lower:
			return slug

	# Try live FR agencies endpoint
	try:
		url = f'{_FR_BASE}/agencies.json'
		with urllib.request.urlopen(url, timeout=_FR_TIMEOUT) as resp:  # noqa: S310
			agencies = json.loads(resp.read())
		for agency in agencies:
			name = (agency.get('name') or '').lower()
			slug_candidate = agency.get('slug', '')
			if name and slug_candidate and (name in lower or lower in name):
				return slug_candidate
	except Exception:
		pass

	# Naive fallback: hyphenate first three words
	words = lower.replace(',', '').split()
	if words:
		return '-'.join(words[:3])
	return None


def _fetch_federal_register(agency_slug: str, days_back: int = 30) -> list[dict]:
	"""
	Fetch recent FR notices for an agency.  Uses urllib directly to avoid
	requests percent-encoding [ ] which the FR API rejects with 400.
	"""
	cutoff = time.strftime('%Y-%m-%d', time.gmtime(time.time() - days_back * 86400))
	params = (
		f'?fields[]=title&fields[]=abstract&fields[]=publication_date'
		f'&fields[]=document_type&fields[]=agencies'
		f'&conditions[agencies][]={agency_slug}'
		f'&conditions[publication_date][gte]={cutoff}'
		f'&per_page=10&order=newest'
	)
	url = f'{_FR_BASE}/articles{params}'
	try:
		with urllib.request.urlopen(url, timeout=_FR_TIMEOUT) as resp:  # noqa: S310
			data = json.loads(resp.read())
		results = data.get('results', [])
		return [
			{
				'title':   r.get('title', ''),
				'date':    r.get('publication_date', ''),
				'type':    r.get('document_type', ''),
				'summary': (r.get('abstract') or '')[:300],
			}
			for r in results
		]
	except urllib.error.HTTPError as exc:
		logger.debug('FR API HTTP %s for slug %s: %s', exc.code, agency_slug, exc)
	except Exception as exc:
		logger.debug('FR API failed for slug %s: %s', agency_slug, exc)
	return []


class MarketSignalProvider:
	"""
	Inject live market signals into capability prompts.

	All methods return dicts that are safe to embed in AI prompts.
	Network failures result in empty signal lists + a `_note` field — never exceptions.
	"""

	def __init__(self, search_engine: Any = None, ttl_hours: float = 4.0) -> None:
		self._search = search_engine
		self._ttl    = ttl_hours * 3600
		self._cache: dict[tuple, tuple[float, Any]] = {}
		self._lock   = threading.Lock()

	# ── Cache helpers ─────────────────────────────────────────────────────────

	def _cached(self, key: tuple, fetch_fn) -> Any:
		now = time.monotonic()
		with self._lock:
			entry = self._cache.get(key)
			if entry is not None:
				ts, val = entry
				if now - ts < self._ttl:
					return val
		result = fetch_fn()
		with self._lock:
			self._cache[key] = (now, result)
		return result

	def expire_cache(self) -> None:
		with self._lock:
			self._cache.clear()

	# ── Public API ────────────────────────────────────────────────────────────

	def inject_into_context(
		self,
		context_type: str = 'rfp',
		issuer: str = '',
		topic: str = '',
		naics: str = '',
	) -> dict[str, Any]:
		"""
		Return a dict of live market signals appropriate for context_type.

		context_type: 'rfp' | 'blog' | 'social' | 'general'
		"""
		signals: dict[str, Any] = {
			'budget_notices':  [],
			'news':            [],
			'price_indices':   [],
			'_note':           '',
		}

		notes: list[str] = []

		if context_type == 'rfp':
			# Federal Register notices for the issuer
			if issuer:
				slug = _resolve_agency_slug(issuer)
				if slug:
					notices = self._cached(
						('fr', slug),
						lambda s=slug: _fetch_federal_register(s),
					)
					signals['budget_notices'] = notices
					if not notices:
						notes.append(f'No recent FR notices for {issuer}.')

			# News context for RFP topic
			if topic or naics:
				query = f'{issuer} {topic} contract procurement {naics}'.strip()
				news = self._search_news(query, max_results=5)
				signals['news'] = news

		elif context_type == 'blog':
			if topic:
				news = self._search_news(f'{topic} industry trends this month', max_results=6)
				signals['news'] = news

		elif context_type == 'social':
			if topic:
				news = self._search_news(f'{topic} trending news today', max_results=4)
				signals['news'] = news

		else:  # general
			if topic:
				news = self._search_news(topic, max_results=5)
				signals['news'] = news

		# Append BLS price index note
		if naics and context_type == 'rfp':
			signals['price_indices'] = self._bls_headline(naics)

		signals['_note'] = ' | '.join(notes) if notes else ''
		return signals

	def _search_news(self, query: str, max_results: int = 5) -> list[dict]:
		if self._search is None:
			return []
		try:
			results = self._search.search(query, num_results=max_results)
			return [
				{'title': r.get('title', ''), 'summary': r.get('body', '')[:250], 'url': r.get('url', '')}
				for r in results
			]
		except Exception as exc:
			logger.debug('news search failed: %s', exc)
			return []

	def _bls_headline(self, naics: str) -> list[dict]:
		"""Return a static note about BLS PPI series for common NAICS prefixes."""
		prefix = naics[:2]
		_PPI_MAP: dict[str, str] = {
			'54': 'PPI Professional & Technical Services',
			'51': 'PPI Information sector',
			'33': 'PPI Manufacturing',
			'61': 'PPI Educational services',
			'62': 'PPI Health care',
			'72': 'PPI Accommodation & food services',
		}
		label = _PPI_MAP.get(prefix)
		if label:
			return [{'title': label, 'summary': f'BLS Producer Price Index for NAICS {naics[:2]}xx.', 'url': 'https://www.bls.gov/ppi/'}]
		return []

	def format_for_prompt(self, signals: dict[str, Any], max_chars: int = 1500) -> str:
		"""Render signals as a compact block suitable for injection into an AI prompt."""
		lines: list[str] = []

		notices = signals.get('budget_notices', [])
		if notices:
			lines.append('Federal Register notices (recent):')
			for n in notices[:3]:
				lines.append(f'  [{n.get("date","")}] {n.get("type","")} — {n.get("title","")}')
				if n.get('summary'):
					lines.append(f'    {n["summary"][:150]}')

		news = signals.get('news', [])
		if news:
			lines.append('Recent market news:')
			for item in news[:4]:
				lines.append(f'  • {item.get("title","")}')
				if item.get('summary'):
					lines.append(f'    {item["summary"][:120]}')

		price = signals.get('price_indices', [])
		if price:
			lines.append('Industry price context:')
			for p in price:
				lines.append(f'  {p.get("title","")} — {p.get("summary","")}')

		note = signals.get('_note', '')
		if note:
			lines.append(f'Note: {note}')

		text = '\n'.join(lines)
		return text[:max_chars] if len(text) > max_chars else text


# ── Singleton ─────────────────────────────────────────────────────────────────

_provider: MarketSignalProvider | None = None
_provider_lock = threading.Lock()


def get_market_signal_provider(search_engine: Any = None) -> MarketSignalProvider:
	global _provider
	if _provider is None:
		with _provider_lock:
			if _provider is None:
				_provider = MarketSignalProvider(search_engine=search_engine)
	return _provider

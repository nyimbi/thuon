# core/citation_verifier.py
# Universal weakness #1 — Citation grounding.
#
# After any capability produces key_findings / recommendations, this module
# scrapes the cited source URLs and verifies that the claimed facts actually
# appear in the source text. Unverified claims are flagged, not silently dropped.

import json
import re

from core.ai_engine import AIModel
from core.search_engine import scrape_webpage


def verify_citations(
	claims: list[str],
	source_urls: list[str],
	ai_engine: AIModel,
	max_sources: int = 5,
) -> list[dict]:
	"""
	For each claim check whether supporting evidence exists in any source URL.

	Returns a list of dicts, one per claim:
	  {claim, verified (bool), evidence (quote), source_url, confidence}
	"""
	if not claims or not source_urls:
		return [
			{'claim': c, 'verified': False, 'evidence': '', 'source_url': '', 'confidence': 'none'}
			for c in claims
		]

	# Scrape sources (bounded to avoid excessive network calls)
	scraped: dict[str, str] = {}
	for url in source_urls[:max_sources]:
		if not url or not url.startswith('http'):
			continue
		try:
			text = scrape_webpage(url)
			if text and len(text) > 100:
				scraped[url] = text[:3000]
		except Exception:
			pass

	if not scraped:
		return [
			{'claim': c, 'verified': False, 'evidence': '', 'source_url': '', 'confidence': 'none'}
			for c in claims
		]

	sources_block = '\n\n'.join(
		f'SOURCE [{i+1}] ({url}):\n{text}'
		for i, (url, text) in enumerate(scraped.items())
	)
	claims_block = '\n'.join(f'{i+1}. {c}' for i, c in enumerate(claims))

	prompt = (
		'You are a rigorous fact-checker. For each numbered claim below, determine whether '
		'supporting evidence appears verbatim or equivalently in the provided source texts.\n\n'
		f'CLAIMS:\n{claims_block}\n\n'
		f'SOURCE TEXTS:\n{sources_block[:5000]}\n\n'
		'Return a JSON array — one object per claim — with keys:\n'
		'  claim_number (int, 1-based),\n'
		'  verified (bool),\n'
		'  confidence ("high"|"medium"|"low"|"none"),\n'
		'  evidence (verbatim quote from source, or "" if unverified),\n'
		'  source_url (URL of supporting source, or "")'
	)

	response = ai_engine.generate_text(prompt)
	try:
		match = re.search(r'\[.*\]', response, re.DOTALL)
		if match:
			items = json.loads(match.group())
			out = []
			idx_map = {item.get('claim_number', 0): item for item in items}
			for i, claim in enumerate(claims):
				item = idx_map.get(i + 1, {})
				out.append({
					'claim':      claim,
					'verified':   bool(item.get('verified', False)),
					'confidence': item.get('confidence', 'none'),
					'evidence':   item.get('evidence', ''),
					'source_url': item.get('source_url', ''),
				})
			return out
	except Exception:
		pass

	# Fallback — all unverified
	return [
		{'claim': c, 'verified': False, 'evidence': '', 'source_url': '', 'confidence': 'none'}
		for c in claims
	]


def add_citation_verification(result: dict, ai_engine: AIModel) -> dict:
	"""
	Convenience wrapper: extract claims and source URLs from a capability result dict,
	run verification, and attach a 'citation_verification' summary back to the result.

	Operates in-place and returns the modified dict.
	"""
	# Collect verifiable claims from common output keys
	claims: list[str] = []
	for key in ('key_findings', 'recommendations', 'key_points', 'vulnerabilities'):
		val = result.get(key)
		if isinstance(val, list):
			for item in val[:6]:
				if isinstance(item, str):
					claims.append(item)
				elif isinstance(item, dict):
					text = (
						item.get('description')
						or item.get('finding')
						or item.get('recommendation')
						or item.get('name')
						or ''
					)
					if text:
						claims.append(str(text)[:200])

	# Collect source URLs from common output keys
	source_urls: list[str] = []
	for key in ('sources_used', 'sources', 'key_citations', 'references', 'source_urls'):
		val = result.get(key)
		if isinstance(val, list):
			for item in val:
				if isinstance(item, str) and item.startswith('http'):
					source_urls.append(item)
				elif isinstance(item, dict):
					url = item.get('url') or item.get('href') or ''
					if url.startswith('http'):
						source_urls.append(url)

	if not claims or not source_urls:
		result['citation_verification'] = {
			'status':  'skipped',
			'reason':  'no verifiable claims or source URLs found in output',
		}
		return result

	verifications = verify_citations(claims[:6], source_urls[:5], ai_engine)
	verified_count = sum(1 for v in verifications if v['verified'])
	high_confidence = sum(1 for v in verifications if v['confidence'] == 'high')

	result['citation_verification'] = {
		'verified':          verified_count,
		'unverified':        len(verifications) - verified_count,
		'total_checked':     len(verifications),
		'verification_rate': round(verified_count / len(verifications), 2) if verifications else 0,
		'high_confidence':   high_confidence,
		'details':           verifications,
	}
	return result

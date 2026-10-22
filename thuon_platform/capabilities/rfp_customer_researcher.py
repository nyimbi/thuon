# capabilities/rfp_customer_researcher.py
"""
Atomic capability: research the RFP issuer's strategic priorities and pain points.
"""

from __future__ import annotations

from typing import Any

from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json


class RFPCustomerResearcher:
	def __init__(
		self,
		ai_engine: AIModel,
		search_engine: SearchEngine,
		market_signal_provider: Any = None,
	):
		self.ai_engine              = ai_engine
		self.search_engine          = search_engine
		self.market_signal_provider = market_signal_provider

	def research(
		self,
		issuer: str,
		scope_summary: str = '',
		naics: str = '',
	) -> dict:
		"""
		Research the issuing organization to inform win strategy.

		Returns:
			{strategic_priorities, pain_points, recent_news,
			 leadership_focus, budget_environment, implied_intent,
			 ghost_worthy_intel, market_signals}
		"""
		search_results = self.search_engine.search(
			f'{issuer} strategic plan priorities initiatives 2024 2025',
			num_results=5,
		)
		news_results = self.search_engine.search(
			f'{issuer} recent news announcements procurement',
			num_results=3,
		)
		web_context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:300]}"
			for r in (search_results + news_results)
		)

		# Inject live market signals when available
		market_block = ''
		raw_signals: dict = {}
		if self.market_signal_provider is not None:
			try:
				raw_signals = self.market_signal_provider.inject_into_context(
					'rfp', issuer=issuer, topic=scope_summary, naics=naics,
				)
				market_block = self.market_signal_provider.format_for_prompt(raw_signals)
			except Exception:
				pass

		market_section = (
			f'\nLive market signals:\n{market_block}\n'
			if market_block
			else ''
		)

		# Known contacts at the issuer, from the CRM. This is the one source of
		# first-hand relationship context the platform already holds, so it
		# belongs in the prompt ahead of anything scraped from the web.
		contacts_block = ''
		known_contacts: list[dict] = []
		try:
			from core.crm_store import get_crm_store
			known_contacts = get_crm_store().search_contacts(organization=issuer)
			if known_contacts:
				lines = []
				for c in known_contacts[:8]:
					desc = ', '.join(filter(None, [c.get('name', ''), c.get('role', '')]))
					notes = (c.get('notes') or '').strip()
					lines.append(f'- {desc}' + (f' — {notes[:200]}' if notes else ''))
				contacts_block = '\nKnown contacts at this organization:\n' + '\n'.join(lines) + '\n'
		except Exception:
			pass

		prompt = (
			'You are a business development strategist. Research this buyer for an RFP response.\n\n'
			f'Issuing Organization: {issuer}\n'
			f'RFP Scope: {scope_summary}\n'
			f'{f"NAICS: {naics}" if naics else ""}\n'
			f'\nWeb research context:\n{web_context}\n'
			f'{market_section}'
			f'{contacts_block}'
			'\nReturn ONLY a valid JSON object with:\n'
			'- strategic_priorities (list of str): top 3-5 documented organizational priorities\n'
			'- pain_points (list of str): inferred problems they are trying to solve\n'
			'- recent_news (list of str): relevant recent announcements or initiatives\n'
			'- leadership_focus (str): current leadership themes and messaging\n'
			'- budget_environment (str): budget climate — growing/flat/constrained\n'
			'- implied_intent (str): what they really want beyond what the RFP states\n'
			'- ghost_worthy_intel (str): anything useful for ghosting incumbent or competitors'
		)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response) or {
			'strategic_priorities': [],
			'pain_points':          [],
			'recent_news':          [],
			'leadership_focus':     response[:300],
			'budget_environment':   'Unknown',
			'implied_intent':       '',
			'ghost_worthy_intel':   '',
		}

		if raw_signals:
			result['market_signals'] = raw_signals
		if known_contacts:
			result['known_contacts'] = [
				{'name': c.get('name', ''), 'role': c.get('role', ''), 'email': c.get('email', '')}
				for c in known_contacts[:8]
			]

		return result

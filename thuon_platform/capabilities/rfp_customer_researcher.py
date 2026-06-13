# capabilities/rfp_customer_researcher.py
"""
Atomic capability: research the RFP issuer's strategic priorities and pain points.
"""

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json, extract_json_array


class RFPCustomerResearcher:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine     = ai_engine
		self.search_engine = search_engine

	def research(
		self,
		issuer: str,
		scope_summary: str = '',
	) -> dict:
		"""
		Research the issuing organization to inform win strategy.

		Returns:
			{strategic_priorities, pain_points, recent_news,
			 leadership_focus, budget_environment, implied_intent}
		"""
		search_results = self.search_engine.search(
			f'{issuer} strategic plan priorities initiatives 2024 2025',
			num_results=5,
		)
		news_results = self.search_engine.search(
			f'{issuer} recent news announcements procurement',
			num_results=3,
		)
		context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:300]}"
			for r in (search_results + news_results)
		)

		prompt = (
			f'You are a business development strategist. Research this buyer for an RFP response.\n\n'
			f'Issuing Organization: {issuer}\n'
			f'RFP Scope: {scope_summary}\n\n'
			f'Web research context:\n{context}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- strategic_priorities (list of str): top 3-5 documented organizational priorities\n'
			'- pain_points (list of str): inferred problems they are trying to solve\n'
			'- recent_news (list of str): relevant recent announcements or initiatives\n'
			'- leadership_focus (str): current leadership themes and messaging\n'
			'- budget_environment (str): budget climate — growing/flat/constrained\n'
			'- implied_intent (str): what they really want beyond what the RFP states\n'
			'- ghost_worthy_intel (str): anything useful for ghosting incumbent or competitors'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'strategic_priorities': [],
			'pain_points':          [],
			'recent_news':          [],
			'leadership_focus':     response[:300],
			'budget_environment':   'Unknown',
			'implied_intent':       '',
			'ghost_worthy_intel':   '',
		}

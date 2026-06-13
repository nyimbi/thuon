# capabilities/rfp_competitor_analyst.py
"""
Atomic capability: competitive landscape analysis for an RFP.
"""

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json, extract_json_array


class RFPCompetitorAnalyst:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine     = ai_engine
		self.search_engine = search_engine

	def analyze(
		self,
		rfp_title: str,
		scope_summary: str = '',
		issuer: str = '',
	) -> dict:
		"""
		Research likely competitors and build a competitive landscape brief.

		Returns:
			{known_incumbents, likely_bidders, competitor_strengths,
			 competitor_weaknesses, differentiation_angles, ghosting_opportunities}
		"""
		results = self.search_engine.search(
			f'{issuer} {rfp_title} contract award incumbent vendor',
			num_results=5,
		)
		contract_results = self.search_engine.search(
			f'{issuer} {scope_summary[:80]} contractor awarded',
			num_results=4,
		)
		context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:250]}"
			for r in (results + contract_results)
		)

		prompt = (
			'You are a competitive intelligence analyst preparing for an RFP response.\n\n'
			f'RFP: {rfp_title}\n'
			f'Issuer: {issuer}\n'
			f'Scope: {scope_summary}\n\n'
			f'Research context:\n{context}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- known_incumbents (list of str): companies currently holding related contracts\n'
			'- likely_bidders (list of str): companies likely to bid on this\n'
			'- competitor_strengths (object): key → list of strengths for top 2-3 competitors\n'
			'- competitor_weaknesses (object): key → list of weaknesses for same competitors\n'
			'- differentiation_angles (list of str): how our offering stands apart from each\n'
			'- ghosting_opportunities (list of str): competitor weaknesses we can address '
			'implicitly in our proposal without naming competitors'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'known_incumbents':       [],
			'likely_bidders':         [],
			'competitor_strengths':   {},
			'competitor_weaknesses':  {},
			'differentiation_angles': [],
			'ghosting_opportunities': [],
		}

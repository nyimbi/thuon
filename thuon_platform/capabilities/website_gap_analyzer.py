# capabilities/website_gap_analyzer.py
"""
Atomic capability: identify content gaps and improvement priorities for a website page.
"""

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.llm_utils import extract_json, extract_json_array


class WebsiteGapAnalyzer:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine     = ai_engine
		self.search_engine = search_engine

	def analyze(
		self,
		current_content: str,
		company_context: str = '',
		target_audience: str = '',
		page_path: str = '/',
		competitor_urls: list | str = '',
	) -> dict:
		"""
		Identify what's missing, outdated, or under-optimized on a page.

		Returns:
			{missing_topics, outdated_claims, seo_gaps, competitor_advantages,
			 improvement_priority, recommended_structure}
		"""
		# Search for what competitors are covering on similar pages
		search_q = f'best {page_path.strip("/") or "homepage"} content {target_audience}'
		results  = self.search_engine.search(search_q, num_results=4)
		context  = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:200]}"
			for r in results
		)

		prompt = (
			f'You are a content strategist analyzing a website page for improvement.\n\n'
			f'Page: {page_path}\n'
			f'Target audience: {target_audience or "business decision makers"}\n\n'
			f'CURRENT PAGE CONTENT:\n{current_content[:3000]}\n\n'
			f'COMPANY CAPABILITIES:\n{company_context[:1500]}\n\n'
			f'COMPETITOR / INDUSTRY CONTEXT:\n{context}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- missing_topics (list of str): important topics absent from current page\n'
			'- outdated_claims (list of str): statements that may be stale or need updating\n'
			'- seo_gaps (list of str): keywords and topics to target for this page\n'
			'- competitor_advantages (list of str): things competitors cover that we don\'t\n'
			'- improvement_priority (list of str): top 5 changes, ordered by impact\n'
			'- recommended_structure (list of str): suggested new section order / structure\n'
			'- value_propositions_to_add (list of str): company strengths not yet highlighted'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'missing_topics':          [],
			'outdated_claims':         [],
			'seo_gaps':                [],
			'competitor_advantages':   [],
			'improvement_priority':    [response[:300]],
			'recommended_structure':   [],
			'value_propositions_to_add': [],
		}

# capabilities/intellectual_property_strategist.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.rag_engine import RAGEngine


class IntellectualPropertyStrategist:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine, rag_engine: RAGEngine = None):
		self.ai_engine = ai_engine
		self.search_engine = search_engine
		self.rag_engine = rag_engine

	def conduct_patent_landscape_analysis(
		self,
		keywords: list,
		jurisdictions: list = ['US', 'EP', 'CN', 'JP'],
	) -> dict:
		# USPTO PatentsView — real structured patent data
		real_patents = []
		patent_context = ''
		try:
			from core.data_sources.patents import search_patents, format_patents_for_context
			query_str = ' '.join(keywords[:5])
			real_patents = search_patents(query_str, limit=10)
			if real_patents:
				patent_context = (
					f"\nUSPTO PatentsView ({len(real_patents)} patents found):\n"
					f"{format_patents_for_context(real_patents[:6])}"
				)
		except Exception:
			pass

		web_query = f"patents {' '.join(keywords)} landscape analysis {' '.join(jurisdictions[:2])}"
		web_results = self.search_engine.search(web_query, num_results=5)
		web_context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:300]}" for r in web_results
		)

		prompt = (
			f"You are an IP strategy expert. Conduct a patent landscape analysis for the following technology area.\n\n"
			f"Keywords: {keywords}\nJurisdictions: {jurisdictions}\n\n"
			f"Research context:\n{web_context}{patent_context}\n\n"
			f"Return JSON with keys: technology_area, landscape_summary, key_patent_holders (list), "
			f"patent_trends (list), white_spaces (list of unprotected areas), "
			f"jurisdiction_analysis (object per jurisdiction with: activity_level, key_players, notable_patents), "
			f"competitive_threats (list), ip_opportunities (list), strategic_recommendations (list), "
			f"freedom_to_operate_assessment."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				if real_patents:
					result['patents_retrieved'] = len(real_patents)
					result['sample_patents'] = [
						{'id': p.get('patent_id'), 'title': p.get('patent_title'), 'date': p.get('patent_date')}
						for p in real_patents[:5]
					]
				return result
		except Exception:
			pass
		result = {'result': response, 'keywords': keywords, 'jurisdictions': jurisdictions, 'status': 'success'}
		if real_patents:
			result['patents_retrieved'] = len(real_patents)
		return result

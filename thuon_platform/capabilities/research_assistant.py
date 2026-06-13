# capabilities/research_assistant.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.rag_engine import RAGEngine
from core.data_handler import DatabaseHandler


def _llm_json(ai_engine, prompt: str) -> dict:
	response = ai_engine.generate_text(prompt)
	try:
		match = re.search(r'\{.*\}', response, re.DOTALL)
		if match:
			return json.loads(match.group())
	except Exception:
		pass
	return {'result': response, 'status': 'success'}


class ResearchAssistant:
	def __init__(
		self,
		ai_engine: AIModel,
		search_engine: SearchEngine,
		rag_engine: RAGEngine = None,
		data_handler: DatabaseHandler = None,
	):
		self.ai_engine = ai_engine
		self.search_engine = search_engine
		self.rag_engine = rag_engine
		self.data_handler = data_handler

	def perform_research(
		self,
		research_query: str,
		sources: list = ['web', 'knowledge_graph'],
		depth: str = 'medium',
	) -> dict:
		"""
		depth='quick'        — LLM prior knowledge only, no search (~2s)
		depth='shallow'      — single search pass + LLM synthesis (~10s)
		depth='medium'       — agent loop, up to 10 tool calls (~1 min)
		depth='deep'         — agent loop, up to 20 tool calls, reads full articles (~3 min)
		depth='comprehensive'— agent loop, 35 iterations, multi-angle search (~5 min)
		depth='academic'     — multi-phase orchestration with source evaluation (~10 min)
		depth='phd'          — full systematic review, thesis-quality output (~20 min)
		depth='consulting'   — McKinsey/BCG-grade: SCQA + MECE issue tree + self-consistency
		                       + competing hypotheses + pyramid synthesis + G-Eval gate (~15 min)
		"""
		# consulting depth routes to ConsultingResearchEngine
		if depth == 'consulting':
			return self._consulting_research(research_query)
		from capabilities.deep_researcher import RESEARCH_LEVELS
		if depth not in RESEARCH_LEVELS:
			depth = 'medium'
		if depth == 'shallow':
			return self._shallow_research(research_query)
		# medium/deep: direct agent loop (stable API, tested separately)
		if depth in ('medium', 'deep'):
			return self._direct_agentic(research_query, depth=depth)
		# quick/comprehensive/academic/phd: routed through DeepResearcher
		return self._routed_research(research_query, depth=depth)

	def _shallow_research(self, query: str) -> dict:
		web_results = self.search_engine.search(query, num_results=5)
		snippets = '\n'.join(
			f"- {r.get('title', '')}: {r.get('body', '')[:300]}"
			for r in web_results[:5]
		)

		# Academic context from arXiv — supplements web search with peer-reviewed papers
		arxiv_context = ''
		arxiv_count   = 0
		try:
			from core.data_sources.arxiv_client import search as arxiv_search, format_papers
			papers = arxiv_search(query, max_results=5)
			if papers:
				arxiv_context = f"\n\narXiv academic papers ({len(papers)} found):\n{format_papers(papers[:4])}"
				arxiv_count   = len(papers)
		except Exception:
			pass

		rag_context = ''
		if self.rag_engine:
			try:
				rag_context = self.rag_engine.generate_response_with_rag(query, 'research_docs') or ''
			except Exception:
				pass

		prompt = (
			f"You are an expert research analyst. Conduct comprehensive research on the following query.\n\n"
			f"Query: {query}\n\n"
			f"Web search results:\n{snippets}"
			f"{arxiv_context}\n\n"
			f"{'RAG context: ' + rag_context if rag_context else ''}\n\n"
			f"Return JSON with keys: summary, key_findings (list), data_points (list), "
			f"sources_used (list), confidence_level, recommendations (list)."
		)
		result = _llm_json(self.ai_engine, prompt)
		result.setdefault('query', query)
		result.setdefault('depth', 'shallow')
		result.setdefault('web_results_count', len(web_results))
		if arxiv_count:
			result['arxiv_papers_found'] = arxiv_count
		return result

	def _direct_agentic(self, query: str, depth: str = 'medium') -> dict:
		from core.agent_loop import research_agent
		max_iter = {'medium': 10, 'deep': 20}.get(depth, 10)
		agent = research_agent(max_iterations=max_iter)
		result = agent.run(query)
		result['query'] = query
		result['depth'] = depth
		return result

	def _routed_research(self, query: str, depth: str = 'medium') -> dict:
		from capabilities.deep_researcher import DeepResearcher
		dr = DeepResearcher(ai_engine=self.ai_engine, search_engine=self.search_engine)
		result = dr.research(query, level=depth)
		result.setdefault('query', query)
		result.setdefault('depth', depth)
		return result

	def _consulting_research(self, query: str) -> dict:
		from capabilities.consulting_research_engine import ConsultingResearchEngine
		engine = ConsultingResearchEngine(ai_engine=self.ai_engine, search_engine=self.search_engine)
		result = engine.research(query, output_format='both')
		result['depth'] = 'consulting'
		return result

	def summarize_research_findings(self, research_data: dict, length: str = 'medium') -> str:
		content = json.dumps(research_data, indent=2)
		return self.ai_engine.summarize_text(content, length)

	def curate_data_from_research(self, research_data: dict, data_fields: list) -> list:
		prompt = (
			f"From the following research data, extract these specific fields: {data_fields}.\n\n"
			f"Research data: {json.dumps(research_data)}\n\n"
			f"Return a JSON array of objects, one per field found, with keys: field, value, confidence."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\[.*\]', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return [{'field': f, 'value': research_data.get(f, ''), 'confidence': 'low'} for f in data_fields]

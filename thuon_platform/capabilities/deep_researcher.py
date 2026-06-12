# capabilities/deep_researcher.py
# Multi-level deep research capability.
#
# Level map:
#   quick         — LLM prior knowledge, no tools (~2s)
#   shallow       — single search batch + synthesis (~10s)
#   medium        — agent loop, 10 iterations (~1 min)
#   deep          — agent loop, 20 iterations, reads full articles (~3 min)
#   comprehensive — agent loop, 35 iterations, multi-angle search (~5 min)
#   academic      — orchestrated multi-phase: decompose → per-subq investigation
#                   → evidence synthesis → quality critique → structured report (~10 min)
#   phd           — full systematic review: question formulation → scoped lit search
#                   → source evaluation → thematic analysis → gap identification
#                   → original synthesis → thesis-quality structured output (~20 min)

import json
import re
import time

from core.ai_engine import AIModel
from core.search_engine import SearchEngine, scrape_webpage

RESEARCH_LEVELS = {
	'quick':         {'max_iter': 0,    'label': 'Quick (LLM knowledge only, ~2s)'},
	'shallow':       {'max_iter': 1,    'label': 'Shallow (single search + synthesis, ~10s)'},
	'medium':        {'max_iter': 10,   'label': 'Medium (agentic search loop, ~1 min)'},
	'deep':          {'max_iter': 20,   'label': 'Deep (reads full articles, ~3 min)'},
	'comprehensive': {'max_iter': 35,   'label': 'Comprehensive (multi-angle, ~5 min)'},
	'academic':      {'max_iter': None, 'label': 'Academic (multi-phase orchestration, ~10 min)'},
	'phd':           {'max_iter': None, 'label': 'PhD (systematic review + thesis structure, ~20 min)'},
}


class DeepResearcher:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	# ── Public API ────────────────────────────────────────────────────────

	def research(self, query: str, level: str = 'medium') -> dict:
		"""Run research at the specified depth level."""
		if level not in RESEARCH_LEVELS:
			return {'error': f'Unknown level "{level}". Choose from: {list(RESEARCH_LEVELS)}'}

		start = time.time()
		dispatch = {
			'quick':         self._quick,
			'shallow':       self._shallow,
			'medium':        lambda q: self._agentic(q, max_iter=10),
			'deep':          lambda q: self._agentic(q, max_iter=20, read_full_articles=True),
			'comprehensive': lambda q: self._agentic(q, max_iter=35, read_full_articles=True, multi_angle=True),
			'academic':      self._academic,
			'phd':           self._phd,
		}
		result = dispatch[level](query)
		result['query'] = query
		result['level'] = level
		result['elapsed_seconds'] = round(time.time() - start, 1)
		return result

	# ── Level implementations ─────────────────────────────────────────────

	def _quick(self, query: str) -> dict:
		"""LLM prior knowledge only — no external tools."""
		prompt = (
			f"You are an expert researcher. Answer the following question using your knowledge.\n\n"
			f"Question: {query}\n\n"
			f"Provide a concise, accurate answer. Return JSON with keys: "
			f"summary, key_points (list), confidence_level (high/medium/low), "
			f"caveats (list of limitations of this answer), "
			f"suggested_followup_questions (list)."
		)
		return self._llm_json(prompt, fallback_key='summary')

	def _shallow(self, query: str) -> dict:
		"""Single search batch + LLM synthesis."""
		results = self.search_engine.search(query, num_results=8)
		context = self._format_search_results(results)
		prompt = (
			f"You are a research analyst. Synthesize the following search results into a concise report.\n\n"
			f"Query: {query}\n\nSearch results:\n{context}\n\n"
			f"Return JSON with keys: summary, key_findings (list), "
			f"sources (list of {{title, url, relevance}}), confidence_level, "
			f"knowledge_gaps (list), recommendations (list)."
		)
		result = self._llm_json(prompt, fallback_key='summary')
		result['sources_searched'] = len(results)
		return result

	def _agentic(self, query: str, max_iter: int = 10, read_full_articles: bool = False, multi_angle: bool = False) -> dict:
		"""Agent loop — LLM decides which tools to call, iterates until done."""
		from core.agent_loop import research_agent
		extra = ''
		if read_full_articles:
			extra += ' Use scrape_url to read the full text of the most relevant articles, not just snippets.'
		if multi_angle:
			extra += (
				' Search from multiple angles: (1) direct query, (2) related concepts, '
				'(3) opposing viewpoints, (4) recent developments, (5) practical applications.'
			)
		agent = research_agent(max_iterations=max_iter)
		return agent.run(query + extra)

	def _academic(self, query: str) -> dict:
		"""
		Multi-phase academic research orchestration.
		Phase 1 — Decompose: break query into 4-6 focused sub-questions.
		Phase 2 — Investigate: run a focused agent loop per sub-question.
		Phase 3 — Source deep-read: scrape full text of top 2 sources per sub-question.
		Phase 4 — Synthesize: per-sub-question synthesis from findings + full texts.
		Phase 5 — Integrate: combine all syntheses into a coherent analysis.
		Phase 6 — Critique: identify weaknesses, contradictions, gaps.
		Phase 7 — Report: produce structured academic-style report.
		"""
		report = {'phases': {}}

		# Phase 1: Decompose
		sub_questions = self._decompose(query, n=5)
		report['phases']['decomposition'] = sub_questions

		# Phase 2 + 3: Investigate each sub-question
		investigations = {}
		for sq in sub_questions:
			inv = self._investigate_sub_question(sq, read_full=True)
			investigations[sq] = inv

		report['phases']['investigations'] = {
			sq: {'tool_calls': inv.get('tool_calls', []), 'answer_preview': inv.get('answer', '')[:400]}
			for sq, inv in investigations.items()
		}

		# Phase 4: Synthesize per sub-question
		syntheses = {}
		for sq, inv in investigations.items():
			syntheses[sq] = self._synthesize_sub_question(query, sq, inv.get('answer', ''))

		report['phases']['syntheses'] = syntheses

		# Phase 5: Integrate
		integration = self._integrate(query, sub_questions, syntheses)
		report['phases']['integration'] = integration

		# Phase 6: Critique
		critique = self._critique(query, integration)
		report['phases']['critique'] = critique

		# Phase 7: Final report
		final = self._write_academic_report(query, integration, critique, syntheses)
		report.update(final)
		return report

	def _phd(self, query: str) -> dict:
		"""
		Full systematic review at PhD thesis chapter quality.
		Phase 0 — Formulate: refine into a precise research question with scope.
		Phase 1 — Scope: define inclusion/exclusion criteria, search strategy.
		Phase 2 — Multi-angle literature search: 5 orthogonal search vectors.
		Phase 3 — Source evaluation: assess quality, relevance, recency per source.
		Phase 4 — Full-text reading: scrape all high-value sources.
		Phase 5 — Thematic analysis: identify cross-cutting themes.
		Phase 6 — Contradiction mapping: where do sources disagree?
		Phase 7 — Gap analysis: what is NOT known or NOT studied?
		Phase 8 — Original synthesis: novel analysis beyond summarizing.
		Phase 9 — Thesis structure: write as a full academic chapter.
		Phase 10 — Self-critique: identify limitations and future work.
		"""
		report = {'phases': {}}

		# Phase 0: Formulate research question
		rq = self._formulate_research_question(query)
		report['phases']['research_question'] = rq
		refined_query = rq.get('research_question', query)

		# Phase 1: Scope + search strategy
		scope = self._define_scope(refined_query)
		report['phases']['scope'] = scope

		# Phase 2: Multi-angle literature search (5 search vectors)
		search_vectors = self._build_search_vectors(refined_query, scope)
		all_sources = []
		for vector in search_vectors:
			results = self.search_engine.search(vector, num_results=6)
			for r in results:
				r['search_vector'] = vector
			all_sources.extend(results)

		# Deduplicate by URL
		seen_urls = set()
		unique_sources = []
		for s in all_sources:
			url = s.get('href', s.get('url', ''))
			if url and url not in seen_urls:
				seen_urls.add(url)
				unique_sources.append(s)

		# Phase 2b: Semantic Scholar citation chaining
		# Finds peer-reviewed papers, then chains through their citations and references
		# to surface high-quality academic sources the web search may have missed.
		ss_papers_found = 0
		ss_citations_found = 0
		try:
			from core.data_sources.semantic_scholar import (
				search_papers, get_citations, get_references, format_papers_for_context
			)
			ss_results = search_papers(refined_query, limit=5)
			for paper in ss_results[:3]:
				paper_id = paper.get('paperId', '')
				paper_url = paper.get('url', '')
				if paper_url and paper_url not in seen_urls:
					seen_urls.add(paper_url)
					unique_sources.append({
						'title':          paper.get('title', ''),
						'url':            paper_url,
						'href':           paper_url,
						'body':           (paper.get('abstract') or '')[:400],
						'source':         'semantic_scholar',
						'year':           paper.get('year'),
						'citation_count': paper.get('citationCount', 0),
					})
					ss_papers_found += 1
				# Fetch forward citations (papers that cite this work)
				if paper_id:
					for cited in get_citations(paper_id, limit=8):
						curl = cited.get('url', '')
						if curl and curl not in seen_urls:
							seen_urls.add(curl)
							unique_sources.append({
								'title':  cited.get('title', ''),
								'url':    curl,
								'href':   curl,
								'body':   '',
								'source': 'semantic_scholar_citation',
								'year':   cited.get('year'),
							})
							ss_citations_found += 1
		except Exception:
			pass

		report['phases']['sources_found']       = len(unique_sources)
		report['phases']['search_vectors']      = search_vectors
		report['phases']['ss_papers_found']     = ss_papers_found
		report['phases']['ss_citations_chained'] = ss_citations_found

		# Phase 3: Source evaluation
		evaluated = self._evaluate_sources(refined_query, unique_sources[:20])
		high_value = [s for s in evaluated if s.get('include', True)]
		report['phases']['source_evaluation'] = {
			'total': len(unique_sources),
			'included': len(high_value),
			'excluded': len(unique_sources) - len(high_value),
		}

		# Phase 4: Full-text reading of top sources
		full_texts = {}
		for src in high_value[:8]:
			url = src.get('href', src.get('url', ''))
			if url:
				text = scrape_webpage(url)
				if text and len(text) > 200:
					full_texts[url] = text
		report['phases']['full_texts_read'] = len(full_texts)

		# Phase 5: Thematic analysis
		themes = self._thematic_analysis(refined_query, high_value, full_texts)
		report['phases']['themes'] = themes

		# Phase 6: Contradiction mapping
		contradictions = self._map_contradictions(refined_query, high_value, full_texts)
		report['phases']['contradictions'] = contradictions

		# Phase 7: Gap analysis
		gaps = self._gap_analysis(refined_query, themes, contradictions, high_value)
		report['phases']['gaps'] = gaps

		# Phase 8: Original synthesis
		synthesis = self._original_synthesis(refined_query, themes, contradictions, gaps)
		report['phases']['synthesis'] = synthesis

		# Phase 9: Thesis chapter
		thesis = self._write_thesis_chapter(refined_query, rq, scope, themes,
		                                    contradictions, gaps, synthesis, high_value)
		report.update(thesis)

		# Phase 10: Self-critique
		limitations = self._self_critique(refined_query, thesis)
		report['limitations'] = limitations
		report['phases']['self_critique'] = limitations

		return report

	# ── Phase helpers ──────────────────────────────────────────────────────

	def _decompose(self, query: str, n: int = 5) -> list[str]:
		prompt = (
			f"Break the following research question into {n} focused, non-overlapping sub-questions "
			f"that together fully cover the topic.\n\nResearch question: {query}\n\n"
			f"Return a JSON array of {n} sub-question strings."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\[.*\]', response, re.DOTALL)
			if match:
				qs = json.loads(match.group())
				if isinstance(qs, list) and qs:
					return [str(q) for q in qs[:n]]
		except Exception:
			pass
		# Fallback: generate generic sub-questions
		return [
			f"What is the current state of {query}?",
			f"What are the key factors that influence {query}?",
			f"What does recent research say about {query}?",
			f"What are the practical implications of {query}?",
			f"What are the open challenges and future directions for {query}?",
		]

	def _investigate_sub_question(self, sub_question: str, read_full: bool = False) -> dict:
		from core.agent_loop import research_agent
		extra = ' Use scrape_url to read key articles in full.' if read_full else ''
		agent = research_agent(max_iterations=8)
		return agent.run(sub_question + extra)

	def _synthesize_sub_question(self, main_query: str, sub_question: str, findings: str) -> str:
		prompt = (
			f"Context: researching '{main_query}'\n"
			f"Sub-question: {sub_question}\n\n"
			f"Findings:\n{findings[:3000]}\n\n"
			f"Write a concise, critical synthesis (2-3 paragraphs) of these findings. "
			f"Note evidence quality, consensus, and key uncertainties."
		)
		return self.ai_engine.generate_text(prompt).strip()

	def _integrate(self, query: str, sub_questions: list, syntheses: dict) -> str:
		combined = '\n\n'.join(f"## {sq}\n{syntheses.get(sq, '')}" for sq in sub_questions)
		prompt = (
			f"Research question: {query}\n\n"
			f"You have researched {len(sub_questions)} sub-questions. "
			f"Integrate these findings into a coherent overall analysis:\n\n{combined[:5000]}\n\n"
			f"Write an integrated analysis (4-6 paragraphs) that draws connections, "
			f"identifies patterns, and builds toward an overall understanding."
		)
		return self.ai_engine.generate_text(prompt).strip()

	def _critique(self, query: str, integration: str) -> dict:
		prompt = (
			f"Research question: {query}\n\n"
			f"Draft analysis:\n{integration[:3000]}\n\n"
			f"Critically evaluate this analysis. Return JSON with keys: "
			f"strengths (list), weaknesses (list), unsupported_claims (list), "
			f"missing_perspectives (list), evidence_quality_assessment, "
			f"contradictions_noted (list), overall_rating (1-10)."
		)
		return self._llm_json(prompt, fallback_key='overall_rating')

	def _write_academic_report(self, query: str, integration: str, critique: dict, syntheses: dict) -> dict:
		prompt = (
			f"Write a structured academic research report on: {query}\n\n"
			f"Based on:\n"
			f"Integrated analysis: {integration[:2000]}\n"
			f"Critical assessment: {json.dumps(critique, indent=2)[:1000]}\n\n"
			f"Return JSON with keys: "
			f"abstract (200 words), "
			f"introduction (context and motivation), "
			f"literature_review (what is known), "
			f"analysis (your synthesis and interpretation), "
			f"discussion (implications), "
			f"conclusion (summary and outlook), "
			f"key_citations (list of URLs found during research), "
			f"confidence_level (high/medium/low), "
			f"research_quality_score (1-10)."
		)
		return self._llm_json(prompt, fallback_key='abstract')

	def _formulate_research_question(self, query: str) -> dict:
		prompt = (
			f"Refine the following into a precise, scholarly research question suitable for a PhD thesis.\n\n"
			f"Input: {query}\n\n"
			f"Return JSON with keys: "
			f"research_question (precise formulation), "
			f"research_objectives (list, 3-5 SMART objectives), "
			f"scope (what is included), "
			f"out_of_scope (what is excluded), "
			f"significance (why this matters), "
			f"hypothesis (if applicable), "
			f"research_paradigm (quantitative/qualitative/mixed/theoretical)."
		)
		return self._llm_json(prompt, fallback_key='research_question')

	def _define_scope(self, query: str) -> dict:
		prompt = (
			f"Define the scope and search strategy for a systematic literature review on:\n{query}\n\n"
			f"Return JSON with keys: "
			f"inclusion_criteria (list), "
			f"exclusion_criteria (list), "
			f"time_range (years to cover), "
			f"key_databases (where to search), "
			f"primary_keywords (list), "
			f"secondary_keywords (list), "
			f"expected_evidence_types (list)."
		)
		return self._llm_json(prompt, fallback_key='inclusion_criteria')

	def _build_search_vectors(self, query: str, scope: dict) -> list[str]:
		"""Generate 5 orthogonal search queries from different angles."""
		keywords = scope.get('primary_keywords', [])
		secondary = scope.get('secondary_keywords', [])
		base_terms = ' '.join(keywords[:3]) if keywords else query
		vectors = [
			query,                                           # direct
			f"{base_terms} systematic review meta-analysis", # academic
			f"{base_terms} recent advances 2023 2024 2025",  # recent
			f"{' '.join(secondary[:3])} {base_terms}" if secondary else f"critique limitations {query}",
			f"{base_terms} future directions challenges open problems",
		]
		return vectors

	def _evaluate_sources(self, query: str, sources: list) -> list:
		"""Evaluate source relevance and quality in a single LLM call."""
		sources_text = json.dumps([
			{'title': s.get('title', ''), 'url': s.get('href', s.get('url', '')), 'snippet': s.get('body', '')[:200]}
			for s in sources[:20]
		], indent=1)
		prompt = (
			f"Research question: {query}\n\n"
			f"Evaluate these sources for a systematic literature review. "
			f"For each, decide whether to include or exclude based on relevance and likely quality.\n\n"
			f"Sources:\n{sources_text}\n\n"
			f"Return a JSON array, one object per source, with keys: "
			f"title, url, include (bool), relevance_score (1-10), "
			f"reason (brief justification)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\[.*\]', response, re.DOTALL)
			if match:
				evaluated = json.loads(match.group())
				# Merge evaluation back into source objects
				eval_by_url = {e.get('url', ''): e for e in evaluated}
				for s in sources:
					url = s.get('href', s.get('url', ''))
					if url in eval_by_url:
						s.update(eval_by_url[url])
				return sources
		except Exception:
			pass
		# Fallback: include all
		for s in sources:
			s.setdefault('include', True)
			s.setdefault('relevance_score', 5)
		return sources

	def _thematic_analysis(self, query: str, sources: list, full_texts: dict) -> dict:
		context = self._format_search_results(sources[:10])
		ft_summary = '\n\n'.join(f"[{url}]\n{text[:800]}" for url, text in list(full_texts.items())[:4])
		prompt = (
			f"Research question: {query}\n\n"
			f"Source summaries:\n{context[:2000]}\n\n"
			f"Full text excerpts:\n{ft_summary[:3000]}\n\n"
			f"Perform a thematic analysis. Identify the major themes across these sources. "
			f"Return JSON with keys: "
			f"themes (list, each with: theme_name, description, supporting_sources (list of URLs), "
			f"evidence_strength (strong/moderate/weak)), "
			f"dominant_paradigm, theoretical_frameworks_used (list), "
			f"methodological_approaches (list)."
		)
		return self._llm_json(prompt, fallback_key='themes')

	def _map_contradictions(self, query: str, sources: list, full_texts: dict) -> dict:
		context = self._format_search_results(sources[:10])
		prompt = (
			f"Research question: {query}\n\n"
			f"Sources:\n{context[:3000]}\n\n"
			f"Identify contradictions, disagreements, and debates in this literature. "
			f"Return JSON with keys: "
			f"contradictions (list, each with: claim_a, claim_b, source_a, source_b, "
			f"nature_of_disagreement, resolution_status (resolved/unresolved/ongoing_debate)), "
			f"consensus_areas (list of things widely agreed upon), "
			f"contested_areas (list of ongoing debates)."
		)
		return self._llm_json(prompt, fallback_key='contradictions')

	def _gap_analysis(self, query: str, themes: dict, contradictions: dict, sources: list) -> dict:
		prompt = (
			f"Research question: {query}\n\n"
			f"Themes identified: {json.dumps(themes.get('themes', []))[:1500]}\n"
			f"Contested areas: {json.dumps(contradictions.get('contested_areas', []))[:800]}\n\n"
			f"Identify research gaps — what has NOT been studied, what questions remain unanswered, "
			f"what methodologies are missing. Return JSON with keys: "
			f"knowledge_gaps (list, each with: gap_description, significance, suggested_approach), "
			f"methodological_gaps (list), "
			f"empirical_gaps (list), "
			f"theoretical_gaps (list), "
			f"priority_gaps (top 3 most important, list)."
		)
		return self._llm_json(prompt, fallback_key='knowledge_gaps')

	def _original_synthesis(self, query: str, themes: dict, contradictions: dict, gaps: dict) -> str:
		prompt = (
			f"Research question: {query}\n\n"
			f"Based on your analysis of the literature:\n"
			f"- Themes: {json.dumps(themes.get('themes', []))[:1200]}\n"
			f"- Key contradictions: {json.dumps(contradictions.get('contested_areas', []))[:600]}\n"
			f"- Research gaps: {json.dumps(gaps.get('priority_gaps', []))[:600]}\n\n"
			f"Write an ORIGINAL synthesis — not a summary, but a novel analytical perspective "
			f"that advances understanding beyond what any single source says. "
			f"Identify patterns, propose explanatory frameworks, or offer a new interpretation. "
			f"This should be the intellectual contribution of the review. (4-6 paragraphs)"
		)
		return self.ai_engine.generate_text(prompt).strip()

	def _write_thesis_chapter(self, query, rq, scope, themes, contradictions, gaps, synthesis, sources) -> dict:
		citations = [s.get('href', s.get('url', '')) for s in sources if s.get('href') or s.get('url')]
		prompt = (
			f"Write a complete PhD thesis chapter (literature review) on: {query}\n\n"
			f"Research question: {rq.get('research_question', query)}\n"
			f"Scope: {json.dumps(scope)[:500]}\n\n"
			f"Use all the analysis you've done. Return JSON with keys: "
			f"title, "
			f"abstract (250 words), "
			f"introduction (600 words: background, motivation, chapter structure), "
			f"theoretical_framework (300 words), "
			f"literature_review (1500 words: systematic review organized by themes), "
			f"critical_analysis (600 words: contradictions, debates, evidence quality), "
			f"synthesis (from the original synthesis, 600 words), "
			f"research_gaps_and_future_directions (400 words), "
			f"conclusion (300 words: key takeaways), "
			f"references (list of URLs as placeholder citations), "
			f"word_count_estimate, "
			f"academic_quality_score (1-10, self-assessed)."
		)
		result = self._llm_json(prompt, fallback_key='title')
		if citations and 'references' not in result:
			result['references'] = citations
		return result

	def _self_critique(self, query: str, thesis: dict) -> dict:
		chapter_text = thesis.get('literature_review', '') + thesis.get('critical_analysis', '')
		prompt = (
			f"Critically assess this PhD thesis chapter on '{query}' as a peer reviewer would.\n\n"
			f"Chapter excerpt:\n{chapter_text[:2000]}\n\n"
			f"Return JSON with keys: "
			f"strengths (list), "
			f"limitations (list), "
			f"validity_threats (list), "
			f"suggestions_for_future_research (list), "
			f"overall_contribution (brief statement), "
			f"publishability_assessment."
		)
		return self._llm_json(prompt, fallback_key='limitations')

	# ── Utilities ─────────────────────────────────────────────────────────

	def _llm_json(self, prompt: str, fallback_key: str = 'result') -> dict:
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {fallback_key: response, 'status': 'success'}

	@staticmethod
	def _format_search_results(results: list) -> str:
		lines = []
		for r in results:
			title = r.get('title', 'Untitled')
			url = r.get('href', r.get('url', ''))
			body = r.get('body', r.get('snippet', ''))[:400]
			lines.append(f'[{title}]({url})\n{body}')
		return '\n\n'.join(lines)

# capabilities/niche_finder.py
# Strategic niche-finder capability.
#
# Modes:
#   quick    — LLM prior knowledge only (~5s). Good for brainstorming.
#   research — Multi-phase agentic search → synthesis (~5-10 min).
#              Backed by real public data: incumbent analysis, founder interviews,
#              regulatory shifts, behavioral trends, pricing benchmarks.
#
# Output always includes:
#   landscape      — key players, startups, core product capabilities
#   pnf_analysis   — well-served / underserved / emerging user needs
#   gaps           — where demand exceeds supply
#   niches         — 1-3 concrete niche propositions, each with:
#                    hypothesis, target_segment, jtbd, differentiator,
#                    revenue_model, pricing_logic, risks, gtm_path

import json
import re
import time

from core.ai_engine import AIModel
from core.search_engine import SearchEngine

_SYSTEM_PROMPT = """\
You are an elite strategic niche-finder and product strategist. Your job is to identify \
product capability niches that can be profitably built within a given industry.

Methodology:
1. Map the landscape — key players/incumbents, notable startups, core product capabilities.
2. Analyse product-market fit — well-served, underserved, and emerging user needs; friction \
points, regulatory shifts, behavioural trends.
3. Spot gaps — where demand exceeds supply or existing solutions lack depth, accessibility, \
or integration.
4. Evaluate commercial viability — willingness to pay, market size, competitive moats, \
unit economics.
5. Synthesise 1-3 concrete, differentiated niche propositions.

Prioritise niches that are narrow enough to dominate quickly but large enough to sustain \
a profitable business. Base analysis on verifiable public information: founder interviews, \
industry reports, regulatory filings, pricing pages, user reviews.
"""


class NicheFinder:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	# ── Public API ──────────────────────────────────────────────────────────

	def find_niches(
		self,
		industry: str,
		mode: str = 'research',
		num_niches: int = 3,
		focus_area: str = '',
	) -> dict:
		"""
		industry    — e.g. 'fintech', 'healthtech', 'proptech', 'edtech'
		mode        — 'quick' (LLM only) | 'research' (agentic search + synthesis)
		num_niches  — how many niche propositions to produce (1-5)
		focus_area  — optional constraint e.g. 'SME lending', 'mental health'
		"""
		if mode not in ('quick', 'research'):
			mode = 'research'
		num_niches = max(1, min(5, num_niches))

		start = time.time()
		if mode == 'quick':
			result = self._quick_analysis(industry, num_niches, focus_area)
		else:
			result = self._research_analysis(industry, num_niches, focus_area)

		result['industry'] = industry
		result['mode'] = mode
		result['focus_area'] = focus_area
		result['elapsed_seconds'] = round(time.time() - start, 1)
		return result

	# ── Quick mode ──────────────────────────────────────────────────────────

	def _quick_analysis(self, industry: str, num_niches: int, focus_area: str) -> dict:
		focus_clause = f' with a focus on {focus_area}' if focus_area else ''
		prompt = (
			f"{_SYSTEM_PROMPT}\n\n"
			f"Industry: {industry}{focus_clause}\n\n"
			f"Using your knowledge, produce a full niche analysis. "
			f"Return JSON with keys:\n"
			f"  landscape (dict): {{\n"
			f"    incumbents (list of {{name, core_capabilities (list), market_position}}),\n"
			f"    startups (list of {{name, focus, stage, differentiator}}),\n"
			f"    technology_stack (dominant technologies list)\n"
			f"  }},\n"
			f"  pmf_analysis (dict): {{\n"
			f"    well_served_needs (list),\n"
			f"    underserved_needs (list of {{need, evidence, severity (high/medium/low)}}),\n"
			f"    emerging_needs (list),\n"
			f"    friction_points (list),\n"
			f"    regulatory_tailwinds (list),\n"
			f"    behavioural_trends (list)\n"
			f"  }},\n"
			f"  gaps (list of {{gap, demand_signal, supply_weakness, integration_opportunity}}),\n"
			f"  niches (list of {num_niches} objects, each with:\n"
			f"    hypothesis (one-line value proposition),\n"
			f"    target_segment,\n"
			f"    jtbd (job-to-be-done, underserved),\n"
			f"    differentiator (vs incumbents/alternatives),\n"
			f"    revenue_model,\n"
			f"    pricing_logic (initial pricing rationale + ballpark figures),\n"
			f"    market_size_estimate,\n"
			f"    competitive_moat,\n"
			f"    unit_economics_note,\n"
			f"    risks (list of {{risk, mitigation}}),\n"
			f"    gtm_path (step-by-step entry strategy)\n"
			f"  ),\n"
			f"  confidence_note (caveats on LLM-only analysis)"
		)
		return self._llm_json(prompt, fallback_key='niches')

	# ── Research mode ───────────────────────────────────────────────────────

	def _research_analysis(self, industry: str, num_niches: int, focus_area: str) -> dict:
		"""
		Phase 1 — Landscape: search incumbents, startups, funding rounds.
		Phase 2 — PMF: search pain points, user reviews, forum discussions.
		Phase 3 — Regulatory/trends: search regulatory changes, market reports.
		Phase 4 — Pricing/moats: search pricing pages, teardowns, benchmarks.
		Phase 5 — Synthesis: agent loop for cross-cutting research.
		Phase 6 — Niche formulation: structured LLM synthesis.
		"""
		focus_clause = f' {focus_area}' if focus_area else ''
		result = {'phases': {}}

		# Phase 1: Landscape
		landscape_data = self._phase_landscape(industry, focus_clause)
		result['phases']['landscape_research'] = landscape_data

		# Phase 2: PMF
		pmf_data = self._phase_pmf(industry, focus_clause)
		result['phases']['pmf_research'] = pmf_data

		# Phase 3: Regulatory/trends
		trends_data = self._phase_trends(industry, focus_clause)
		result['phases']['trends_research'] = trends_data

		# Phase 4: Pricing / commercial signals
		pricing_data = self._phase_pricing(industry, focus_clause)
		result['phases']['pricing_research'] = pricing_data

		# Phase 5: Agent loop for depth (follows leads across all four areas)
		agent_findings = self._phase_agent_synthesis(industry, focus_area, num_niches)
		result['phases']['agent_synthesis'] = agent_findings.get('answer', '')[:2000]
		result['phases']['agent_tool_calls'] = len(agent_findings.get('tool_calls', []))

		# Phase 6: Final structured niche synthesis
		niche_report = self._synthesize_niches(
			industry, focus_area, num_niches,
			landscape_data, pmf_data, trends_data, pricing_data, agent_findings
		)
		result.update(niche_report)
		return result

	def _phase_landscape(self, industry: str, focus_clause: str) -> dict:
		queries = [
			f"{industry}{focus_clause} key players incumbent companies 2024 2025",
			f"{industry}{focus_clause} top startups funding Y Combinator Sequoia",
			f"{industry}{focus_clause} product features comparison review",
		]
		sources = []
		for q in queries:
			results = self.search_engine.search(q, num_results=5)
			sources.extend(results)
		context = _format_results(sources[:12])
		prompt = (
			f"Industry: {industry}{focus_clause}\n\n"
			f"Search data:\n{context[:3000]}\n\n"
			f"Map the competitive landscape. Return JSON with keys: "
			f"incumbents (list of {{name, core_capabilities (list), market_position, weakness}}), "
			f"startups (list of {{name, focus, stage, differentiator, funding}}), "
			f"technology_stack (list), market_maturity (emerging/growing/mature/declining)."
		)
		return self._llm_json(prompt, fallback_key='incumbents')

	def _phase_pmf(self, industry: str, focus_clause: str) -> dict:
		queries = [
			f"{industry}{focus_clause} user pain points complaints Reddit Hacker News",
			f"{industry}{focus_clause} underserved market unmet needs customers",
			f"{industry}{focus_clause} G2 Capterra reviews problems limitations",
		]
		sources = []
		for q in queries:
			results = self.search_engine.search(q, num_results=5)
			sources.extend(results)
		context = _format_results(sources[:12])
		prompt = (
			f"Industry: {industry}{focus_clause}\n\n"
			f"User feedback + market data:\n{context[:3000]}\n\n"
			f"Analyze product-market fit across this industry. Return JSON with keys: "
			f"well_served_needs (list), "
			f"underserved_needs (list of {{need, evidence, severity (high/medium/low), affected_segment}}), "
			f"emerging_needs (list), "
			f"friction_points (list of {{friction, root_cause, who_feels_it}}), "
			f"switching_barriers (list)."
		)
		return self._llm_json(prompt, fallback_key='underserved_needs')

	def _phase_trends(self, industry: str, focus_clause: str) -> dict:
		queries = [
			f"{industry}{focus_clause} regulatory changes 2024 2025 compliance",
			f"{industry}{focus_clause} market trends report growth forecast",
			f"{industry}{focus_clause} behavioral shift customer adoption trends",
		]
		sources = []
		for q in queries:
			results = self.search_engine.search(q, num_results=5)
			sources.extend(results)
		context = _format_results(sources[:12])
		prompt = (
			f"Industry: {industry}{focus_clause}\n\n"
			f"News + reports:\n{context[:3000]}\n\n"
			f"Identify trends creating opportunity. Return JSON with keys: "
			f"regulatory_tailwinds (list of {{regulation, impact, timeline}}), "
			f"regulatory_headwinds (list), "
			f"behavioral_trends (list of {{trend, evidence, opportunity}}), "
			f"technology_enablers (list of new tech making new products possible), "
			f"market_size_signals (evidence on TAM/SAM growth)."
		)
		return self._llm_json(prompt, fallback_key='behavioral_trends')

	def _phase_pricing(self, industry: str, focus_clause: str) -> dict:
		queries = [
			f"{industry}{focus_clause} pricing SaaS subscription model pricing page",
			f"{industry}{focus_clause} willingness to pay customer acquisition cost LTV",
			f"{industry}{focus_clause} unit economics startup revenue model teardown",
		]
		sources = []
		for q in queries:
			results = self.search_engine.search(q, num_results=5)
			sources.extend(results)
		context = _format_results(sources[:12])
		prompt = (
			f"Industry: {industry}{focus_clause}\n\n"
			f"Pricing + economics data:\n{context[:3000]}\n\n"
			f"Extract commercial signals. Return JSON with keys: "
			f"observed_pricing_models (list of {{company, model, price_point, what_included}}), "
			f"willingness_to_pay_signals (evidence of price sensitivity or premium acceptance), "
			f"average_deal_size (if detectable), "
			f"customer_acquisition_benchmarks, "
			f"margin_profile_notes."
		)
		return self._llm_json(prompt, fallback_key='observed_pricing_models')

	def _phase_agent_synthesis(self, industry: str, focus_area: str, num_niches: int) -> dict:
		from core.agent_loop import AgentLoop
		from core.tools import RESEARCH_TOOLS
		focus_clause = f' focused on {focus_area}' if focus_area else ''
		system = (
			f"{_SYSTEM_PROMPT}\n\n"
			f"You are researching the {industry} industry{focus_clause} to find {num_niches} profitable niche opportunities. "
			f"Search for: (1) specific user complaints and unmet needs, "
			f"(2) startups that recently raised seed/Series A in this space and what problem they solve, "
			f"(3) regulatory announcements in the past 2 years, "
			f"(4) pricing pages and revenue models of incumbents, "
			f"(5) analyst reports on market gaps. "
			f"Follow leads. Be specific."
		)
		agent = AgentLoop(
			tools=RESEARCH_TOOLS,
			max_iterations=15,
			system_prompt=system,
		)
		query = (
			f"Find the most promising product niches in the {industry} industry{focus_clause}. "
			f"Research incumbents, user pain points, regulatory tailwinds, and recent startup activity."
		)
		return agent.run(query)

	def _synthesize_niches(
		self,
		industry: str,
		focus_area: str,
		num_niches: int,
		landscape: dict,
		pmf: dict,
		trends: dict,
		pricing: dict,
		agent_findings: dict,
	) -> dict:
		focus_clause = f' (focus: {focus_area})' if focus_area else ''
		context = (
			f"Landscape:\n{json.dumps(landscape, indent=1)[:1500]}\n\n"
			f"PMF analysis:\n{json.dumps(pmf, indent=1)[:1500]}\n\n"
			f"Trends:\n{json.dumps(trends, indent=1)[:1000]}\n\n"
			f"Pricing signals:\n{json.dumps(pricing, indent=1)[:800]}\n\n"
			f"Agent research findings:\n{agent_findings.get('answer', '')[:1500]}"
		)
		prompt = (
			f"{_SYSTEM_PROMPT}\n\n"
			f"Industry: {industry}{focus_clause}\n\n"
			f"Research gathered:\n{context}\n\n"
			f"Now synthesise exactly {num_niches} concrete, differentiated niche propositions. "
			f"Each niche must be narrow enough to dominate quickly but large enough to sustain profit. "
			f"Return JSON with keys:\n"
			f"  landscape_summary (2-3 sentences on competitive landscape),\n"
			f"  key_gaps (list of top gaps identified),\n"
			f"  niches (list of {num_niches} objects, each with:\n"
			f"    hypothesis (one-line value proposition — the niche in a sentence),\n"
			f"    target_segment (who exactly),\n"
			f"    jtbd (their underserved job-to-be-done),\n"
			f"    differentiator (vs incumbents/alternatives — be specific),\n"
			f"    revenue_model (SaaS/marketplace/usage/services/etc),\n"
			f"    pricing_logic (initial price, what justifies it, comp anchors),\n"
			f"    market_size_estimate (TAM→SAM→SOM reasoning),\n"
			f"    competitive_moat (why hard to replicate),\n"
			f"    unit_economics_note (CAC, LTV, payback period intuition),\n"
			f"    risks (list of {{risk, mitigation}}),\n"
			f"    gtm_path (step-by-step entry: first 10 customers → first $1M ARR)\n"
			f"  ),\n"
			f"  methodology_note (how this analysis was conducted),\n"
			f"  confidence_level (high/medium/low with reasoning)"
		)
		return self._llm_json(prompt, fallback_key='niches')

	# ── Utilities ───────────────────────────────────────────────────────────

	def _llm_json(self, prompt: str, fallback_key: str = 'result') -> dict:
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {fallback_key: response, 'status': 'success'}


def _format_results(results: list) -> str:
	lines = []
	for r in results:
		title = r.get('title', 'Untitled')
		url = r.get('href', r.get('url', ''))
		body = r.get('body', r.get('snippet', ''))[:400]
		lines.append(f'[{title}]({url})\n{body}')
	return '\n\n'.join(lines)

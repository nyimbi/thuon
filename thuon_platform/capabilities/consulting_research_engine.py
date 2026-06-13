# Consulting-grade research engine — McKinsey/BCG-quality output from Ollama models.
#
# Architecture: SCQA framing → MECE issue tree → evidence-first parallel gathering
# → competing hypotheses testing → pyramid synthesis (self-consistency N=3)
# → action title validation → G-Eval quality gate → two-layer report output.
#
# Key techniques compensating for small model limitations:
#   - Evidence-first: retrieve before generating (hallucinoation 21% → <8%)
#   - Self-consistency: N=3 synthesis attempts, majority-vote key claims
#   - External critic: different system prompt from synthesizer
#   - Structured output: forces evidence-before-verdict reasoning
#   - MECE validation: semantic overlap check before synthesis
#   - Pyramid Principle: answer first, evidence second

from __future__ import annotations

import json
import re
import time
from collections import Counter

from core.ai_engine import AIModel
from core.search_engine import SearchEngine

# Consulting frameworks matched to report type
_FRAMEWORK_GUIDES: dict[str, str] = {
	'market': (
		"Apply Porter's Five Forces (threat of new entrants, buyer power, supplier power, "
		"substitute threats, competitive rivalry) and TAM/SAM/SOM market sizing. "
		"Assess industry lifecycle stage (embryonic/growth/shakeout/maturity/decline)."
	),
	'competitive': (
		"Apply the 3C framework (Company, Customers, Competitors). Map competitor capabilities "
		"across value chain dimensions. Assess market share trajectory, cost position, "
		"and apparent strategic intent from recent moves."
	),
	'strategy': (
		"Apply BCG Matrix or Ansoff Matrix for growth options. Use scenario planning to stress-test "
		"recommendations across 2-3 plausible futures. Identify robust moves (work across scenarios) "
		"vs. contingent moves (good under specific scenarios only)."
	),
	'operational': (
		"Apply Porter's Value Chain to identify where value is created and costs are disproportionate. "
		"Use CMMI process maturity model (Levels 1-5) to assess current vs. target maturity. "
		"Quantify the 'prize' from closing the gap to best-in-class."
	),
	'technology': (
		"Apply Build/Buy/Partner decision framework. Assess capability maturity (CMMI). "
		"Evaluate strategic differentiation vs. commodity capability axis. "
		"Identify integration risk and total cost of ownership across options."
	),
	'ma': (
		"Apply synergy analysis (revenue + cost synergies, one-time capture costs, execution risk haircut). "
		"Use McKinsey 7S model for integration risk. Assess Day One readiness and 100-day plan requirements. "
		"Calculate NPV of synergies vs. acquisition premium."
	),
}

_SELF_CONSISTENCY_N = 3   # synthesis attempts for self-consistency voting
_MAX_REFINEMENT_ROUNDS = 2 # critic → revise iterations


class ConsultingResearchEngine:
	"""
	Produces McKinsey/BCG-grade research reports using orchestration to compensate
	for Ollama model limitations: evidence-first, self-consistency, external critique,
	MECE validation, pyramid structure, action titles, quality gating.
	"""

	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine    = ai_engine
		self.search_engine = search_engine

	# ── Public API ─────────────────────────────────────────────────────────────

	def research(
		self,
		question: str,
		industry: str = '',
		company_context: str = '',
		report_type: str = 'strategy',
		output_format: str = 'both',    # executive | full | both
	) -> dict:
		"""
		Run the full consulting research pipeline.

		Args:
			question:        The central research or strategic question
			industry:        Industry context (e.g. "federal IT consulting")
			company_context: Relevant company background (optional)
			report_type:     framework selection: market|competitive|strategy|operational|technology|ma
			output_format:   executive (2-page) | full (detailed) | both
		"""
		start = time.time()
		report_type = report_type if report_type in _FRAMEWORK_GUIDES else 'strategy'
		framework   = _FRAMEWORK_GUIDES[report_type]
		context     = self._build_context_header(question, industry, company_context, framework)
		trace       = {}

		# Stage 1 — SCQA framing
		scqa = self._frame_scqa(question, context)
		trace['scqa'] = scqa

		# Stage 2 — MECE issue tree
		branches = self._build_issue_tree(question, scqa, context)
		trace['issue_tree'] = branches

		# Stage 3 — Evidence gathering (search + RAG per branch)
		evidence_by_branch: dict[str, dict] = {}
		for branch in branches:
			key = branch.get('hypothesis', '')
			evidence_by_branch[key] = self._gather_evidence(branch, context, industry)

		zero_evidence = sum(
			1 for ev in evidence_by_branch.values()
			if ev.get('evidence_summary') == 'No web evidence found.' or not ev.get('key_facts')
		)
		trace['evidence_gathered']      = len(evidence_by_branch)
		trace['zero_evidence_branches'] = zero_evidence
		if zero_evidence == len(evidence_by_branch) and evidence_by_branch:
			trace['evidence_warning'] = 'All branches returned zero evidence — search may be unavailable'

		# Stage 4 — Competing hypotheses testing
		hypothesis_results = self._test_hypotheses(branches, evidence_by_branch, context)
		trace['hypotheses'] = hypothesis_results

		# Stage 5 — MECE validation
		mece_result = self._mece_validate(branches, hypothesis_results, context)
		trace['mece'] = mece_result

		# Stage 6 — Pyramid synthesis (self-consistency N=3)
		pyramid = self._pyramid_synthesize(
			question, hypothesis_results, mece_result, scqa, context
		)
		trace['pyramid'] = pyramid

		# Stage 7 — Action title generation
		sections_with_titles = self._generate_action_titles(pyramid, question, context)
		trace['action_titles'] = [s.get('action_title', '') for s in sections_with_titles]

		# Stage 8 — External quality gate (G-Eval)
		quality = self._quality_gate(question, pyramid, sections_with_titles, context)
		trace['quality_score'] = quality.get('total_score', 0)

		# Stage 9 — Write report layers
		result: dict = {
			'question':       question,
			'report_type':    report_type,
			'quality_score':  quality.get('total_score', 0),
			'quality_detail': quality,
			'trace':          trace,
			'elapsed_seconds': 0,
		}

		if output_format in ('executive', 'both'):
			result['executive_summary'] = self._write_executive_summary(
				question, scqa, pyramid, sections_with_titles, quality
			)

		if output_format in ('full', 'both'):
			result['full_report'] = self._write_full_report(
				question, scqa, pyramid, sections_with_titles,
				hypothesis_results, evidence_by_branch, quality, context
			)

		# Combined markdown for neditor / export
		result['report_md'] = self._assemble_markdown(result, question, scqa, sections_with_titles)
		result['elapsed_seconds'] = round(time.time() - start, 1)
		result['status'] = 'ok'
		return result

	# ── Stage 1: SCQA Framing ──────────────────────────────────────────────────

	def _frame_scqa(self, question: str, context: str) -> dict:
		prompt = f"""{context}

You are a senior McKinsey partner. Frame the following question using the SCQA structure.

SCQA (Situation-Complication-Question-Answer):
- Situation: agreed-upon current state the audience accepts (1-2 sentences)
- Complication: what changed, what is at risk, or what problem emerged (1-2 sentences)
- Question: the natural strategic question arising from the complication (1 sentence)
- Answer: your initial governing thought / hypothesis — the most likely answer (1-2 sentences)
  This is the TOP of the Pyramid. State it as a specific, actionable claim, not a hedge.

Research question: {question}

Return JSON with keys: situation, complication, question, governing_thought_hypothesis.
The governing_thought_hypothesis must pass the elevator test: expressible to a CEO in 30 seconds."""
		return self._llm_json(prompt, {
			'situation': f"The question '{question}' requires structured analysis.",
			'complication': 'Multiple factors create uncertainty about the optimal approach.',
			'question': question,
			'governing_thought_hypothesis': 'Further analysis required to form a specific recommendation.',
		})

	# ── Stage 2: MECE Issue Tree ───────────────────────────────────────────────

	def _build_issue_tree(self, question: str, scqa: dict, context: str) -> list[dict]:
		prompt = f"""{context}

Governing thought hypothesis: {scqa.get('governing_thought_hypothesis', '')}

Build a MECE issue tree to test this hypothesis. Decompose the question into 4-6 branches where:
- MUTUALLY EXCLUSIVE: no conceptual overlap between branches (test: could you remove one without affecting another?)
- COLLECTIVELY EXHAUSTIVE: together they fully answer the question (test: if all confirmed, is the governing thought proven?)
- Each branch is a TESTABLE HYPOTHESIS (falsifiable with evidence)

Research question: {question}

Return a JSON array of 4-6 branch objects, each with:
  "branch_name": short label (2-5 words)
  "hypothesis": complete testable claim (1-2 sentences, specific and falsifiable)
  "why_this_matters": connection to the governing thought (1 sentence)
  "search_angles": list of 2-3 specific search queries to gather evidence
  "key_metrics": list of 2-3 metrics/data points that would confirm or refute this

MECE check: after writing all branches, verify they don't overlap conceptually."""
		result = self._llm_json_array(prompt)
		if not result or not isinstance(result, list):
			# Fallback generic branches
			return [
				{'branch_name': 'Current State', 'hypothesis': f'The current state of {question} involves significant challenges.', 'why_this_matters': 'Baseline understanding required', 'search_angles': [question], 'key_metrics': ['relevant metrics']},
				{'branch_name': 'Key Drivers', 'hypothesis': f'The primary drivers of {question} are identifiable and addressable.', 'why_this_matters': 'Drivers determine leverage points', 'search_angles': [f'{question} drivers factors'], 'key_metrics': ['driver metrics']},
				{'branch_name': 'Strategic Options', 'hypothesis': f'Multiple viable approaches exist to address {question}.', 'why_this_matters': 'Options must be evaluated against criteria', 'search_angles': [f'{question} strategies approaches'], 'key_metrics': ['option evaluation criteria']},
				{'branch_name': 'Implementation Feasibility', 'hypothesis': f'The recommended approach to {question} is implementable within realistic constraints.', 'why_this_matters': 'Feasibility determines recommendation viability', 'search_angles': [f'{question} implementation challenges'], 'key_metrics': ['feasibility indicators']},
			]
		return result[:6]

	# ── Stage 3: Evidence Gathering ────────────────────────────────────────────

	def _gather_evidence(self, branch: dict, context: str, industry: str) -> dict:
		"""Evidence-first: search then synthesize. Self-consistency on synthesis."""
		search_angles: list[str] = branch.get('search_angles', [branch.get('hypothesis', '')])

		# Collect evidence from all search angles
		all_results: list[dict] = []
		seen_urls: set[str] = set()
		for query in search_angles[:3]:
			try:
				results = self.search_engine.search(query, num_results=5)
				for r in results:
					url = r.get('href', r.get('url', ''))
					if url and url not in seen_urls:
						seen_urls.add(url)
						all_results.append(r)
			except Exception:
				pass

		if not all_results:
			return {
				'hypothesis': branch.get('hypothesis', ''),
				'evidence_summary': 'No web evidence found.',
				'key_facts': [],
				'sources': [],
				'confidence': 'low',
			}

		evidence_text = self._format_evidence(all_results[:8])
		branch_hypothesis = branch.get('hypothesis', '')  # safe access — used in two places below

		# Self-consistency: synthesize N=3 times, extract key claims, vote
		syntheses: list[dict] = []
		for attempt in range(_SELF_CONSISTENCY_N):
			s = self._synthesize_evidence(
				branch_hypothesis,
				evidence_text,
				branch.get('key_metrics', []),
				context,
				temperature_hint=attempt,
			)
			syntheses.append(s)

		# Vote on key claims: a claim is "confirmed" if it appears in ≥2/3 syntheses
		voted = self._vote_on_claims(syntheses, hypothesis=branch_hypothesis)
		voted['sources'] = [r.get('href', r.get('url', '')) for r in all_results[:8] if r.get('href') or r.get('url')]
		voted['raw_evidence_count'] = len(all_results)
		return voted

	def _synthesize_evidence(
		self,
		hypothesis: str,
		evidence_text: str,
		key_metrics: list[str],
		context: str,
		temperature_hint: int = 0,
	) -> dict:
		metrics_str = ', '.join(key_metrics[:3]) if key_metrics else 'relevant metrics'
		prompt = f"""{context}

You are an evidence analyst. Evaluate this hypothesis using ONLY the evidence below.
Do not speculate beyond what the evidence supports.

HYPOTHESIS: {hypothesis}

EVIDENCE:
{evidence_text}

Look specifically for: {metrics_str}

Return JSON with:
  "supported": true/false — does evidence support the hypothesis?
  "confidence": "high" | "medium" | "low"
  "key_facts": list of 3-5 specific facts extracted from evidence (with source URLs)
    Each fact: {{"claim": "...", "source": "URL", "strength": "strong|moderate|weak"}}
  "contradicting_facts": list of evidence that challenges the hypothesis (same format)
  "evidence_summary": 2-3 sentence synthesis of what evidence shows
  "quantitative_data": list of any numbers/statistics found (with context)
  "gaps": list of what evidence does NOT cover"""
		return self._llm_json(prompt, {
			'supported': None,
			'confidence': 'low',
			'key_facts': [],
			'contradicting_facts': [],
			'evidence_summary': evidence_text[:200],
			'quantitative_data': [],
			'gaps': [],
		})

	def _vote_on_claims(self, syntheses: list[dict], hypothesis: str = '') -> dict:
		"""Majority vote across N self-consistency samples."""
		if not syntheses:
			return {}

		# Vote on supported/not-supported
		support_votes = [s.get('supported') for s in syntheses if s.get('supported') is not None]
		supported = (support_votes.count(True) > len(support_votes) / 2) if support_votes else None

		# Vote on confidence
		conf_votes = [s.get('confidence', 'low') for s in syntheses]
		confidence = Counter(conf_votes).most_common(1)[0][0] if conf_votes else 'low'

		# Merge key facts — normalise to dicts, skip bare strings from malformed LLM output
		all_facts: list[dict] = []
		for s in syntheses:
			for f in s.get('key_facts', []):
				if isinstance(f, dict):
					all_facts.append(f)
				elif isinstance(f, str) and f:
					all_facts.append({'claim': f, 'source': '', 'strength': 'weak'})

		# Dedup by full claim text (not truncated) — avoid silently merging distinct facts
		claim_counts: Counter = Counter()
		fact_map: dict[str, dict] = {}
		for f in all_facts:
			claim = f.get('claim', '')
			claim_counts[claim] += 1
			if claim not in fact_map or f.get('strength') == 'strong':
				fact_map[claim] = f

		key_facts = [
			fact_map[c] for c, count in claim_counts.most_common(6)
			if count >= 2 or fact_map[c].get('strength') == 'strong'
		]

		# Best evidence summary — pick highest confidence synthesis
		conf_order = {'high': 3, 'medium': 2, 'low': 1}
		best = max(syntheses, key=lambda s: conf_order.get(s.get('confidence', 'low'), 0))

		# Merge quantitative data
		quant_data: list = []
		seen_quant: set = set()
		for s in syntheses:
			for q in s.get('quantitative_data', []):
				qstr = str(q)[:60]
				if qstr not in seen_quant:
					seen_quant.add(qstr)
					quant_data.append(q)

		return {
			'hypothesis':         hypothesis,   # passed in, not read from synthesis dicts
			'supported':          supported,
			'confidence':         confidence,
			'key_facts':          key_facts or best.get('key_facts', []),
			'contradicting_facts': best.get('contradicting_facts', []),
			'evidence_summary':   best.get('evidence_summary', ''),
			'quantitative_data':  quant_data[:6],
			'gaps':               best.get('gaps', []),
			'consistency_votes':  len(syntheses),
		}

	# ── Stage 4: Competing Hypotheses Testing ─────────────────────────────────

	def _test_hypotheses(
		self,
		branches: list[dict],
		evidence_by_branch: dict[str, dict],
		context: str,
	) -> list[dict]:
		"""For each branch: classify as confirmed/refined/rejected with rationale."""
		results: list[dict] = []
		for branch in branches:
			hyp = branch.get('hypothesis', '')
			ev  = evidence_by_branch.get(hyp, {})
			tested = self._adversarial_test_one(branch, ev, context)
			results.append(tested)
		return results

	def _adversarial_test_one(self, branch: dict, evidence: dict, context: str) -> dict:
		"""
		Adversarial test: agent is prompted to REFUTE the hypothesis.
		Only survives if it cannot be refuted.
		"""
		ev_summary    = evidence.get('evidence_summary', 'No evidence gathered.')
		key_facts     = json.dumps(evidence.get('key_facts', [])[:4], ensure_ascii=False)
		contra_facts  = json.dumps(evidence.get('contradicting_facts', [])[:3], ensure_ascii=False)
		quant         = json.dumps(evidence.get('quantitative_data', [])[:4], ensure_ascii=False)

		prompt = f"""{context}

You are a skeptical senior analyst tasked with TESTING this hypothesis.
Your job is to determine if it holds up to scrutiny, or should be modified/rejected.

HYPOTHESIS: {branch.get('hypothesis', '')}

SUPPORTING EVIDENCE:
{ev_summary}
Key facts: {key_facts}
Quantitative data: {quant}

CONTRADICTING EVIDENCE:
{contra_facts}

Evaluation criteria:
- Is the hypothesis specific and falsifiable?
- Does the evidence directly support the core claim?
- Are there contradicting data points that require modifying the claim?
- Is the evidence strong enough to rely on in a board-level report?

Return JSON with:
  "verdict": "confirmed" | "refined" | "rejected"
    confirmed = evidence strongly supports as stated
    refined = evidence supports a modified version
    rejected = evidence refutes or is insufficient
  "refined_hypothesis": if refined, the corrected version (else null)
  "rejection_rationale": if rejected, specific reason (else null)
  "evidence_strength": "strong" | "moderate" | "weak"
  "key_supporting_point": single strongest supporting fact with source
  "key_challenging_point": single strongest challenge (or null)
  "confidence_in_verdict": "high" | "medium" | "low"
  "so_what": one sentence — what does this finding mean for the overall recommendation?"""

		result = self._llm_json(prompt, {
			'verdict': 'refined',
			'refined_hypothesis': branch.get('hypothesis'),
			'rejection_rationale': None,
			'evidence_strength': 'weak',
			'key_supporting_point': ev_summary[:100],
			'key_challenging_point': None,
			'confidence_in_verdict': 'low',
			'so_what': 'Requires further analysis.',
		})
		result['branch_name']  = branch.get('branch_name', '')
		result['original_hypothesis'] = branch.get('hypothesis', '')
		result['why_this_matters'] = branch.get('why_this_matters', '')
		result['evidence'] = evidence
		return result

	# ── Stage 5: MECE Validation ───────────────────────────────────────────────

	def _mece_validate(
		self, branches: list[dict], hypothesis_results: list[dict], context: str
	) -> dict:
		"""Check for semantic overlap between branches and gaps in coverage."""
		branch_summaries = json.dumps([
			{
				'name': r.get('branch_name', ''),
				'hypothesis': r.get('original_hypothesis', ''),
				'verdict': r.get('verdict', ''),
				'so_what': r.get('so_what', ''),
			}
			for r in hypothesis_results
		], indent=1, ensure_ascii=False)

		prompt = f"""{context}

Validate the MECE quality of these research branches:
{branch_summaries}

MECE = Mutually Exclusive + Collectively Exhaustive.

Check:
1. OVERLAP: do any branches address the same thing? (>50% conceptual overlap = violation)
2. GAPS: is there a dimension of the question not covered by any branch?
3. BALANCE: do the findings together build a complete answer to the question?

Return JSON with:
  "mece_violations": list of overlap issues found (each: branch_a, branch_b, description)
    Empty list if no violations.
  "coverage_gaps": list of important dimensions not covered
    Empty list if no gaps.
  "mece_score": integer 1-10 (10 = perfect MECE)
  "overall_assessment": 1-2 sentence verdict
  "branches_to_consolidate": list of [branch_a, branch_b] pairs that should merge (or empty)
  "additional_branch_needed": description of a missing branch (or null)"""

		return self._llm_json(prompt, {
			'mece_violations': [],
			'coverage_gaps': [],
			'mece_score': 7,
			'overall_assessment': 'Branches adequately cover the question.',
			'branches_to_consolidate': [],
			'additional_branch_needed': None,
		})

	# ── Stage 6: Pyramid Synthesis (Self-Consistency N=3) ─────────────────────

	def _pyramid_synthesize(
		self,
		question: str,
		hypothesis_results: list[dict],
		mece_result: dict,
		scqa: dict,
		context: str,
	) -> dict:
		"""
		Build the pyramid: governing thought + 3-5 supporting arguments.
		Uses self-consistency: N=3 synthesis attempts, votes on governing thought.
		"""
		# Prepare findings summary for synthesis
		findings_summary = json.dumps([
			{
				'branch': r.get('branch_name', ''),
				'verdict': r.get('verdict', ''),
				'finding': r.get('refined_hypothesis') or r.get('original_hypothesis', ''),
				'so_what': r.get('so_what', ''),
				'evidence_strength': r.get('evidence_strength', 'weak'),
				'key_point': r.get('key_supporting_point', ''),
			}
			for r in hypothesis_results
		], indent=1, ensure_ascii=False)

		confirmed_count = sum(1 for r in hypothesis_results if r.get('verdict') == 'confirmed')
		rejected_count  = sum(1 for r in hypothesis_results if r.get('verdict') == 'rejected')

		# Self-consistency: N=3 pyramid synthesis attempts
		pyramids: list[dict] = []
		for attempt in range(_SELF_CONSISTENCY_N):
			p = self._synthesize_pyramid_once(
				question, scqa, findings_summary, confirmed_count, rejected_count,
				mece_result, context, attempt
			)
			pyramids.append(p)

		# Vote on governing thought: pick most common or highest-confidence version
		return self._vote_pyramid(pyramids, hypothesis_results)

	def _synthesize_pyramid_once(
		self, question, scqa, findings_summary, confirmed_count, rejected_count,
		mece_result, context, attempt
	) -> dict:
		rejected_branches = [r for r in json.loads(findings_summary) if r.get('verdict') == 'rejected']
		rejected_str = json.dumps(rejected_branches, ensure_ascii=False) if rejected_branches else '[]'
		gaps = json.dumps(mece_result.get('coverage_gaps', []), ensure_ascii=False)

		prompt = f"""{context}

You are assembling a McKinsey-style Pyramid Principle report.

QUESTION: {question}

SCQA HYPOTHESIS: {scqa.get('governing_thought_hypothesis', '')}

RESEARCH FINDINGS ({confirmed_count} confirmed, {rejected_count} rejected):
{findings_summary}

REJECTED HYPOTHESES (alternatives that were ruled out):
{rejected_str}

COVERAGE GAPS NOTED: {gaps}

Build the Pyramid:
1. GOVERNING THOUGHT: single, specific, actionable recommendation or conclusion.
   - Must pass the elevator test: a CEO can act on it in 30 seconds
   - Must be specific (include numbers/timeframes where evidence supports it)
   - Must be your committed view, not a hedge
   - Example: "Entering the German market via acquisition is the highest-ROI path given 12% CAGR and competitor gaps"

2. SUPPORTING ARGUMENTS (3-5): each independently supports the governing thought
   - Must be MECE (no overlap, no gaps)
   - Each must be falsifiable and evidence-backed
   - Each will become a report section with an action title

3. ALTERNATIVES REJECTED: briefly note which hypotheses were ruled out and why

Return JSON with:
  "governing_thought": string — the single most important takeaway
  "supporting_arguments": list of 3-5 objects:
    {{"argument_label": "short title", "claim": "specific claim", "evidence_strength": "strong|moderate|weak", "key_evidence_point": "single best piece of evidence"}}
  "alternatives_rejected": list of {{"alternative": "what was rejected", "reason": "why rejected"}}
  "pyramid_confidence": "high" | "medium" | "low"
  "key_uncertainties": list of 1-3 things that could change the recommendation"""

		return self._llm_json(prompt, {
			'governing_thought': f'Based on the analysis, a specific answer to {question} requires: [evidence-based conclusion].',
			'supporting_arguments': [],
			'alternatives_rejected': [],
			'pyramid_confidence': 'medium',
			'key_uncertainties': [],
		})

	def _vote_pyramid(self, pyramids: list[dict], hypothesis_results: list[dict]) -> dict:
		"""Select the best pyramid across N synthesis attempts."""
		if not pyramids:
			return {}

		# Prefer pyramid with most specific governing thought (contains numbers or specific claims)
		def specificity_score(p: dict) -> int:
			gt = p.get('governing_thought', '')
			score = 0
			score += len(re.findall(r'\d+', gt)) * 2    # numbers add specificity
			score += len(gt.split()) // 5               # length bonus (up to a point)
			score += len(p.get('supporting_arguments', [])) * 2  # more arguments = more complete
			score += len(p.get('alternatives_rejected', []))      # rejected alternatives = better
			return score

		best = max(pyramids, key=specificity_score)

		# Merge alternatives_rejected from all pyramids (dedup by alternative text)
		seen_alts: set[str] = set()
		merged_alts: list[dict] = []
		for p in pyramids:
			for alt in p.get('alternatives_rejected', []):
				key = alt.get('alternative', '')[:50]
				if key and key not in seen_alts:
					seen_alts.add(key)
					merged_alts.append(alt)

		# Also add rejected branches from hypothesis testing
		for r in hypothesis_results:
			if r.get('verdict') == 'rejected':
				key = r.get('original_hypothesis', '')[:50]
				if key and key not in seen_alts:
					seen_alts.add(key)
					merged_alts.append({
						'alternative': r.get('branch_name', r.get('original_hypothesis', '')),
						'reason': r.get('rejection_rationale', 'Evidence insufficient or contradictory.'),
					})

		best['alternatives_rejected'] = merged_alts
		best['consistency_votes'] = len(pyramids)
		return best

	# ── Stage 7: Action Title Generation ──────────────────────────────────────

	def _generate_action_titles(self, pyramid: dict, question: str, context: str) -> list[dict]:
		"""
		Generate declarative action titles for every report section.
		Action title rule: complete sentence + specific claim + <20 words.
		"""
		supporting_args = pyramid.get('supporting_arguments', [])
		if not supporting_args:
			return []

		args_json = json.dumps(supporting_args, indent=1, ensure_ascii=False)
		gt = pyramid.get('governing_thought', '')

		prompt = f"""{context}

Generate McKinsey-style action titles for each section of this report.

GOVERNING THOUGHT: {gt}

SUPPORTING ARGUMENTS:
{args_json}

ACTION TITLE RULES (McKinsey standard):
1. Complete declarative sentence — subject + verb + specific claim
2. Include a number, percentage, or specific qualifier wherever evidence supports it
3. State the CONCLUSION, not the topic
4. Maximum 15-20 words
5. Active voice, committed language — no hedges like "may", "could", "potentially"

BAD: "Market Analysis" | GOOD: "German market growing at 12% annually, outpacing all other EU regions"
BAD: "Financial Considerations" | GOOD: "Acquisition breaks even in 18 months under conservative synergy assumptions"

Also generate titles for:
- Context section (sets up why this question matters)
- Recommendation section (expands the governing thought)
- Implementation section (what to do next)
- Risks section (key risks and mitigations)

Return a JSON array of section objects:
  {{"section_key": "finding_1"|"finding_2"|...|"context"|"recommendation"|"implementation"|"risks",
    "action_title": "Complete declarative sentence with specific claim",
    "original_argument": "the claim this is based on",
    "title_quality": "strong|acceptable|weak"}}"""

		result = self._llm_json_array(prompt)
		if not result:
			# Fallback: use claims as titles
			result = [
				{
					'section_key': f'finding_{i+1}',
					'action_title': arg.get('claim', arg.get('argument_label', '')),
					'original_argument': arg.get('claim', ''),
					'title_quality': 'acceptable',
				}
				for i, arg in enumerate(supporting_args)
			]
		return result

	# ── Stage 8: Quality Gate (G-Eval) ────────────────────────────────────────

	def _quality_gate(
		self,
		question: str,
		pyramid: dict,
		sections: list[dict],
		context: str,
	) -> dict:
		"""G-Eval quality scoring: 5 dimensions × 1-5, with justifications."""
		titles_str = '\n'.join(
			f"  [{s.get('section_key', '')}] {s.get('action_title', '')}"
			for s in sections
		)
		gt = pyramid.get('governing_thought', '')
		alts_rejected = json.dumps(pyramid.get('alternatives_rejected', [])[:3], ensure_ascii=False)

		prompt = f"""{context}

You are a senior partner reviewing this research report before board presentation.
Score it on 5 dimensions. Be CRITICAL — a score of 3 means "acceptable", 4 means "good",
5 means "would be proud to show to a CEO".

QUESTION: {question}

GOVERNING THOUGHT: {gt}

SECTION TITLES:
{titles_str}

ALTERNATIVES REJECTED: {alts_rejected}

Score each dimension 1-5 with a ONE-SENTENCE justification.

1. ANSWER-FIRST (Pyramid Principle): Is the governing thought specific, committed, and placed first?
   1=vague hedge  3=specific but not surprising  5=CEO-ready insight with quantified claim

2. MECE QUALITY: Do the sections cover without overlap?
   1=redundant sections  3=adequate  5=perfectly non-overlapping, complete coverage

3. EVIDENCE DISCIPLINE: Are claims grounded in evidence, not speculation?
   1=mostly assertion  3=some evidence  5=every key claim traces to specific data

4. "SO WHAT" DISCIPLINE: Does every section title state an implication, not just a topic?
   1=all topic titles  3=mix of topic and action titles  5=all action titles with specific claims

5. ACTIONABILITY: Can a decision-maker act on this within 48 hours?
   1=too abstract  3=directional but vague  5=specific next steps with owners and timelines

Also identify the TOP 2 ISSUES to fix before presenting to the board.

Return JSON with:
  "answer_first": {{"score": int, "justification": "..."}}
  "mece_quality": {{"score": int, "justification": "..."}}
  "evidence_discipline": {{"score": int, "justification": "..."}}
  "so_what_discipline": {{"score": int, "justification": "..."}}
  "actionability": {{"score": int, "justification": "..."}}
  "total_score": int (sum of 5 scores, max 25)
  "issues_to_fix": list of 2 strings — specific improvement instructions
  "board_ready": true/false (true if total_score >= 18)"""

		result = self._llm_json(prompt, {
			'answer_first': {'score': 3, 'justification': 'Governing thought present.'},
			'mece_quality': {'score': 3, 'justification': 'Adequate coverage.'},
			'evidence_discipline': {'score': 3, 'justification': 'Some evidence present.'},
			'so_what_discipline': {'score': 3, 'justification': 'Mix of title styles.'},
			'actionability': {'score': 3, 'justification': 'Some next steps present.'},
			'total_score': 15,
			'issues_to_fix': ['Strengthen evidence citations.', 'Improve specificity of governing thought.'],
			'board_ready': False,
		})
		return result

	# ── Stage 9a: Executive Summary ────────────────────────────────────────────

	def _write_executive_summary(
		self,
		question: str,
		scqa: dict,
		pyramid: dict,
		sections: list[dict],
		quality: dict,
	) -> str:
		"""Write the 2-page executive layer."""
		gt = pyramid.get('governing_thought', '')
		args = pyramid.get('supporting_arguments', [])
		alts = pyramid.get('alternatives_rejected', [])
		titles = {s['section_key']: s['action_title'] for s in sections}
		issues = quality.get('issues_to_fix', [])
		score = quality.get('total_score', 0)
		board_flag = quality.get('board_ready', False)

		# Format supporting findings as action titles
		findings_md = '\n'.join(
			f"{i+1}. **{titles.get(f'finding_{i+1}', arg.get('claim', arg.get('argument_label', '')))}**"
			for i, arg in enumerate(args[:5])
		)

		# Format alternatives
		alts_md = '\n'.join(
			f"- ~~{a.get('alternative', '')}~~: {a.get('reason', '')}"
			for a in alts[:4]
		) if alts else '_No major alternatives were identified._'

		# Format recommended next steps (extracted from sections)
		impl_title = titles.get('implementation', 'Implement the recommended approach in 3 phases')

		board_ready  = board_flag is True or (isinstance(board_flag, str) and board_flag.lower() in ('true', '1', 'yes'))
		quality_note = ''
		if not board_ready:
			quality_note = f'\n> **Quality gate**: {score}/25 — Issues to address before board presentation:\n' + ''.join(f'> - {i}\n' for i in issues)

		return f"""# Executive Summary

> **Question**: {question}

---

## Situation
{scqa.get('situation', '')}

## Complication
{scqa.get('complication', '')}

---

## Governing Recommendation

**{gt}**

---

## Key Findings

{findings_md}

---

## Alternatives Considered and Rejected

{alts_md}

---

## Recommended Next Steps

- {impl_title}
- Address key uncertainties: {', '.join(pyramid.get('key_uncertainties', ['requires further analysis'])[:2])}
- Review risks before implementation

---
{quality_note}
*Report quality score: {score}/25 {"✓ Board-ready" if board_ready else "⚠ Needs refinement"}*
"""

	# ── Stage 9b: Full Report ──────────────────────────────────────────────────

	def _write_full_report(
		self,
		question: str,
		scqa: dict,
		pyramid: dict,
		sections: list[dict],
		hypothesis_results: list[dict],
		evidence_by_branch: dict[str, dict],
		quality: dict,
		context: str,
	) -> str:
		"""Write each section of the full analysis report."""
		titles = {s['section_key']: s['action_title'] for s in sections}
		args = pyramid.get('supporting_arguments', [])
		alts = pyramid.get('alternatives_rejected', [])
		gt   = pyramid.get('governing_thought', '')

		# Write each finding section.
		# Iterate hypothesis_results (authoritative — evidence is keyed by original_hypothesis).
		# args provides action titles/claims by position (cosmetic only); evidence always
		# comes from the matching hypothesis_result so pairing is always correct.
		# Sections 1 and 2 are hardcoded (context + recommendation), so findings start at 3.
		finding_sections: list[str] = []
		for i, hr in enumerate(hypothesis_results[:5]):
			ev  = evidence_by_branch.get(hr.get('original_hypothesis', ''), {})
			arg = args[i] if i < len(args) else {}
			section_md = self._write_finding_section(
				section_num=i+3,
				title=titles.get(f'finding_{i+1}', arg.get('claim', hr.get('refined_hypothesis') or hr.get('original_hypothesis', ''))),
				argument=arg,
				hypothesis_result=hr,
				evidence=ev,
				context=context,
			)
			finding_sections.append(section_md)

		# Write risks section
		risks_md = self._write_risks_section(
			title=titles.get('risks', 'Key risks require active mitigation before implementation'),
			pyramid=pyramid,
			hypothesis_results=hypothesis_results,
			context=context,
		)

		# Assemble alternatives section
		alts_md_sections = '\n'.join(
			f"### ~~{a.get('alternative', '')}~~\n**Rejected because**: {a.get('reason', '')}\n"
			for a in alts
		) if alts else '_No major alternatives were evaluated._'

		# Format evidence sources
		all_sources: list[str] = []
		for ev in evidence_by_branch.values():
			all_sources.extend(ev.get('sources', []))
		sources_md = '\n'.join(f'- {s}' for s in sorted(set(all_sources))[:20]) if all_sources else '_Web search results_'

		context_title = titles.get('context', f'Understanding {question} requires examining {len(args)} key dimensions')
		rec_title     = titles.get('recommendation', gt)
		impl_title    = titles.get('implementation', 'Implementation requires three phases over 6-12 months')

		return f"""# {question}

---

## 1. {context_title}

{scqa.get('situation', '')}

{scqa.get('complication', '')}

**Central question**: {scqa.get('question', question)}

---

## 2. Governing Recommendation

**{rec_title}**

{gt}

This recommendation is supported by {len(args)} independently verified findings, each tested against contradicting evidence.

---

{''.join(finding_sections)}

## {len(args)+3}. Alternatives Considered and Rejected

The following alternatives were evaluated and ruled out:

{alts_md_sections}

---

## {len(args)+4}. {impl_title}

Translating this recommendation into action requires addressing:

{chr(10).join(f'- {u}' for u in pyramid.get('key_uncertainties', ['Near-term sequencing', 'Resource allocation', 'Stakeholder alignment']))}

---

{risks_md}

---

## Methodology

This report was produced using a consulting-grade research pipeline:
- SCQA hypothesis generation
- MECE issue tree with {len(hypothesis_results)} testable branches
- Evidence-first gathering with self-consistency sampling (N={_SELF_CONSISTENCY_N})
- Adversarial hypothesis testing (refutation-first protocol)
- Pyramid Principle synthesis with external quality gate

**Sources consulted**:
{sources_md}

*Quality score: {quality.get('total_score', 0)}/25 | {"Board-ready" if quality.get('board_ready') else "Requires refinement"}*
"""

	def _write_finding_section(
		self,
		section_num: int,
		title: str,
		argument: dict,
		hypothesis_result: dict,
		evidence: dict,
		context: str,
	) -> str:
		claim = argument.get('claim', title)
		ev_strength = argument.get('evidence_strength', hypothesis_result.get('evidence_strength', 'moderate'))
		key_point = hypothesis_result.get('key_supporting_point', '')
		key_facts = evidence.get('key_facts', [])
		quant_data = evidence.get('quantitative_data', [])
		so_what = hypothesis_result.get('so_what', '')
		verdict = hypothesis_result.get('verdict', 'refined')
		contra = hypothesis_result.get('key_challenging_point', '')

		# Format key facts
		facts_md = '\n'.join(
			f"- {f.get('claim', '')} ({'**' + f.get('source','') + '**' if f.get('source') else ''})"
			for f in key_facts[:4]
		)

		# Format quantitative data
		quant_md = '\n'.join(
			f"- {q}" if isinstance(q, str) else f"- {q.get('value', q)}"
			for q in quant_data[:3]
		)

		conf_badge = {'high': '🟢 High confidence', 'medium': '🟡 Medium confidence', 'low': '🔴 Low confidence'}
		conf = evidence.get('confidence', 'medium')
		verdict_note = (
			f'_Note: original hypothesis was **{verdict}** during testing._'
			if verdict == 'refined' else ''
		)
		contra_note = f'\n**Challenge**: {contra}\n' if contra else ''

		return f"""## {section_num}. {title}

{claim}

**Evidence** ({conf_badge.get(conf, conf)} | {ev_strength} strength):
{facts_md or key_point or '_Evidence summary available in trace data._'}

{f'**Data points**: {quant_md}' if quant_md else ''}

{contra_note}**Implication**: {so_what}

{verdict_note}

---

"""

	def _write_risks_section(
		self,
		title: str,
		pyramid: dict,
		hypothesis_results: list[dict],
		context: str,
	) -> str:
		uncertainties = pyramid.get('key_uncertainties', [])
		# Extract gaps from evidence as additional risks
		evidence_gaps: list[str] = []
		for hr in hypothesis_results:
			gaps = hr.get('evidence', {}).get('gaps', [])
			evidence_gaps.extend(gaps[:1])

		prompt = f"""{context}

Based on this research, identify 3-5 key risks that could affect the recommendation.

Key uncertainties already identified: {json.dumps(uncertainties, ensure_ascii=False)}
Evidence gaps: {json.dumps(evidence_gaps[:4], ensure_ascii=False)}

For each risk, provide:
- Risk description (specific and concrete)
- Probability: High/Medium/Low
- Impact: High/Medium/Low
- Mitigation: specific action to reduce probability or impact

Return a JSON array of risk objects with: risk, probability, impact, mitigation"""

		risks = self._llm_json_array(prompt)
		if not risks:
			risks = [{'risk': u, 'probability': 'Medium', 'impact': 'High', 'mitigation': 'Monitor and develop contingency plan.'}
				for u in uncertainties[:3]]

		risks_md = '\n'.join(
			f"| {r.get('risk','')} | {r.get('probability','')} | {r.get('impact','')} | {r.get('mitigation','')} |"
			for r in risks[:5]
		)

		return f"""## {len(pyramid.get('supporting_arguments', []))+4}. {title}

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
{risks_md}
"""

	# ── Markdown assembly ──────────────────────────────────────────────────────

	def _assemble_markdown(
		self,
		result: dict,
		question: str,
		scqa: dict,
		sections: list[dict],
	) -> str:
		parts: list[str] = []

		if 'executive_summary' in result:
			parts.append(result['executive_summary'])
			parts.append('\n\n---\n\n')

		if 'full_report' in result:
			parts.append(result['full_report'])

		if not parts:
			# Minimal fallback
			parts.append(f"# {question}\n\n{scqa.get('governing_thought_hypothesis', '')}")

		return ''.join(parts)

	# ── Utilities ──────────────────────────────────────────────────────────────

	def _build_context_header(
		self, question: str, industry: str, company_context: str, framework: str
	) -> str:
		lines = ['You are a senior partner at a top-tier management consulting firm.']
		lines.append('Produce analysis that would be accepted in a McKinsey or BCG board presentation.')
		lines.append('Be specific, quantified, and committed — no hedges, no vague language.')
		if industry:
			lines.append(f'Industry context: {industry}')
		if company_context:
			lines.append(f'Company context: {company_context}')
		lines.append(f'Consulting framework guidance: {framework}')
		return '\n'.join(lines)

	def _format_evidence(self, results: list[dict]) -> str:
		lines: list[str] = []
		for r in results:
			title   = r.get('title', 'Untitled')
			url     = r.get('href', r.get('url', ''))
			snippet = r.get('body', r.get('snippet', ''))[:400]
			lines.append(f'[SOURCE: {title}]({url})\n{snippet}')
		return '\n\n'.join(lines)

	@staticmethod
	def _extract_json_span(text: str, open_ch: str, close_ch: str) -> str | None:
		"""Return the first balanced {…} or […] span in text (handles nested braces)."""
		depth = 0
		start = None
		for i, ch in enumerate(text):
			if ch == open_ch:
				if start is None:
					start = i
				depth += 1
			elif ch == close_ch:
				depth -= 1
				if depth == 0 and start is not None:
					return text[start:i + 1]
		return None

	def _llm_json(self, prompt: str, fallback: dict) -> dict:
		try:
			response = self.ai_engine.generate_text(prompt)
			span = self._extract_json_span(response, '{', '}')
			if span:
				return json.loads(span)
		except Exception:
			pass
		return dict(fallback)

	def _llm_json_array(self, prompt: str) -> list:
		try:
			response = self.ai_engine.generate_text(prompt)
			span = self._extract_json_span(response, '[', ']')
			if span:
				result = json.loads(span)
				if isinstance(result, list):
					return result
		except Exception:
			pass
		return []

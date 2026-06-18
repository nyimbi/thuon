# capabilities/rfp_section_writer.py
"""
Atomic capability: write one proposal section (executive_summary, technical_approach,
management_plan, past_performance, pricing, personnel, corporate_capabilities).
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array

_memory_store = None
_memory_lock = __import__('threading').Lock()

def _get_memory():
	global _memory_store
	if _memory_store is None:
		with _memory_lock:
			if _memory_store is None:
				try:
					from core.memory_store import get_memory_store
					_memory_store = get_memory_store()
				except Exception:
					_memory_store = None
	return _memory_store


_SECTION_INSTRUCTIONS = {
	'executive_summary': (
		'Write the Executive Summary last-in-spirit but now. Hook the evaluator in the first '
		'sentence. State the client\'s need, our unique solution, and quantified benefits. '
		'Infuse win themes. Max 2 pages. No company history boilerplate.'
	),
	'technical_approach': (
		'Write the Technical Approach addressing each SOW element. Use active future tense '
		'("We will..."). Tie every feature to a client benefit using the "so what?" test. '
		'Structure around client processes, not our org chart.'
	),
	'management_plan': (
		'Write the Management Plan covering: staffing structure, communication plan, '
		'risk management matrix, quality assurance, schedule milestones. '
		'Be specific about roles and responsibilities.'
	),
	'past_performance': (
		'Write 3-5 past performance capsules. For each: client name, problem, our solution, '
		'QUANTIFIED results, contract value, period, reference contact. '
		'Explain transferable skills if not exact match.'
	),
	'personnel': (
		'Write the Key Personnel section. For each person: tailored bio highlighting '
		'project-relevant experience. Include a highlights box mapping their experience '
		'to each RFP key personnel requirement.'
	),
	'pricing_narrative': (
		'Write the Price Narrative. Explain value per dollar, cost model assumptions, '
		'and how our approach reduces total cost of ownership. '
		'Link every cost to a technical approach element.'
	),
	'corporate_capabilities': (
		'Write the Corporate Capabilities section covering: company overview, certifications, '
		'financial stability, diversity status, and compliance. Keep factual and concise.'
	),
}


class RFPSectionWriter:
	def __init__(self, ai_engine: AIModel, memory_store=None):
		self.ai_engine = ai_engine
		self._memory = memory_store

	def _get_past_section_context(self, section_name: str, requirements: list | str) -> str:
		"""Retrieve relevant past proposal sections from memory store for context."""
		if not self._memory:
			try:
				from core.memory_store import get_memory_store
				self._memory = get_memory_store()
			except Exception:
				return ''
		query = f'{section_name} {str(requirements)[:200]}'
		episodes = self._memory.search_episodes(query, limit=3)
		if not episodes:
			return ''
		parts = [f'[Past {e["type"]}]: {e["content"][:400]}' for e in episodes]
		return '## Relevant Past Sections\n' + '\n---\n'.join(parts)

	def _log_section_to_memory(self, section_name: str, result: dict) -> None:
		if not self._memory:
			return
		try:
			content = f'Proposal section {section_name}: {result.get("content","")[:500]}'
			self._memory.log_episode('rfp_writer', 'tool_result', content, {'section': section_name, 'word_count': result.get('word_count', 0)})
		except Exception:
			pass

	def write_section(
		self,
		section_name: str,
		requirements: list | str = '',
		win_themes: list | str = '',
		company_context: str = '',
		sow_excerpt: str = '',
		page_limit: int | None = None,
	) -> dict:
		"""
		Write a single proposal section.

		Args:
			section_name:    One of: executive_summary, technical_approach, management_plan,
			                 past_performance, personnel, pricing_narrative, corporate_capabilities
			requirements:    Relevant requirements to address in this section.
			win_themes:      Win themes to weave in.
			company_context: Relevant company KB context (past perf, capabilities, personnel).
			sow_excerpt:     Relevant SOW text for this section.
			page_limit:      Target page limit if specified in RFP.

		Returns:
			{section_name, content, word_count, requirements_addressed, placeholders, notes}
		"""
		reqs_text   = json.dumps(requirements) if isinstance(requirements, list) else str(requirements)
		themes_text = json.dumps(win_themes) if isinstance(win_themes, list) else str(win_themes)
		instructions = _SECTION_INSTRUCTIONS.get(
			section_name,
			f'Write the {section_name.replace("_", " ").title()} section thoroughly.',
		)
		page_note = f' Target length: {page_limit} pages.' if page_limit else ''

		past_context = self._get_past_section_context(section_name, requirements)

		# Augment company_context with the 3 most relevant past winning sections
		episodic_context = ''
		mem = _get_memory()
		if mem is not None:
			try:
				query = f'{section_name} {sow_excerpt[:200]}'
				episodes = mem.search_episodes(query, limit=3)
				if episodes:
					parts = [
						f'[Past section — {e.get("event_type","?")}]\n{e.get("content","")[:500]}'
						for e in episodes
					]
					episodic_context = '\n\n---\n\n'.join(parts)
			except Exception:
				pass

		prompt = (
			f'You are a proposal writer. Write the {section_name.replace("_", " ").title()} '
			f'section for this RFP response.{page_note}\n\n'
			f'Writing instructions: {instructions}\n\n'
			f'Requirements to address:\n{reqs_text[:2000]}\n\n'
			f'Win themes to incorporate:\n{themes_text[:1500]}\n\n'
			f'Company context (past performance, capabilities, personnel):\n{company_context[:3000]}\n\n'
			+ (f'Relevant past sections (for reference and consistency):\n{past_context[:1500]}\n\n' if past_context else '')
			+ (f'Relevant past winning sections (for inspiration, not verbatim copy):\n{episodic_context}\n\n' if episodic_context else '')
			+ f'SOW excerpt:\n{sow_excerpt[:1500]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- section_name (str)\n'
			'- content (str): the full written section in markdown\n'
			'- word_count (int): approximate word count\n'
			'- requirements_addressed (list of str): req_ids or brief descriptions addressed\n'
			'- placeholders (list of str): items marked [PLACEHOLDER] needing human input\n'
			'- notes (str): any reviewer notes or flagged gaps'
		)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response)
		if result is not None and 'content' in result:
			self._log_section_to_memory(section_name, result)
			return result

		# Fallback: treat entire response as content
		return {
			'section_name':            section_name,
			'content':                 response,
			'word_count':              len(response.split()),
			'requirements_addressed':  [],
			'placeholders':            [],
			'notes':                   'Returned as raw text — JSON parse failed',
		}

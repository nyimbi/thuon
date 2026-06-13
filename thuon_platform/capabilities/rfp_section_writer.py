# capabilities/rfp_section_writer.py
"""
Atomic capability: write one proposal section (executive_summary, technical_approach,
management_plan, past_performance, pricing, personnel, corporate_capabilities).
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


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
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

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

		prompt = (
			f'You are a proposal writer. Write the {section_name.replace("_", " ").title()} '
			f'section for this RFP response.{page_note}\n\n'
			f'Writing instructions: {instructions}\n\n'
			f'Requirements to address:\n{reqs_text[:2000]}\n\n'
			f'Win themes to incorporate:\n{themes_text[:1500]}\n\n'
			f'Company context (past performance, capabilities, personnel):\n{company_context[:3000]}\n\n'
			f'SOW excerpt:\n{sow_excerpt[:1500]}\n\n'
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

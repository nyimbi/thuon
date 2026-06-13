# capabilities/website_section_writer.py
"""
Atomic capability: write new/updated website page content.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class WebsiteSectionWriter:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def write(
		self,
		section_name: str,
		purpose: str = '',
		current_content: str = '',
		improvements: list | str = '',
		company_context: str = '',
		target_audience: str = '',
		tone: str = 'professional-conversational',
	) -> dict:
		"""
		Rewrite or create website content for a specific page/section.

		Returns:
			{new_content, change_summary, seo_keywords, word_count}
		"""
		improvements_text = (
			json.dumps(improvements) if isinstance(improvements, list) else str(improvements)
		)

		prompt = (
			f'You are a professional copywriter writing website content.\n\n'
			f'Page/section: {section_name}\n'
			f'Purpose: {purpose or "Communicate value to potential clients"}\n'
			f'Target audience: {target_audience or "Business decision makers"}\n'
			f'Tone: {tone}\n\n'
			f'CURRENT CONTENT (to improve upon):\n{current_content[:2000]}\n\n'
			f'IMPROVEMENTS TO MAKE:\n{improvements_text[:1500]}\n\n'
			f'COMPANY CONTEXT (capabilities, differentiators, examples):\n{company_context[:2000]}\n\n'
			'Write compelling, conversion-focused website copy. Lead with benefits, not features. '
			'Be specific. Avoid jargon and "we are pleased to" language.\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- new_content (str): the rewritten page content in markdown\n'
			'- change_summary (str): what changed and why\n'
			'- seo_keywords (list of str): keywords naturally incorporated\n'
			'- word_count (int)\n'
			'- headline (str): proposed H1 for this page\n'
			'- subheadline (str): supporting H2 or tagline'
		)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response)
		if result is not None and 'new_content' in result:
			return result

		return {
			'new_content':    response,
			'change_summary': 'Content rewritten',
			'seo_keywords':   [],
			'word_count':     len(response.split()),
			'headline':       '',
			'subheadline':    '',
		}

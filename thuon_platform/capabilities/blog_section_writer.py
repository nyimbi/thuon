# capabilities/blog_section_writer.py
"""
Atomic capability: write one or more blog post sections from an outline.
Can write the full post when given the full outline.
"""

import json
import re
import time
from pathlib import Path
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array

from core.bundle import writable_data_dir as _wdd
_OUTPUT_DIR = _wdd() / 'blog'


class BlogSectionWriter:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def write(
		self,
		heading: str,
		subheadings: list | str = '',
		context: str = '',
		tone: str = 'authoritative-friendly',
		company_context: str = '',
		seo_keyword: str = '',
		word_target: int = 300,
		is_full_post: bool = False,
		outline: list | str = '',
	) -> dict:
		"""
		Write a blog section or a full post.

		Args:
			heading:         The section heading to write.
			subheadings:     List of H3 subheadings to cover.
			context:         Notes / key points for this section.
			tone:            Writing tone.
			company_context: Company context for incorporating expertise/examples.
			seo_keyword:     Primary keyword to include naturally.
			word_target:     Target word count.
			is_full_post:    If True, write the entire post from the outline.
			outline:         Full outline (used when is_full_post=True).

		Returns:
			{content, word_count, sections_written, output_path (if saved)}
		"""
		subs_text    = json.dumps(subheadings) if isinstance(subheadings, list) else str(subheadings)
		outline_text = json.dumps(outline)      if isinstance(outline, list)      else str(outline)

		if is_full_post:
			prompt = (
				f'Write a complete, publication-ready blog post in markdown.\n\n'
				f'Outline:\n{outline_text[:3000]}\n\n'
				f'Tone: {tone}\n'
				f'Primary keyword to include naturally: {seo_keyword}\n'
				f'Company context / examples to draw from:\n{company_context[:1000]}\n\n'
				f'Write the full post. Start with the H1 title. Use proper markdown headings. '
				f'Each section should flow naturally, no robotic structure. '
				f'Return ONLY a valid JSON object with:\n'
				'- content (str): complete blog post in markdown\n'
				'- word_count (int)\n'
				'- sections_written (list of str): heading names written'
			)
		else:
			prompt = (
				f'Write the "{heading}" section of a blog post.\n\n'
				f'Subheadings to cover: {subs_text}\n'
				f'Notes / key points: {context[:800]}\n'
				f'Tone: {tone}\n'
				f'Primary keyword to weave in naturally: {seo_keyword}\n'
				f'Company examples / context: {company_context[:600]}\n'
				f'Target: ~{word_target} words\n\n'
				'Write this section in clean markdown. No meta-commentary.\n'
				'Return ONLY a valid JSON object with:\n'
				'- content (str): section content in markdown\n'
				'- word_count (int)\n'
				'- sections_written (list of str): [heading name]'
			)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response)
		if result is not None and 'content' in result:
			return result

		return {
			'content':          response,
			'word_count':       len(response.split()),
			'sections_written': [heading],
		}

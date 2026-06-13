# capabilities/blog_outliner.py
"""
Atomic capability: create a detailed structured outline for a blog post.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class BlogOutliner:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def outline(
		self,
		topic: str,
		audience: str = '',
		target_length: int = 1200,
		seo_keyword: str = '',
		company_context: str = '',
		tone: str = 'authoritative-friendly',
	) -> dict:
		"""
		Create a structured blog post outline.

		Returns:
			{outline, meta_description, seo_title, estimated_word_count,
			 internal_links_suggested, cta_suggestion}
		"""
		prompt = (
			f'You are a content strategist creating a detailed blog outline.\n\n'
			f'Topic: {topic}\n'
			f'Audience: {audience or "business professionals"}\n'
			f'Target length: ~{target_length} words\n'
			f'Primary keyword: {seo_keyword or topic}\n'
			f'Tone: {tone}\n'
			f'Company context: {company_context[:500] or "Not provided"}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- outline (list): each item with:\n'
			'  - heading (str): H2 heading\n'
			'  - subheadings (list of str): H3 subheadings under this section\n'
			'  - notes (str): key points, stats, examples to include\n'
			'  - word_target (int): target word count for this section\n'
			'- meta_description (str): 150-160 character meta description\n'
			'- seo_title (str): 50-60 character SEO-optimized title\n'
			'- estimated_word_count (int): total estimated words\n'
			'- internal_links_suggested (list of str): topics to link to internally\n'
			'- cta_suggestion (str): call-to-action for end of post'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'outline':                   [],
			'meta_description':          '',
			'seo_title':                 topic,
			'estimated_word_count':      target_length,
			'internal_links_suggested':  [],
			'cta_suggestion':            '',
		}

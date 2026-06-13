# capabilities/website_seo_optimizer.py
"""
Atomic capability: SEO-optimize website page content.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class WebsiteSEOOptimizer:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def optimize(
		self,
		content: str,
		page_path: str = '/',
		target_keywords: list | str = '',
		site_name: str = '',
	) -> dict:
		"""
		Apply SEO optimization to website page content.

		Returns:
			{optimized_content, title_tag, meta_description,
			 heading_structure, schema_markup_suggestion, canonical_url}
		"""
		kw_text = json.dumps(target_keywords) if isinstance(target_keywords, list) else str(target_keywords)

		prompt = (
			f'You are an SEO specialist optimizing a website page.\n\n'
			f'Page: {page_path}\n'
			f'Site: {site_name or "the website"}\n'
			f'Target keywords: {kw_text}\n\n'
			f'PAGE CONTENT:\n{content[:5000]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- optimized_content (str): SEO-improved content in markdown\n'
			'- title_tag (str): 50-60 char title tag with primary keyword\n'
			'- meta_description (str): 150-160 char meta description\n'
			'- heading_structure (list): [{level: h1|h2|h3, text: ...}] list of headings\n'
			'- schema_markup_suggestion (str): recommended schema type e.g. "Organization", "Service"\n'
			'- canonical_url (str): canonical URL path\n'
			'- og_title (str): Open Graph title\n'
			'- og_description (str): Open Graph description'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'optimized_content':          content,
			'title_tag':                  '',
			'meta_description':           '',
			'heading_structure':          [],
			'schema_markup_suggestion':   'Organization',
			'canonical_url':              page_path,
			'og_title':                   '',
			'og_description':             '',
		}

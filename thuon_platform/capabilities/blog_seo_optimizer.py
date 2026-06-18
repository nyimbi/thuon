# capabilities/blog_seo_optimizer.py
"""
Atomic capability: SEO-optimize a complete blog post and save to disk.
"""

import json
import re
import time
from pathlib import Path
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array

from core.bundle import writable_data_dir as _wdd
_OUTPUT_DIR = _wdd() / 'blog'


class BlogSEOOptimizer:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def optimize(
		self,
		full_content: str,
		target_keyword: str = '',
		meta_description: str = '',
		tone: str = '',
		save_to_disk: bool = True,
		slug: str = '',
	) -> dict:
		"""
		SEO-optimize a complete blog post and write to data/blog/.

		Returns:
			{optimized_content, seo_title, meta_description, keyword_density,
			 improvements, output_path, word_count}
		"""
		prompt = (
			'You are an SEO specialist and editor. Optimize this blog post for search and readability.\n\n'
			f'Primary keyword: {target_keyword}\n'
			f'Current meta description: {meta_description}\n\n'
			f'BLOG POST:\n{full_content[:8000]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- optimized_content (str): improved post in markdown with keyword naturally included\n'
			'- seo_title (str): 50-60 char SEO title with keyword near front\n'
			'- meta_description (str): 150-160 char compelling description\n'
			'- keyword_density (float): estimated keyword density as decimal e.g. 0.012\n'
			'- improvements (list of str): changes made\n'
			'- slug (str): URL-friendly slug for this post\n'
			'- word_count (int): final word count\n'
			'- reading_time_min (int): estimated reading time'
		)

		response = self.ai_engine.generate_text(prompt)
		result = {}
		try:
			result = extract_json(response)
		except Exception:
			result = {
				'optimized_content': full_content,
				'seo_title':         target_keyword,
				'meta_description':  meta_description,
				'keyword_density':   0.0,
				'improvements':      [],
				'slug':              slug or 'blog-post',
				'word_count':        len(full_content.split()),
				'reading_time_min':  max(1, len(full_content.split()) // 200),
			}

		# Save to disk
		output_path = ''
		if save_to_disk:
			final_slug = result.get('slug') or slug or f'post-{time.strftime("%Y%m%d-%H%M%S")}'
			final_slug = re.sub(r'[^\w\-]', '-', final_slug.lower())[:80]
			_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
			out_path = _OUTPUT_DIR / f'{final_slug}.md'
			content  = result.get('optimized_content', full_content)
			frontmatter = (
				f'---\ntitle: "{result.get("seo_title", target_keyword)}"\n'
				f'description: "{result.get("meta_description", meta_description)}"\n'
				f'keywords: [{target_keyword}]\n'
				f'date: {time.strftime("%Y-%m-%d")}\n---\n\n'
			)
			out_path.write_text(frontmatter + content, encoding='utf-8')
			output_path = str(out_path)
			result['output_path'] = output_path

			# Open in neditor
			try:
				from core.neditor_bridge import get_neditor_bridge
				get_neditor_bridge().open(output_path, {'type': 'blog_post'})
			except Exception:
				pass

			# Copy to Obsidian
			try:
				from core.obsidian_bridge import get_obsidian_bridge
				get_obsidian_bridge().write_blog(
					result.get('seo_title', target_keyword),
					frontmatter + content,
				)
			except Exception:
				pass

		return result

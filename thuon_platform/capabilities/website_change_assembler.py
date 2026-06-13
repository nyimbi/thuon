# capabilities/website_change_assembler.py
"""
Atomic capability: write finalized website page content to the static site repo.
Does NOT git push — human reviews and commits manually.
"""

import json
import re
import time
from pathlib import Path
from core.ai_engine import AIModel
from core.settings_manager import get_settings


class WebsiteChangeAssembler:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def assemble(
		self,
		page_path: str = '/',
		optimized_content: str = '',
		title_tag: str = '',
		meta_description: str = '',
		site_repo_path: str = '',
		additional_pages: dict | str = '',
	) -> dict:
		"""
		Write generated page content to the local static site repo directory.

		Args:
			page_path:         URL path e.g. "/" or "/about" or "/services".
			optimized_content: Markdown content for this page.
			title_tag:         SEO title tag.
			meta_description:  SEO meta description.
			site_repo_path:    Override for site repo location from config.
			additional_pages:  Dict {path: content} for additional pages in one run.

		Returns:
			{files_written, change_summary, git_commit_message, repo_path}
		"""
		settings = get_settings()
		repo = Path(
			site_repo_path
			or settings.get_setting('website.site_repo_path', '')
		)

		files_written = []
		errors        = []

		pages_to_write: dict[str, dict] = {}
		if optimized_content:
			pages_to_write[page_path] = {
				'content':          optimized_content,
				'title_tag':        title_tag,
				'meta_description': meta_description,
			}
		if additional_pages:
			extra = json.loads(additional_pages) if isinstance(additional_pages, str) else additional_pages
			if isinstance(extra, dict):
				pages_to_write.update(extra)

		for path, page_data in pages_to_write.items():
			try:
				content = page_data.get('content', '') if isinstance(page_data, dict) else str(page_data)
				t_tag   = page_data.get('title_tag', title_tag) if isinstance(page_data, dict) else ''
				m_desc  = page_data.get('meta_description', meta_description) if isinstance(page_data, dict) else ''

				frontmatter = ''
				if t_tag or m_desc:
					frontmatter = (
						f'---\ntitle: "{t_tag}"\ndescription: "{m_desc}"\n'
						f'date: {time.strftime("%Y-%m-%d")}\n---\n\n'
					)

				# Determine file path inside repo
				if repo.exists():
					if path in ('/', ''):
						out_file = repo / 'index.md'
					else:
						clean = path.strip('/').replace('/', '-')
						out_file = repo / f'{clean}.md'
					out_file.write_text(frontmatter + content, encoding='utf-8')
					files_written.append(str(out_file))
				else:
					# No repo configured — output to thuon data dir
					from pathlib import Path as _P
					tmp_dir = _P(__file__).parent.parent / 'data' / 'website_output'
					tmp_dir.mkdir(parents=True, exist_ok=True)
					clean    = (path.strip('/') or 'index').replace('/', '-')
					out_file = tmp_dir / f'{clean}.md'
					out_file.write_text(frontmatter + content, encoding='utf-8')
					files_written.append(str(out_file))

			except Exception as exc:
				errors.append(f'{path}: {exc}')

		# Generate commit message
		changed = ', '.join(
			p.strip('/') or 'homepage' for p in pages_to_write.keys()
		)
		commit_msg = (
			f'chore(website): refresh content for {changed} — {time.strftime("%Y-%m-%d")}'
		)

		return {
			'files_written':      files_written,
			'change_summary':     f'Updated {len(files_written)} page(s). Errors: {errors}',
			'git_commit_message': commit_msg,
			'repo_path':          str(repo),
		}

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

try:
	import requests
except ImportError:
	requests = None

from core.settings_manager import get_settings

_NS = '{http://www.w3.org/2005/Atom}'
_SORT_MAP = {'relevance': 'relevance', 'date': 'submittedDate', 'citations': 'relevance'}


class ArxivSearcher:

	def search(self, query: str, max_results: int = 10, sort_by: str = 'relevance', categories: list = []) -> dict[str, Any]:
		try:
			if requests is None:
				return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}

			settings = get_settings()
			base_url = settings.get_setting('tools.arxiv_base_url', 'https://export.arxiv.org/api/query')

			sort_key = _SORT_MAP.get(sort_by, 'relevance')

			if categories:
				cat_filter = ' OR '.join(f'cat:{c}' for c in categories)
				search_query = f'({cat_filter}) AND all:{query}'
			else:
				search_query = f'all:{query}'

			params = {
				'search_query': search_query,
				'start': 0,
				'max_results': max_results,
				'sortBy': sort_key,
				'sortOrder': 'descending',
			}

			resp = requests.get(base_url, params=params, timeout=30)
			resp.raise_for_status()

			root = ET.fromstring(resp.text)

			papers = []
			for entry in root.findall(f'{_NS}entry'):
				title_el = entry.find(f'{_NS}title')
				title = title_el.text.strip() if title_el is not None else ''

				authors = [
					a.find(f'{_NS}name').text.strip()
					for a in entry.findall(f'{_NS}author')
					if a.find(f'{_NS}name') is not None
				]

				summary_el = entry.find(f'{_NS}summary')
				abstract = summary_el.text.strip() if summary_el is not None else ''

				id_el = entry.find(f'{_NS}id')
				url = id_el.text.strip() if id_el is not None else ''
				pdf_url = url.replace('/abs/', '/pdf/')

				published_el = entry.find(f'{_NS}published')
				published = published_el.text.strip() if published_el is not None else ''

				# arxiv uses opensearch + atom; category tags live in <category term="...">
				cats = [
					t.get('term', '')
					for t in entry.findall(f'{_NS}category')
					if t.get('term')
				]

				papers.append({
					'title': title,
					'authors': authors,
					'abstract': abstract,
					'url': url,
					'pdf_url': pdf_url,
					'published': published,
					'categories': cats,
				})

			return {
				'status': 'success',
				'query': query,
				'papers': papers,
				'count': len(papers),
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

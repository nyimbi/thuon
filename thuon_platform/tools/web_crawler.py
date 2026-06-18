from collections import deque
from urllib.parse import urljoin, urlparse
from typing import Any

try:
	import requests
except ImportError:
	requests = None

try:
	from bs4 import BeautifulSoup
except ImportError:
	BeautifulSoup = None

from core.settings_manager import get_settings


class WebCrawler:

	def crawl(self, seed_url: str, max_pages: int = 5, same_domain: bool = True) -> dict[str, Any]:
		try:
			if requests is None:
				return {'status': 'error', 'error': 'Package requests not installed. Run: uv add requests'}
			if BeautifulSoup is None:
				return {'status': 'error', 'error': 'Package beautifulsoup4 not installed. Run: uv add beautifulsoup4'}

			settings = get_settings()
			timeout = settings.get_setting('tools.web_crawler.timeout', 15)

			seed_domain = urlparse(seed_url).netloc
			queue: deque[str] = deque([seed_url])
			visited: set[str] = set()
			pages: list[dict[str, Any]] = []
			total_links_found = 0

			while queue and len(pages) < max_pages:
				url = queue.popleft()
				if url in visited:
					continue
				visited.add(url)

				try:
					resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'ThuonCrawler/1.0'})
					resp.raise_for_status()
				except Exception:
					# skip unreachable pages, continue crawl
					continue

				soup = BeautifulSoup(resp.text, 'html.parser')

				title_tag = soup.find('title')
				title = title_tag.get_text(strip=True) if title_tag else ''

				for tag in soup(['script', 'style', 'noscript', 'head']):
					tag.decompose()
				text = soup.get_text(separator=' ', strip=True)
				word_count = len(text.split())

				pages.append({'url': url, 'title': title, 'text': text, 'word_count': word_count})

				# collect links for BFS
				for a in soup.find_all('a', href=True):
					href = a['href'].strip()
					if not href or href.startswith('#') or href.startswith('javascript:'):
						continue
					abs_url = urljoin(url, href)
					parsed = urlparse(abs_url)
					# only http/https
					if parsed.scheme not in ('http', 'https'):
						continue
					if same_domain and parsed.netloc != seed_domain:
						continue
					total_links_found += 1
					if abs_url not in visited:
						queue.append(abs_url)

			return {
				'status': 'success',
				'seed_url': seed_url,
				'pages': pages,
				'total_pages': len(pages),
				'links_found': total_links_found,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

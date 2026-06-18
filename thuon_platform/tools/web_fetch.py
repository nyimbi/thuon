import re
from typing import Any

import trafilatura
import requests
from bs4 import BeautifulSoup


class WebFetcher:

	def fetch(self, url: str, extract_text: bool = True, selector: str = '') -> dict[str, Any]:
		try:
			html = trafilatura.fetch_url(url)

			# fallback to requests if trafilatura.fetch_url returns nothing
			if not html:
				resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
				resp.raise_for_status()
				html = resp.text

			if not html:
				return {'status': 'error', 'error': f'could not fetch content from {url}'}

			soup = BeautifulSoup(html, 'html.parser')

			title_tag = soup.find('title')
			title = title_tag.get_text(strip=True) if title_tag else ''

			if selector:
				nodes = soup.select(selector)
				text = '\n'.join(n.get_text(separator=' ', strip=True) for n in nodes)
			elif extract_text:
				extracted = trafilatura.extract(html, include_links=True)
				text = extracted or soup.get_text(separator=' ', strip=True)
			else:
				text = html

			# collect all href links from the page
			links: list[str] = [
				a['href'] for a in soup.find_all('a', href=True)
				if a['href'].startswith('http')
			]

			word_count = len(re.findall(r'\S+', text)) if text else 0

			return {
				'status': 'success',
				'url': url,
				'title': title,
				'text': text,
				'word_count': word_count,
				'links': links,
			}

		except Exception as e:
			return {'status': 'error', 'error': str(e)}

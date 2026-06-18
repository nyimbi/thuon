from datetime import datetime, timedelta, timezone
from typing import Any

try:
	from ddgs import DDGS
except ImportError:
	DDGS = None

from core.settings_manager import get_settings


class NewsSearcher:

	def search(self, query: str, max_results: int | None = None, days_back: int | None = None) -> dict:
		try:
			if DDGS is None:
				return {'status': 'error', 'error': 'Package ddgs not installed. Run: uv add ddgs'}

			settings = get_settings()
			max_results = max_results if max_results is not None else settings.get_setting('news.max_results', 10)
			days_back = days_back if days_back is not None else settings.get_setting('news.days_back', 7)
			cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

			raw = list(DDGS().news(query, max_results=max_results))

			articles: list[dict[str, Any]] = []
			for r in raw:
				date_str = r.get('date', '')
				# filter by date if parseable
				if date_str:
					try:
						pub = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
						if pub.tzinfo is None:
							pub = pub.replace(tzinfo=timezone.utc)
						if pub < cutoff:
							continue
					except ValueError:
						pass

				articles.append({
					'title': r.get('title', ''),
					'url': r.get('url', ''),
					'summary': r.get('body', ''),
					'published': date_str,
					'source': r.get('source', ''),
				})

			return {
				'status': 'success',
				'query': query,
				'articles': articles,
				'count': len(articles),
			}
		except Exception as e:
			return {'status': 'error', 'error': str(e)}

# capabilities/daily_brief.py
"""
Daily/weekly brief aggregator.
Pulls news, knowledge-base highlights, and market signals into a structured digest.
"""

from __future__ import annotations
import json
import re
from datetime import datetime


class DailyBrief:
	def __init__(
		self,
		ai_engine,
		search_engine=None,
		knowledge_pipeline=None,
	):
		self.ai_engine         = ai_engine
		self.search_engine     = search_engine
		self.knowledge_pipeline = knowledge_pipeline  # KnowledgeIngestionPipeline

	def generate(
		self,
		topics: list[str] | None = None,
		focus_areas: list[str] | None = None,
		include_sections: list[str] | None = None,
	) -> dict:
		"""
		Generate a daily brief.

		Args:
			topics:           News/search topics e.g. ['AI', 'Kenya business']
			focus_areas:      Knowledge-base query areas
			include_sections: Subset of ['news_summary','knowledge_highlights','market_pulse','action_items']
		"""
		sections_to_run = set(include_sections or [
			'news_summary', 'knowledge_highlights', 'market_pulse', 'action_items',
		])
		topics      = topics      or ['technology', 'business', 'AI', 'Africa']
		focus_areas = focus_areas or topics

		brief: dict = {
			'generated_at': datetime.utcnow().isoformat(),
			'date':         datetime.utcnow().strftime('%A, %d %B %Y'),
			'topics':       topics,
			'sections':     {},
		}

		if 'news_summary' in sections_to_run:
			brief['sections']['news_summary'] = self._news_summary(topics)

		if 'knowledge_highlights' in sections_to_run:
			brief['sections']['knowledge_highlights'] = self._knowledge_highlights(focus_areas)

		if 'market_pulse' in sections_to_run:
			brief['sections']['market_pulse'] = self._market_pulse(topics)

		if 'action_items' in sections_to_run:
			brief['sections']['action_items'] = self._action_items(brief['sections'])

		brief['formatted_text'] = self._format(brief)
		brief['word_count']     = len(brief['formatted_text'].split())
		brief['status']         = 'ok'
		return brief

	def _news_summary(self, topics: list[str]) -> dict:
		articles: list[dict] = []
		if self.search_engine:
			for topic in topics[:3]:
				try:
					results = self.search_engine.search(f'{topic} news today 2025', num_results=5)
					for r in results[:3]:
						articles.append({
							'title':   r.get('title', ''),
							'snippet': r.get('body', r.get('snippet', ''))[:200],
							'url':     r.get('href', r.get('url', '')),
							'topic':   topic,
						})
				except Exception:
					continue

		if not articles:
			return {'items': [], 'summary': 'No news data available.', 'article_count': 0}

		headlines = '\n'.join(f"- {a['title']}: {a['snippet']}" for a in articles[:9])
		prompt = (
			'Summarize these news headlines into 3-5 key insights for a business executive. '
			'Be concise and highlight actionable implications.\n\n'
			f'Headlines:\n{headlines}\n\nSummary (bullet points):'
		)
		summary = self.ai_engine.generate_text(prompt)
		return {'items': articles, 'summary': summary.strip(), 'article_count': len(articles)}

	def _knowledge_highlights(self, focus_areas: list[str]) -> dict:
		if not self.knowledge_pipeline or self.knowledge_pipeline.chunk_count == 0:
			return {'highlights': [], 'note': 'No knowledge base content indexed.'}

		highlights: list[dict] = []
		for area in focus_areas[:3]:
			chunks = self.knowledge_pipeline.search(area, top_k=2)
			for c in chunks:
				if c['score'] > 0.1:
					highlights.append({
						'area':    area,
						'source':  c['source'],
						'excerpt': c['text'][:200],
						'score':   round(c['score'], 3),
					})

		return {
			'highlights': highlights[:6],
			'kb_size': {
				'chunks':  self.knowledge_pipeline.chunk_count,
				'sources': self.knowledge_pipeline.source_count,
			},
		}

	def _market_pulse(self, topics: list[str]) -> dict:
		if not self.search_engine:
			return {'signals': [], 'note': 'Search engine not available.'}

		signals: list[dict] = []
		for topic in topics[:2]:
			try:
				results = self.search_engine.search(
					f'{topic} market trend analysis 2025', num_results=3
				)
				for r in results[:2]:
					signals.append({
						'topic':   topic,
						'title':   r.get('title', ''),
						'insight': r.get('body', r.get('snippet', ''))[:200],
					})
			except Exception:
				continue

		return {'signals': signals}

	def _action_items(self, sections: dict) -> dict:
		news_summary = sections.get('news_summary', {}).get('summary', '')
		if not news_summary:
			return {'items': [], 'note': 'No content to derive actions from.'}

		prompt = (
			'Based on this news summary, suggest 3-5 specific actionable items '
			'for a business professional. Be concrete (who, what, when).\n\n'
			f'News: {news_summary[:1000]}\n\n'
			'Return a JSON list of action item strings:'
		)
		raw = self.ai_engine.generate_text(prompt)
		try:
			m = re.search(r'\[.*\]', raw, re.DOTALL)
			items: list = json.loads(m.group()) if m else [raw.strip()]
		except Exception:
			items = [raw.strip()]
		return {'items': items[:5]}

	def _format(self, brief: dict) -> str:
		lines = [f"# Daily Brief — {brief['date']}", '']
		sections = brief.get('sections', {})

		if 'news_summary' in sections:
			lines += ['## News Summary', sections['news_summary'].get('summary', ''), '']

		if 'knowledge_highlights' in sections:
			hl = sections['knowledge_highlights'].get('highlights', [])
			if hl:
				lines.append('## Knowledge Highlights')
				for h in hl[:4]:
					lines.append(f"- **{h['area']}** ({h['source']}): {h['excerpt']}")
				lines.append('')

		if 'market_pulse' in sections:
			signals = sections['market_pulse'].get('signals', [])
			if signals:
				lines.append('## Market Pulse')
				for s in signals[:4]:
					lines.append(f"- **{s['topic']}**: {s['insight']}")
				lines.append('')

		if 'action_items' in sections:
			items = sections['action_items'].get('items', [])
			if items:
				lines.append('## Action Items')
				for item in items:
					lines.append(f'- {item}')
				lines.append('')

		return '\n'.join(lines)

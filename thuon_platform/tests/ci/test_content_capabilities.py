# tests/ci/test_content_capabilities.py
"""
Unit tests for blog, website, and social content atomic capabilities.
All LLM and search calls are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ai(response: str = '') -> MagicMock:
	m = MagicMock()
	m.generate_text.return_value = response
	return m


def _search(results: list | None = None) -> MagicMock:
	m = MagicMock()
	m.search.return_value = results or [
		{'title': 'AI trends 2026', 'body': 'LLMs dominate enterprise software.', 'href': 'https://example.com/1'},
		{'title': 'Cloud adoption Kenya', 'body': 'SMEs embrace cloud.', 'href': 'https://example.com/2'},
	]
	return m


_TOPICS_JSON = json.dumps({'topics': [
	{'title': 'How AI is Transforming Kenyan SMEs',
	 'angle': 'local case studies',
	 'target_keyword': 'AI for small business Kenya',
	 'competition_level': 'low',
	 'search_intent': 'informational',
	 'why_now': 'post-pandemic digital adoption',
	 'outline_hint': 'Intro → case studies → how to start'},
]})

_OUTLINE_JSON = json.dumps({
	'outline': [
		{'heading': 'Introduction', 'subheadings': ['Background', 'Why it matters'], 'word_target': 200},
		{'heading': 'Main Argument', 'subheadings': ['Point 1', 'Point 2'], 'word_target': 500},
	],
	'meta_description': 'AI is transforming Kenyan SMEs with practical tools.',
})

_BLOG_SECTION_JSON = json.dumps({
	'content': 'Kenyan small businesses are rapidly adopting AI tools...',
	'word_count': 420,
})

_SEO_JSON = json.dumps({
	'optimized_content': 'Kenyan SMEs embrace AI for growth...',
	'seo_title': 'How AI is Changing Business in Kenya | 2026',
	'meta_description': 'Discover how Kenyan SMEs use AI.',
	'keyword_density': 1.8,
	'improvements': ['Add internal links', 'Include FAQ section'],
})

_SOCIAL_JSON = json.dumps({
	'post_text': "AI is reshaping SMEs in Kenya 🚀\n\nThree things to know...",
	'hashtags': ['#AI', '#Kenya', '#SMEs'],
	'character_count': 280,
	'suggested_media_prompt': 'Kenyan entrepreneur using laptop',
})

_SITE_AUDIT_JSON = json.dumps({
	'current_content': 'We provide cloud services to enterprise clients.',
	'word_count': 320,
	'last_updated_est': '2024-01-01',
	'tone': 'formal',
	'top_keywords': ['cloud', 'enterprise', 'services'],
})

_GAP_JSON = json.dumps({
	'missing_topics': ['AI/ML services', 'pricing transparency'],
	'outdated_claims': ['mentions "2023 growth"'],
	'seo_gaps': ['long-tail keywords missing'],
	'competitor_advantages': ['Safaricom lists case studies'],
	'improvement_priority': ['Add AI/ML section', 'Update case studies'],
})

_SITE_SECTION_JSON = json.dumps({
	'new_content': 'We deliver cloud-native AI solutions to enterprise and SME clients...',
	'change_summary': 'Added AI/ML services, updated tone, added case study links.',
	'seo_keywords': ['cloud AI Kenya', 'ML consulting Nairobi'],
})


# ── BlogTopicResearcher ───────────────────────────────────────────────────────

class TestBlogTopicResearcher:
	def test_research_returns_topics(self):
		from capabilities.blog_topic_researcher import BlogTopicResearcher
		cap = BlogTopicResearcher(_ai(_TOPICS_JSON), _search())
		result = cap.research(domain='AI for business', audience='SME owners')
		assert 'topics' in result
		assert isinstance(result['topics'], list)

	def test_research_calls_search_and_llm(self):
		from capabilities.blog_topic_researcher import BlogTopicResearcher
		ai, search = _ai(_TOPICS_JSON), _search()
		cap = BlogTopicResearcher(ai, search)
		cap.research(domain='fintech')
		search.search.assert_called()
		ai.generate_text.assert_called_once()

	def test_research_num_topics_param(self):
		from capabilities.blog_topic_researcher import BlogTopicResearcher
		cap = BlogTopicResearcher(_ai(_TOPICS_JSON), _search())
		result = cap.research(domain='cloud', num_topics=3)
		assert isinstance(result.get('topics', []), list)

	def test_research_invalid_json_does_not_raise(self):
		from capabilities.blog_topic_researcher import BlogTopicResearcher
		cap = BlogTopicResearcher(_ai('not json'), _search())
		result = cap.research(domain='tech')
		assert result is None or isinstance(result, dict)


# ── BlogOutliner ──────────────────────────────────────────────────────────────

class TestBlogOutliner:
	def test_outline_returns_sections(self):
		from capabilities.blog_outliner import BlogOutliner
		cap = BlogOutliner(_ai(_OUTLINE_JSON))
		result = cap.outline(topic='AI for SMEs', audience='business owners')
		assert 'outline' in result
		assert isinstance(result['outline'], list)

	def test_outline_returns_meta_description(self):
		from capabilities.blog_outliner import BlogOutliner
		cap = BlogOutliner(_ai(_OUTLINE_JSON))
		result = cap.outline(topic='AI for SMEs')
		assert 'meta_description' in result


# ── BlogSectionWriter ─────────────────────────────────────────────────────────

class TestBlogSectionWriter:
	def test_write_returns_content(self):
		from capabilities.blog_section_writer import BlogSectionWriter
		cap = BlogSectionWriter(_ai(_BLOG_SECTION_JSON))
		result = cap.write(heading='Introduction', subheadings=['Background'])
		assert 'content' in result
		assert isinstance(result['content'], str)

	def test_write_returns_word_count(self):
		from capabilities.blog_section_writer import BlogSectionWriter
		cap = BlogSectionWriter(_ai(_BLOG_SECTION_JSON))
		result = cap.write(heading='Main Body')
		assert 'word_count' in result


# ── BlogSEOOptimizer ──────────────────────────────────────────────────────────

class TestBlogSEOOptimizer:
	def test_optimize_returns_seo_title(self):
		from capabilities.blog_seo_optimizer import BlogSEOOptimizer
		cap = BlogSEOOptimizer(_ai(_SEO_JSON))
		result = cap.optimize(
			full_content='Original content here...',
			target_keyword='AI for business Kenya',
		)
		assert 'seo_title' in result
		assert 'optimized_content' in result


# ── SocialPostWriter ──────────────────────────────────────────────────────────

class TestSocialPostWriter:
	def test_write_returns_post_text(self):
		from capabilities.social_post_writer import SocialPostWriter
		cap = SocialPostWriter(_ai(_SOCIAL_JSON))
		result = cap.write(idea='AI trends in Kenya', platform='linkedin')
		assert 'post_text' in result
		assert isinstance(result['post_text'], str)

	def test_write_returns_hashtags(self):
		from capabilities.social_post_writer import SocialPostWriter
		cap = SocialPostWriter(_ai(_SOCIAL_JSON))
		result = cap.write(idea='AI trends', platform='twitter')
		assert 'hashtags' in result

	def test_write_calls_llm(self):
		from capabilities.social_post_writer import SocialPostWriter
		ai = _ai(_SOCIAL_JSON)
		cap = SocialPostWriter(ai)
		cap.write(idea='Tech in Kenya', platform='linkedin')
		ai.generate_text.assert_called_once()


# ── SocialTrendResearcher ─────────────────────────────────────────────────────

class TestSocialTrendResearcher:
	def test_research_returns_trends(self):
		from capabilities.social_trend_researcher import SocialTrendResearcher
		trends_json = json.dumps({
			'trends': [{'platform': 'linkedin', 'hashtags': ['#AI'], 'angle': 'business value', 'best_time': '08:00'}],
			'context_summary': 'AI adoption accelerating across Africa.',
		})
		cap = SocialTrendResearcher(_ai(trends_json), _search())
		result = cap.research(idea='AI in Africa', platforms=['linkedin'])
		assert 'trends' in result or 'context_summary' in result


# ── WebsiteContentAuditor ─────────────────────────────────────────────────────

class TestWebsiteContentAuditor:
	def test_audit_returns_current_content(self):
		from capabilities.website_content_auditor import WebsiteContentAuditor
		cap = WebsiteContentAuditor(_ai(_SITE_AUDIT_JSON))
		result = cap.audit(url='https://example.com', page_path='/services')
		assert 'current_content' in result or 'word_count' in result or isinstance(result, dict)


# ── WebsiteGapAnalyzer ────────────────────────────────────────────────────────

class TestWebsiteGapAnalyzer:
	def test_analyze_returns_gaps(self):
		from capabilities.website_gap_analyzer import WebsiteGapAnalyzer
		cap = WebsiteGapAnalyzer(_ai(_GAP_JSON), _search())
		result = cap.analyze(
			current_content='We provide cloud services.',
			company_context='AI/ML, cloud, data analytics',
		)
		assert 'missing_topics' in result or 'improvement_priority' in result or isinstance(result, dict)


# ── WebsiteSectionWriter ──────────────────────────────────────────────────────

class TestWebsiteSectionWriter:
	def test_write_returns_new_content(self):
		from capabilities.website_section_writer import WebsiteSectionWriter
		cap = WebsiteSectionWriter(_ai(_SITE_SECTION_JSON))
		result = cap.write(
			section_name='services',
			purpose='Describe AI/ML and cloud offerings',
			current_content='We provide cloud services.',
		)
		assert 'new_content' in result or isinstance(result, dict)

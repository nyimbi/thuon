# capabilities/social_post_writer.py
"""
Atomic capability: write platform-specific social media posts for a given idea.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array

_PLATFORM_RULES = {
	'linkedin': (
		'LinkedIn post rules: 1200-1500 chars optimal. Start with a hook line. '
		'Use line breaks for readability. Include 3-5 relevant hashtags at end. '
		'Professional but personal tone. End with a question or CTA. '
		'No em-dashes. Use "I" perspective for thought leadership.'
	),
	'twitter': (
		'Twitter/X post rules: max 280 chars per tweet. '
		'If thread, write 3-5 tweets numbered "1/", "2/", etc. '
		'Punchy, direct. No fluff. 1-3 hashtags max. Strong hook in first tweet. '
		'End thread with clear takeaway.'
	),
	'instagram': (
		'Instagram caption rules: hook in first 2 lines (above fold). '
		'Can be 2200 chars but 125-150 chars is ideal. '
		'30 hashtags in first comment (not caption). '
		'Conversational, visual, emoji-friendly. CTA at end.'
	),
}


class SocialPostWriter:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def write(
		self,
		idea: str,
		platform: str = 'linkedin',
		context: str = '',
		tone: str = '',
		company_context: str = '',
		hashtags: list | str = '',
	) -> dict:
		"""
		Write a social media post for a specific platform.

		Returns:
			{post_text, hashtags, character_count, suggested_media_prompt,
			 platform, thread_tweets (if twitter)}
		"""
		platform_lower = platform.lower()
		rules          = _PLATFORM_RULES.get(platform_lower, _PLATFORM_RULES['linkedin'])
		default_tone   = 'professional-thought-leader' if platform_lower == 'linkedin' else 'concise-punchy'
		actual_tone    = tone or default_tone
		hashtag_list   = hashtags if isinstance(hashtags, list) else []

		prompt = (
			f'Write a {platform} post about this idea.\n\n'
			f'Idea: {idea}\n'
			f'Tone: {actual_tone}\n'
			f'Trending context: {context[:800]}\n'
			f'Company voice / examples: {company_context[:500]}\n'
			f'Suggested hashtags: {json.dumps(hashtag_list)}\n\n'
			f'Rules: {rules}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- post_text (str): the complete post ready to publish\n'
			'- hashtags (list of str): hashtags included\n'
			'- character_count (int): length of post_text\n'
			'- suggested_media_prompt (str): image/graphic description to pair with this post\n'
			'- platform (str): the platform this is for\n'
			+ ('- thread_tweets (list of str): individual tweet texts for the thread\n'
			   if platform_lower == 'twitter' else '')
		)

		response = self.ai_engine.generate_text(prompt)
		result = extract_json(response)
		if result is not None and 'post_text' in result:
			return result

		return {
			'post_text':              response[:2000],
			'hashtags':               hashtag_list,
			'character_count':        len(response),
			'suggested_media_prompt': '',
			'platform':               platform,
		}

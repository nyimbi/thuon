# capabilities/website_creator.py

from core.ai_engine import AIModel


class WebsiteCreator:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def generate_website_content(self, website_purpose: str, target_audience: str, key_features: list = ['homepage', 'about_us', 'contact_form', 'product_catalog']) -> dict:
		features_str = ', '.join(key_features)
		prompt = (
			f"You are a web copywriter and UX strategist. Generate comprehensive website content.\n\n"
			f"Website Purpose: {website_purpose}\nTarget Audience: {target_audience}\nPages: {features_str}\n\n"
			f"Return JSON with keys: site_name_suggestion, tagline, value_proposition, "
			f"pages (object, one key per feature/page with: headline, subheadline, body_content, "
			f"call_to_action, seo_keywords (list)), navigation_structure (list), "
			f"tone_and_voice, color_palette_suggestion, typography_suggestion, "
			f"social_proof_elements (list), trust_signals (list), conversion_goals (list)."
		)
		from core.output_validator import validated_llm_call
		result = validated_llm_call(self.ai_engine, prompt, fallback_key='result', required_keys=[], max_retries=2)
		if result.get('status') == 'parse_failed':
			return {'result': result.get('result', ''), 'purpose': website_purpose, 'audience': target_audience, 'pages': key_features, 'status': 'success'}
		return result

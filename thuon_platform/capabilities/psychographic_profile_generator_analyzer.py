# capabilities/psychographic_profile_generator_analyzer.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class PsychographicProfileGeneratorAnalyzer:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def generate_customer_psychographic_profile(self, target_segment_description: str, profile_dimensions: list = ['values', 'interests', 'lifestyle', 'personality']) -> dict:
		results = self.search_engine.search(f"psychographic profile {target_segment_description} consumer behavior", num_results=3)
		context = '\n'.join(f"- {r.get('body','')[:250]}" for r in results)

		dimensions_str = ', '.join(profile_dimensions)
		prompt = (
			f"You are a consumer psychologist and market researcher. Generate a psychographic profile.\n\n"
			f"Target Segment: {target_segment_description}\nProfile Dimensions: {dimensions_str}\n\n"
			f"Research context:\n{context}\n\n"
			f"Return JSON with keys: segment_name, segment_summary, "
			f"psychographic_profile (object with one key per dimension containing detailed description), "
			f"motivators (list), pain_points (list), decision_making_style, brand_affinities (list), "
			f"media_consumption_habits (list), messaging_recommendations (list), "
			f"product_feature_priorities (list), persona_name, persona_quote."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'segment': target_segment_description, 'dimensions': profile_dimensions, 'status': 'success'}

# capabilities/customer_support_chatbot_builder.py

import json
import re
from core.ai_engine import AIModel


class CustomerSupportChatbotBuilder:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def design_chatbot_flow(self, support_area: str, common_customer_queries: list, desired_chatbot_persona: str) -> dict:
		queries_str = '\n'.join(f"- {q}" for q in common_customer_queries[:10])
		prompt = (
			f"You are a conversational AI designer. Design a customer support chatbot flow.\n\n"
			f"Support Area: {support_area}\nChatbot Persona: {desired_chatbot_persona}\n"
			f"Common Customer Queries:\n{queries_str}\n\n"
			f"Return JSON with keys: chatbot_name, persona_description, "
			f"intents (list, each with: intent_name, example_utterances (list), "
			f"response_template, follow_up_actions (list)), "
			f"conversation_flows (list, each with: trigger, steps (list of: message, user_options)), "
			f"escalation_triggers (list), handoff_to_human_criteria (list), "
			f"fallback_responses (list), success_metrics (list), "
			f"integration_requirements (list), training_data_recommendations."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'support_area': support_area, 'persona': desired_chatbot_persona, 'status': 'success'}

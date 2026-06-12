# capabilities/internal_communications_automator.py

import json
import re
import datetime
from core.ai_engine import AIModel
from core.template_manager import TemplateManager


class InternalCommunicationsAutomator:
	def __init__(self, ai_engine: AIModel, template_manager: TemplateManager):
		self.ai_engine = ai_engine
		self.template_manager = template_manager

	def draft_internal_communication(
		self,
		communication_type: str,
		context_data: dict,
		audience: str,
		tone: str = 'professional',
		output_path: str = 'internal_communication.docx',
	) -> dict:
		"""
		Draft a communication and return a dict with:
		  - content: the drafted communication body
		  - subject, to, key_messages, call_to_action (parsed fields)
		  - output_path: file path if written, else None
		  - status: 'ok' | 'template_missing'
		"""
		template_name = 'announcement' if 'announcement' in communication_type.lower() else 'internal_memo'
		template = self.template_manager.get_template(template_name)

		context_str = json.dumps(context_data, indent=2)
		prompt = (
			f"You are a corporate communications specialist. Draft a {communication_type} internal communication.\n\n"
			f"Audience: {audience}\nTone: {tone}\nContext: {context_str}\n\n"
			f"Return JSON with keys: subject, to, from_name, body, headline, contact, key_messages (list), "
			f"call_to_action, follow_up_date."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			data = json.loads(match.group()) if match else {}
		except Exception:
			data = {'body': response}

		data.setdefault('date', str(datetime.date.today()))
		data.setdefault('to', audience)
		data.setdefault('subject', communication_type.replace('_', ' ').title())
		data.setdefault('headline', data.get('subject', ''))
		data.setdefault('contact', 'management@company.com')
		data.update({k: v for k, v in context_data.items() if k not in data})

		file_written = None
		if template:
			fmt = 'docx' if output_path.endswith('.docx') else 'md'
			ok = self.template_manager.generate_document_from_template_string(
				template.get('content', ''), data, fmt, output_path
			)
			if ok:
				file_written = output_path

		content = data.get('body') or data.get('executive_summary') or response

		return {
			'content':       content,
			'subject':       data.get('subject', ''),
			'to':            data.get('to', audience),
			'key_messages':  data.get('key_messages', []),
			'call_to_action': data.get('call_to_action', ''),
			'output_path':   file_written,
			'status':        'ok' if template else 'template_missing',
			'comm_type':     communication_type,
		}

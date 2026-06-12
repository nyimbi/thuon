# capabilities/proposal_compositor.py

import json
import re
import datetime
from core.ai_engine import AIModel
from core.template_manager import TemplateManager


class ProposalCompositor:
	def __init__(self, ai_engine: AIModel, template_manager: TemplateManager):
		self.ai_engine = ai_engine
		self.template_manager = template_manager

	def compose_proposal(
		self,
		proposal_type: str,
		context_data: dict,
		output_path: str = 'ai_proposal.docx',
	) -> dict:
		"""
		Compose a proposal and return a dict with:
		  - content: full rendered proposal text
		  - parsed structured fields
		  - output_path: file path if written, else None
		  - status: 'ok' | 'template_missing'
		"""
		template_name = 'project_proposal' if 'project' in proposal_type.lower() else 'business_proposal'
		template = self.template_manager.get_template(template_name)

		context_str = json.dumps(context_data, indent=2)
		prompt = (
			f"You are an expert proposal writer. Compose a compelling {proposal_type} proposal.\n\n"
			f"Context: {context_str}\n\n"
			f"Return JSON with keys: proposal_title, executive_summary, problem_statement, proposed_solution, "
			f"scope_of_work, timeline, investment, why_us, next_steps, project_name, project_lead, "
			f"project_overview, objectives, deliverables, resources, risks, budget, client_name, author."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			data = json.loads(match.group()) if match else {}
		except Exception:
			data = {'executive_summary': response}

		data.setdefault('date', str(datetime.date.today()))
		data.setdefault('proposal_title', f"{proposal_type.replace('_', ' ').title()} Proposal")
		data.update({k: v for k, v in context_data.items() if k not in data})

		file_written = None
		if template:
			fmt = 'docx' if output_path.endswith('.docx') else 'md'
			ok = self.template_manager.generate_document_from_template_string(
				template.get('content', ''), data, fmt, output_path
			)
			if ok:
				file_written = output_path

		sections = []
		for key in ('proposal_title', 'executive_summary', 'problem_statement', 'proposed_solution',
		            'scope_of_work', 'timeline', 'investment'):
			val = data.get(key)
			if val:
				sections.append(f"## {key.replace('_', ' ').title()}\n{val if isinstance(val, str) else json.dumps(val, indent=2)}")
		content = '\n\n'.join(sections) or response

		return {
			'content':          content,
			'proposal_title':   data.get('proposal_title', ''),
			'executive_summary': data.get('executive_summary', ''),
			'proposed_solution': data.get('proposed_solution', ''),
			'output_path':      file_written,
			'status':           'ok' if template else 'template_missing',
			'proposal_type':    proposal_type,
		}

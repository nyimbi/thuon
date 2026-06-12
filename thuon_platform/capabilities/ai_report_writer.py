# capabilities/ai_report_writer.py

import json
import re
import datetime
from core.ai_engine import AIModel
from core.template_manager import TemplateManager


class AIReportWriter:
	def __init__(self, ai_engine: AIModel, template_manager: TemplateManager):
		self.ai_engine = ai_engine
		self.template_manager = template_manager

	def generate_report(
		self,
		report_type: str,
		context_data: dict,
		output_path: str = 'ai_report.docx',
	) -> dict:
		"""
		Generate a report and return a dict with:
		  - content: the full rendered report text
		  - title, executive_summary, key_findings, recommendations (parsed fields)
		  - output_path: where the file was written (or None)
		  - status: 'ok' | 'template_missing'
		"""
		template_map = {
			'market_analysis': 'market_analysis_report',
			'executive':       'executive_report',
			'technical':       'technical_report',
		}
		template_name = template_map.get(report_type, 'executive_report')
		template = self.template_manager.get_template(template_name)

		context_str = json.dumps(context_data, indent=2)
		prompt = (
			f"You are an expert business analyst writing a {report_type} report.\n"
			f"Context data: {context_str}\n\n"
			f"Generate report content. Return JSON with keys: title, executive_summary, key_findings, "
			f"recommendations, conclusion, market, region, market_overview, market_size, "
			f"customer_segments, competitive_landscape, opportunities_threats, "
			f"overview, methodology, analysis, results."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			data = json.loads(match.group()) if match else {}
		except Exception:
			data = {'executive_summary': response}

		data.setdefault('title', f"{report_type.replace('_', ' ').title()} Report")
		data.setdefault('date', str(datetime.date.today()))
		data.update({k: v for k, v in context_data.items() if k not in data})

		file_written = None
		if template:
			fmt = 'docx' if output_path.endswith('.docx') else 'md'
			ok = self.template_manager.generate_document_from_template_string(
				template.get('content', ''), data, fmt, output_path
			)
			if ok:
				file_written = output_path

		# Build plain-text content for callers that don't need a file
		sections = []
		for key in ('title', 'executive_summary', 'key_findings', 'recommendations', 'conclusion'):
			val = data.get(key)
			if val:
				sections.append(f"## {key.replace('_', ' ').title()}\n{val if isinstance(val, str) else json.dumps(val, indent=2)}")
		content = '\n\n'.join(sections) or response

		return {
			'content':           content,
			'title':             data.get('title', ''),
			'executive_summary': data.get('executive_summary', ''),
			'key_findings':      data.get('key_findings', ''),
			'recommendations':   data.get('recommendations', ''),
			'output_path':       file_written,
			'status':            'ok' if template else 'template_missing',
			'report_type':       report_type,
		}

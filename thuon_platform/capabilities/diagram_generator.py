# capabilities/diagram_generator.py
"""
Mermaid diagram generator. Produces flowcharts, sequence diagrams, ERDs,
mind maps, Gantt charts, and more from natural language descriptions.
"""

from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile


_DIRECTIVES = {
	'flowchart':  'flowchart TD',
	'sequence':   'sequenceDiagram',
	'class':      'classDiagram',
	'er':         'erDiagram',
	'gantt':      'gantt',
	'pie':        'pie',
	'mindmap':    'mindmap',
	'timeline':   'timeline',
	'quadrant':   'quadrantChart',
	'state':      'stateDiagram-v2',
}


class DiagramGenerator:
	def __init__(self, ai_engine):
		self.ai_engine = ai_engine

	def generate(
		self,
		description: str,
		diagram_type: str = 'flowchart',
		output_path: str | None = None,
	) -> dict:
		"""
		Generate a Mermaid diagram from a natural language description.
		Returns mermaid_code always; also renders to PNG if mmdc CLI is available
		and output_path is given.
		"""
		directive = _DIRECTIVES.get(diagram_type.lower(), 'flowchart TD')
		prompt = (
			f'Generate a valid Mermaid {diagram_type} diagram for: {description}\n\n'
			f'Rules:\n'
			f'- Start with exactly: {directive}\n'
			f'- Use valid Mermaid v10 syntax only\n'
			f'- Include all key entities and relationships\n'
			f'- Keep node labels short (max 5 words)\n'
			f'- Return ONLY the Mermaid code, no explanation\n\n'
			f'```mermaid\n'
		)
		raw = self.ai_engine.generate_text(prompt)
		code = self._extract_code(raw, directive)

		result: dict = {
			'diagram_type':  diagram_type,
			'description':   description,
			'mermaid_code':  code,
			'status':        'ok',
		}

		if output_path:
			rendered = self._render_png(code, output_path)
			result['output_path'] = rendered
			result['rendered']    = rendered is not None

		return result

	def generate_mindmap(self, topic: str, output_path: str | None = None) -> dict:
		return self.generate(topic, diagram_type='mindmap', output_path=output_path)

	def generate_flowchart(self, process: str, output_path: str | None = None) -> dict:
		return self.generate(process, diagram_type='flowchart', output_path=output_path)

	def generate_sequence(self, interaction: str, output_path: str | None = None) -> dict:
		return self.generate(interaction, diagram_type='sequence', output_path=output_path)

	def generate_gantt(self, project: str, output_path: str | None = None) -> dict:
		return self.generate(project, diagram_type='gantt', output_path=output_path)

	def generate_er(self, schema: str, output_path: str | None = None) -> dict:
		return self.generate(schema, diagram_type='er', output_path=output_path)

	def _extract_code(self, raw: str, directive: str) -> str:
		match = re.search(r'```(?:mermaid)?\s*(.*?)```', raw, re.DOTALL)
		if match:
			return match.group(1).strip()
		if raw.strip().split('\n')[0].startswith(directive.split()[0]):
			return raw.strip()
		return raw.strip()

	def _render_png(self, code: str, output_path: str) -> str | None:
		if not shutil.which('mmdc'):
			return None
		with tempfile.NamedTemporaryFile(suffix='.mmd', mode='w', delete=False) as f:
			f.write(code)
			tmp = f.name
		try:
			os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
			r = subprocess.run(
				['mmdc', '-i', tmp, '-o', output_path, '-b', 'white'],
				capture_output=True, timeout=30,
			)
			return output_path if r.returncode == 0 else None
		except Exception:
			return None
		finally:
			os.unlink(tmp)

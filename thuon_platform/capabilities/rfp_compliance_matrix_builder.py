# capabilities/rfp_compliance_matrix_builder.py
"""
Atomic capability: build a compliance matrix from a list of parsed requirements.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array
from core.output_validator import validated_llm_call


class RFPComplianceMatrixBuilder:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def build_matrix(
		self,
		requirements: list | str,
		rfp_title: str = '',
	) -> dict:
		"""
		Build a compliance matrix from parsed requirements.

		Args:
			requirements: List of requirement objects or raw requirements text.
			rfp_title:    Title of the RFP (for context).

		Returns:
			{matrix: [{req_id, text, type, section, response_location,
			           keywords, status, notes}], total_shall, total_should}
		"""
		if isinstance(requirements, str):
			reqs_text = requirements
		else:
			reqs_text = json.dumps(requirements, indent=2)

		prompt = (
			f'You are a proposal compliance expert. For the RFP "{rfp_title}", '
			'build a full compliance matrix from the requirements below.\n\n'
			'Return ONLY a valid JSON object with these keys:\n'
			'- matrix (list): each item has keys:\n'
			'  - req_id (str): e.g. "L-1", "C-3", "M-2"\n'
			'  - text (str): requirement text verbatim\n'
			'  - type (str): "shall" | "should" | "may" | "informational"\n'
			'  - section (str): proposal section to address it (e.g. "Technical Approach")\n'
			'  - response_location (str): e.g. "Section 3.2, Page 12"\n'
			'  - keywords (list of str): key evaluation terms\n'
			'  - status (str): "to_address" for all new items\n'
			'  - notes (str): any flags or special handling needed\n'
			'- total_shall (int): count of shall requirements\n'
			'- total_should (int): count of should requirements\n\n'
			f'REQUIREMENTS:\n{reqs_text}'
		)

		result = validated_llm_call(
			self.ai_engine, prompt,
			required_keys=['matrix'],
			optional_keys=['total_shall', 'total_should'],
		)
		if result.get('status') == 'parse_failed' or 'matrix' not in result:
			result.update({
				'matrix': [], 'total_shall': 0, 'total_should': 0,
				'error': 'Could not parse compliance matrix',
			})
		return result

# capabilities/rfp_consistency_checker.py
"""
Atomic capability: cross-reference all proposal sections against the compliance matrix.
Flags uncovered requirements and internal inconsistencies.
"""

import json
import re
from core.ai_engine import AIModel
from core.llm_utils import extract_json, extract_json_array


class RFPConsistencyChecker:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def check(
		self,
		sections: dict | str = '',
		compliance_matrix: list | str = '',
		rfp_title: str = '',
	) -> dict:
		"""
		Check consistency and completeness across all written sections.

		Args:
			sections:           Dict of {section_name: content_or_section_dict}.
			compliance_matrix:  List of compliance matrix items.
			rfp_title:          Title of the RFP.

		Returns:
			{issues, coverage_pct, uncovered_requirements, red_team_score,
			 strengths, improvement_priorities}
		"""
		if isinstance(sections, dict):
			sections_text = '\n\n'.join(
				f'## {k}\n{v.get("content", str(v)) if isinstance(v, dict) else str(v)[:800]}'
				for k, v in sections.items()
			)
		else:
			sections_text = str(sections)

		matrix_text = json.dumps(compliance_matrix) if isinstance(compliance_matrix, list) else str(compliance_matrix)

		prompt = (
			f'You are a Red Team reviewer for the proposal responding to "{rfp_title or "this RFP"}".\n\n'
			'Your job: find gaps, inconsistencies, and weaknesses — be brutal.\n\n'
			f'COMPLIANCE MATRIX:\n{matrix_text[:3000]}\n\n'
			f'WRITTEN SECTIONS:\n{sections_text[:5000]}\n\n'
			'Return ONLY a valid JSON object with:\n'
			'- issues (list): each with {section, type: [coverage_gap|inconsistency|weak_argument|missing_proof], '
			'description, severity: high|medium|low, recommendation}\n'
			'- coverage_pct (int 0-100): percentage of shall requirements addressed\n'
			'- uncovered_requirements (list of str): req_ids not addressed\n'
			'- red_team_score (int 0-100): overall proposal quality score\n'
			'- strengths (list of str): top 3-5 strong points\n'
			'- improvement_priorities (list of str): top 3 things to fix before submission'
		)

		response = self.ai_engine.generate_text(prompt)
		try:
			return extract_json(response)
		except Exception:
			pass

		return {
			'issues':                    [],
			'coverage_pct':              0,
			'uncovered_requirements':    [],
			'red_team_score':            0,
			'strengths':                 [],
			'improvement_priorities':    [response[:300]],
		}

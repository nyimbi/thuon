# capabilities/accessibility_compliance_verifier.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class AccessibilityComplianceVerifier:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def verify_accessibility_compliance(self, digital_asset_description: str, compliance_standards: list = ['WCAG', 'Section508', 'ADA']) -> dict:
		standards_str = ', '.join(compliance_standards)
		results = self.search_engine.search(f"accessibility compliance {standards_str} checklist requirements 2024", num_results=4)
		context = '\n'.join(f"- {r.get('title','')}: {r.get('body','')[:300]}" for r in results)

		prompt = (
			f"You are an accessibility compliance expert. Evaluate the digital asset against accessibility standards.\n\n"
			f"Digital Asset: {digital_asset_description}\nStandards: {standards_str}\n\n"
			f"Reference context:\n{context}\n\n"
			f"Return JSON with keys: overall_compliance_score (0-100), "
			f"standards_compliance (object per standard with: score, status, violations (list with: "
			f"criterion, description, severity, remediation)), "
			f"priority_violations (top 5 list), quick_fixes (list), "
			f"estimated_remediation_effort (days), recommended_tools (list), "
			f"compliance_roadmap (phases list), legal_risk_level."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				return json.loads(match.group())
		except Exception:
			pass
		return {'result': response, 'asset': digital_asset_description, 'standards': compliance_standards, 'status': 'success'}

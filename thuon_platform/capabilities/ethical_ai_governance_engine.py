# capabilities/ethical_ai_governance_engine.py
# Grounded in EU AI Act (2024), NIST AI RMF 1.0 (2023), and IEEE Ethically Aligned Design.

import json
import re
from core.ai_engine import AIModel

_EU_AI_ACT_RISK_TIERS = {
	'unacceptable': [
		'real-time biometric surveillance in public spaces',
		'social scoring by governments',
		'manipulation of vulnerable groups',
	],
	'high_risk': [
		'biometric identification', 'critical infrastructure', 'employment decisions',
		'access to essential services', 'law enforcement', 'administration of justice',
	],
	'limited_risk': ['chatbots', 'emotion recognition', 'deepfake generation'],
	'minimal_risk': ['spam filters', 'AI-enabled video games', 'inventory automation'],
}

_NIST_RMF_FUNCTIONS = {
	'GOVERN':  'Policies, processes, and practices for AI risk management are in place.',
	'MAP':     'Context is established; AI risks are identified and prioritized.',
	'MEASURE': 'Risks are analyzed and tracked using defined methods.',
	'MANAGE':  'Risks are prioritized, responded to, and monitored.',
}

_IEEE_PRINCIPLES = [
	'Human Well-being', 'Data Agency', 'Effectiveness', 'Transparency',
	'Accountability', 'Awareness of Misuse', 'Competence',
]

_FRAMEWORK_CONTEXT = (
	"EU AI Act Risk Tiers:\n" + json.dumps(_EU_AI_ACT_RISK_TIERS, indent=2)
	+ "\n\nNIST AI RMF Core Functions:\n"
	+ '\n'.join(f"  {k}: {v}" for k, v in _NIST_RMF_FUNCTIONS.items())
	+ "\n\nIEEE Ethically Aligned Design Principles: " + ', '.join(_IEEE_PRINCIPLES)
)


class EthicalAIGovernanceEngine:
	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	def assess_ethical_risks(
		self,
		text_prompt: str,
		ethical_guidelines: list = ['privacy', 'fairness', 'transparency', 'accountability'],
	) -> dict:
		guidelines_str = ', '.join(ethical_guidelines)
		prompt = (
			f"You are an AI ethics expert. Assess the ethical risks of the following AI application.\n\n"
			f"Application/System Description:\n{text_prompt}\n\n"
			f"Ethical principles to evaluate: {guidelines_str}\n\n"
			f"Regulatory and standards framework:\n{_FRAMEWORK_CONTEXT}\n\n"
			f"1. Classify under the EU AI Act risk tier (unacceptable/high_risk/limited_risk/minimal_risk).\n"
			f"2. Assess against each NIST RMF function (GOVERN, MAP, MEASURE, MANAGE).\n"
			f"3. For each ethical guideline: risk_level (low/medium/high/critical), findings, mitigation_steps.\n\n"
			f"Return JSON with keys: overall_risk_level, eu_ai_act_classification (tier name), "
			f"eu_ai_act_obligations (list), nist_rmf_assessment (object per function: status, gaps, recommendations), "
			f"guideline_assessments (object per guideline: risk_level, findings, mitigation_steps), "
			f"key_concerns (list), recommended_safeguards (list), compliance_status, "
			f"requires_conformity_assessment (bool), audit_recommendations (list)."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				result['frameworks_applied'] = ['EU AI Act 2024', 'NIST AI RMF 1.0', 'IEEE EAD']
				return result
		except Exception:
			pass
		return {
			'result':             response,
			'ethical_guidelines': ethical_guidelines,
			'text_assessed':      text_prompt[:100],
			'frameworks_applied': ['EU AI Act 2024', 'NIST AI RMF 1.0', 'IEEE EAD'],
			'status':             'success',
		}

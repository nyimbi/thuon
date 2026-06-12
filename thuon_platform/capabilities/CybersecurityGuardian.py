# capabilities/CybersecurityGuardian.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class CybersecurityGuardian:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def perform_vulnerability_scan(self, system_description: str, scan_type: str = 'quick') -> dict:
		# Real CVE data from NVD — supplements web search with structured vulnerability data
		nvd_cves = []
		try:
			from core.data_sources.nvd import search_cves, format_cves_for_context
			# Extract meaningful keywords from the system description
			keywords = system_description[:80]
			nvd_cves = search_cves(keyword=keywords, limit=10)
		except Exception:
			pass

		web_results = self.search_engine.search(
			f"cybersecurity vulnerabilities {system_description} CVE threats 2024", num_results=4
		)
		web_context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:250]}" for r in web_results
		)

		nvd_context = ''
		if nvd_cves:
			try:
				from core.data_sources.nvd import format_cves_for_context
				nvd_context = f"\nNVD CVE Database ({len(nvd_cves)} relevant CVEs):\n{format_cves_for_context(nvd_cves[:6])}"
			except Exception:
				pass

		prompt = (
			f"You are a cybersecurity expert. Perform a {scan_type} vulnerability assessment.\n\n"
			f"System/Application: {system_description}\nScan Type: {scan_type}\n\n"
			f"Threat intelligence context:\n{web_context}{nvd_context}\n\n"
			f"Return JSON with keys: scan_summary, risk_score (0-10), "
			f"vulnerabilities (list with: cve_id, name, severity (critical/high/medium/low), "
			f"description, affected_component, exploitation_likelihood, remediation, "
			f"patch_available), attack_surface_analysis (list), "
			f"compliance_gaps (list with: standard, gap, remediation), "
			f"immediate_actions (list), security_hardening_recommendations (list), "
			f"monitoring_recommendations (list), estimated_remediation_time_days."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				if nvd_cves:
					result['nvd_cves_found'] = len(nvd_cves)
					result['nvd_sample'] = [
						{'id': c['cve_id'], 'score': c['score'], 'severity': c['severity']}
						for c in nvd_cves[:3]
					]
				return result
		except Exception:
			pass
		result = {'result': response, 'system': system_description, 'scan_type': scan_type, 'status': 'success'}
		if nvd_cves:
			result['nvd_cves_found'] = len(nvd_cves)
		return result

# capabilities/ma_target_profiler.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine


class MATargetProfiler:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine):
		self.ai_engine = ai_engine
		self.search_engine = search_engine

	def profile_ma_target(
		self,
		target_company_name: str,
		areas_of_interest: list = ['financials', 'market_position', 'technology_stack', 'culture_fit'],
	) -> dict:
		# SEC EDGAR — real financial data for US-listed companies
		edgar_context = ''
		edgar_facts = {}
		try:
			from core.data_sources.sec_edgar import (
				search_company_cik, get_company_facts, format_financials_for_context
			)
			cik = search_company_cik(target_company_name)
			if cik:
				edgar_facts = get_company_facts(cik)
				if edgar_facts.get('metrics'):
					edgar_context = (
						f"\nSEC EDGAR Financial Data:\n"
						f"{format_financials_for_context(edgar_facts)}"
					)
		except Exception:
			pass

		web_results = self.search_engine.search(
			f"{target_company_name} company profile financials market strategy", num_results=5
		)
		web_context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:300]}" for r in web_results
		)

		prompt = (
			f"You are an M&A analyst. Create a detailed acquisition target profile for {target_company_name}.\n\n"
			f"Areas of interest: {areas_of_interest}\n\n"
			f"Research context:\n{web_context}{edgar_context}\n\n"
			f"Return JSON with keys: company_name, executive_summary, financials (revenue, profitability, "
			f"debt_level, valuation_estimate), market_position (market_share, competitive_advantages, "
			f"customer_base), technology_stack (key_technologies, ip_assets, tech_debt_risk), "
			f"culture_fit (values, management_style, integration_risk), synergy_opportunities (list), "
			f"risk_factors (list), acquisition_recommendation, estimated_deal_value."
		)
		response = self.ai_engine.generate_text(prompt)
		try:
			match = re.search(r'\{.*\}', response, re.DOTALL)
			if match:
				result = json.loads(match.group())
				if edgar_facts.get('metrics'):
					result['edgar_financials'] = edgar_facts['metrics']
				return result
		except Exception:
			pass
		result = {
			'result': response,
			'company': target_company_name,
			'areas_of_interest': areas_of_interest,
			'status': 'success',
		}
		if edgar_facts.get('metrics'):
			result['edgar_financials'] = edgar_facts['metrics']
		return result

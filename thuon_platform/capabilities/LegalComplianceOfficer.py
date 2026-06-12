# capabilities/LegalComplianceOfficer.py

import json
import re
from core.ai_engine import AIModel
from core.search_engine import SearchEngine
from core.rag_engine import RAGEngine

_CHUNK_SIZE   = 2500
_CHUNK_OVERLAP = 300


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
	"""Split text into overlapping chunks so no clause is cut mid-analysis."""
	if len(text) <= size:
		return [text]
	chunks = []
	start = 0
	while start < len(text):
		end = min(start + size, len(text))
		chunks.append(text[start:end])
		start += size - overlap
	return chunks


class LegalComplianceOfficer:
	def __init__(self, ai_engine: AIModel, search_engine: SearchEngine, rag_engine: RAGEngine = None):
		self.ai_engine = ai_engine
		self.search_engine = search_engine
		self.rag_engine = rag_engine

	def review_contract_for_compliance(
		self,
		contract_text: str,
		compliance_standards: list = ['GDPR', 'CCPA', 'HIPAA'],
	) -> dict:
		standards_str = ', '.join(compliance_standards)
		web_results = self.search_engine.search(
			f"contract compliance {standards_str} requirements legal checklist", num_results=4
		)
		reference_context = '\n'.join(
			f"- {r.get('title','')}: {r.get('body','')[:250]}" for r in web_results
		)

		chunks = _chunk_text(contract_text)
		per_chunk_gaps: list[list] = []
		per_chunk_problems: list[list] = []

		for i, chunk in enumerate(chunks):
			chunk_prompt = (
				f"You are a legal compliance officer. Review the following contract excerpt "
				f"(part {i+1} of {len(chunks)}) for compliance with {standards_str}.\n\n"
				f"Contract excerpt:\n{chunk}\n\n"
				f"Compliance references:\n{reference_context}\n\n"
				f"Return JSON with keys: "
				f"gaps (list with: clause, issue, severity, recommendation), "
				f"problematic_clauses (list with: clause_excerpt, issue, recommendation)."
			)
			chunk_response = self.ai_engine.generate_text(chunk_prompt)
			try:
				m = re.search(r'\{.*\}', chunk_response, re.DOTALL)
				if m:
					chunk_data = json.loads(m.group())
					per_chunk_gaps.extend(chunk_data.get('gaps', []))
					per_chunk_problems.extend(chunk_data.get('problematic_clauses', []))
			except Exception:
				pass

		# Final synthesis across all chunks
		merged_gaps    = json.dumps(per_chunk_gaps[:30], indent=2)
		merged_problems = json.dumps(per_chunk_problems[:20], indent=2)
		summary_prompt = (
			f"You are a legal compliance officer. Synthesize these compliance findings from a full contract review.\n\n"
			f"Standards: {standards_str}\n"
			f"Contract length: {len(contract_text)} characters across {len(chunks)} sections.\n\n"
			f"Gaps found:\n{merged_gaps}\n\n"
			f"Problematic clauses:\n{merged_problems}\n\n"
			f"Return JSON with keys: overall_compliance_score (0-100), "
			f"standards_analysis (object per standard with: compliant (bool), score, gaps (list)), "
			f"risk_areas (list with: area, risk_level, description), "
			f"missing_clauses (list with: clause_name, why_required, suggested_language), "
			f"problematic_clauses (list), recommended_changes (list), "
			f"legal_risk_rating (low/medium/high/critical), requires_legal_counsel (bool), summary."
		)
		final_response = self.ai_engine.generate_text(summary_prompt)
		try:
			m = re.search(r'\{.*\}', final_response, re.DOTALL)
			if m:
				result = json.loads(m.group())
				result['chunks_analyzed'] = len(chunks)
				result['contract_length'] = len(contract_text)
				return result
		except Exception:
			pass
		return {
			'result':          final_response,
			'standards':       compliance_standards,
			'chunks_analyzed': len(chunks),
			'contract_length': len(contract_text),
			'status':          'success',
		}

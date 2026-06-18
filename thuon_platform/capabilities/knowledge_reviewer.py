# capabilities/knowledge_reviewer.py
"""
Atomic capability: review and validate proposed additions to the company
knowledge base for consistency, accuracy, and quality before applying them.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from core.ai_engine import AIModel
from core.bundle import writable_data_dir
from core.company_profile import get_company_profile
from core.llm_utils import extract_json

_log = logging.getLogger('thuon.knowledge_reviewer')

_CONTRIBUTIONS_DIR_NAME = 'kb_contributions'


def _contributions_dir() -> Path:
	d = writable_data_dir() / _CONTRIBUTIONS_DIR_NAME
	d.mkdir(parents=True, exist_ok=True)
	return d


def _company_dir() -> Path:
	d = writable_data_dir() / 'company'
	d.mkdir(parents=True, exist_ok=True)
	return d


def _uuid4_str() -> str:
	import uuid
	return str(uuid.uuid4())


_REVIEW_PROMPT = """You are a rigorous knowledge-base reviewer for a company content system.

## Existing file content
```
{existing_content}
```

## Proposed new content
```
{proposed_content}
```

## Contributor
{contributor}

Evaluate the proposed content against the existing file.  Consider:
1. **Factual contradictions** — does the proposed content contradict any facts stated in the existing content?
2. **Internal inconsistencies** — does the proposed content contradict itself?
3. **Quality issues** — vague claims, missing specifics, grammatical problems, unexplained acronyms, unsubstantiated assertions.
4. **Duplication** — does it merely repeat what is already present without adding value?

Return a single JSON object — no prose outside the JSON:
{{
  "approved": <true|false>,
  "consistency_score": <integer 0-100>,
  "issues": [
    {{"type": "<contradiction|inconsistency|quality|duplication>", "description": "<clear explanation>", "severity": "<high|medium|low>"}}
  ],
  "suggestions": ["<actionable improvement suggestion>"],
  "review_summary": "<one-paragraph plain-English summary of the review decision>",
  "reviewer_notes": "<internal notes for the knowledge-base curator>"
}}

Rules:
- `approved` must be false if any issue has severity "high".
- `consistency_score` reflects overall alignment with the existing KB (100 = perfect fit, 0 = directly contradicts).
- Keep `suggestions` concrete and actionable (empty list if none).
- Be strict but fair.
"""

_VALID_ISSUE_TYPES = frozenset({'contradiction', 'inconsistency', 'quality', 'duplication'})
_VALID_SEVERITIES = frozenset({'high', 'medium', 'low'})


class KnowledgeReviewer:
	"""Review, validate, queue, and apply proposed additions to the company KB."""

	def __init__(self, ai_engine: AIModel):
		self.ai_engine = ai_engine

	# ── Core review ───────────────────────────────────────────────────────────

	def review_contribution(
		self,
		file_name: str,
		proposed_content: str,
		contributor: str = 'unknown',
	) -> dict:
		"""
		Use the AI to validate proposed_content against the existing file.

		Returns:
		    {
		        approved: bool,
		        consistency_score: int (0-100),
		        issues: list[{type, description, severity}],
		        suggestions: list[str],
		        review_summary: str,
		        reviewer_notes: str,
		    }
		"""
		if not file_name.endswith('.md'):
			file_name = file_name + '.md'

		existing_content = get_company_profile().get_file(file_name)

		prompt = _REVIEW_PROMPT.format(
			existing_content=existing_content,
			proposed_content=proposed_content,
			contributor=contributor,
		)

		raw = self.ai_engine.generate_text(prompt)
		parsed = extract_json(raw)

		if parsed is None:
			_log.warning('review_contribution: failed to parse AI response for %s', file_name)
			return {
				'approved': False,
				'consistency_score': 0,
				'issues': [{
					'type': 'quality',
					'description': 'AI reviewer returned an unparseable response.',
					'severity': 'high',
				}],
				'suggestions': ['Retry the review or inspect the AI response manually.'],
				'review_summary': 'Review failed: the AI did not return a valid JSON assessment.',
				'reviewer_notes': f'Raw AI output (truncated): {raw[:500]}',
			}

		# Normalise / fill defaults to guarantee all keys are present.
		result: dict = {
			'approved': bool(parsed.get('approved', False)),
			'consistency_score': max(0, min(100, int(parsed.get('consistency_score', 50)))),
			'issues': [],
			'suggestions': list(parsed.get('suggestions') or []),
			'review_summary': str(parsed.get('review_summary', '')),
			'reviewer_notes': str(parsed.get('reviewer_notes', '')),
		}

		for issue in parsed.get('issues') or []:
			if not isinstance(issue, dict):
				continue
			issue_type = issue.get('type', 'quality')
			severity = issue.get('severity', 'medium')
			result['issues'].append({
				'type': issue_type if issue_type in _VALID_ISSUE_TYPES else 'quality',
				'description': str(issue.get('description', '')),
				'severity': severity if severity in _VALID_SEVERITIES else 'medium',
			})

		# Enforce the rule: any high-severity issue => not approved.
		if any(i['severity'] == 'high' for i in result['issues']):
			result['approved'] = False

		return result

	# ── Apply ─────────────────────────────────────────────────────────────────

	def apply_contribution(
		self,
		file_name: str,
		proposed_content: str,
		contributor: str,
		review: dict,
		override: bool = False,
	) -> dict:
		"""
		Write proposed_content to the company KB file if the review approved it
		(or override=True).  Creates a .bak of the previous content first, then
		reloads the KB.

		Returns:
		    {applied: bool, file_path: str, backup_path: str, message: str}
		"""
		if not file_name.endswith('.md'):
			file_name = file_name + '.md'

		approved: bool = bool(review.get('approved', False))

		if not approved and not override:
			return {
				'applied': False,
				'file_path': '',
				'backup_path': '',
				'message': (
					f"Contribution rejected (approved=False) and override not set. "
					f"Review summary: {review.get('review_summary', 'n/a')}"
				),
			}

		target: Path = _company_dir() / file_name
		backup: Path = Path(str(target) + '.bak')

		# Back up existing file (silently skip if it does not exist yet).
		backup_path_str = ''
		if target.exists():
			try:
				shutil.copy2(target, backup)
				backup_path_str = str(backup)
			except OSError as exc:
				_log.warning('apply_contribution: could not create backup for %s: %s', file_name, exc)

		# Write the new content.
		try:
			target.parent.mkdir(parents=True, exist_ok=True)
			target.write_text(proposed_content, encoding='utf-8')
		except OSError as exc:
			_log.error('apply_contribution: write failed for %s: %s', file_name, exc)
			return {
				'applied': False,
				'file_path': str(target),
				'backup_path': backup_path_str,
				'message': f'Write error: {exc}',
			}

		# Reload the KB so the new content is indexed immediately.
		try:
			get_company_profile().reload()
		except Exception as exc:
			_log.warning('apply_contribution: KB reload failed after writing %s: %s', file_name, exc)

		_log.info(
			'apply_contribution: applied %s (contributor=%s, override=%s)',
			file_name, contributor, override,
		)
		return {
			'applied': True,
			'file_path': str(target),
			'backup_path': backup_path_str,
			'message': (
				f"Contribution applied successfully."
				f"{' Override used.' if override and not approved else ''}"
				f"{f' Backup at {backup_path_str}.' if backup_path_str else ' No previous file to back up.'}"
			),
		}

	# ── Contribution queue ────────────────────────────────────────────────────

	def submit_contribution(
		self,
		file_name: str,
		proposed_content: str,
		contributor: str,
	) -> str:
		"""
		Persist a proposed contribution for later review.

		Returns the contribution id (UUID4 string).
		"""
		contribution_id = _uuid4_str()
		record = {
			'id': contribution_id,
			'file_name': file_name if file_name.endswith('.md') else file_name + '.md',
			'proposed_content': proposed_content,
			'contributor': contributor,
			'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
			'status': 'pending',
		}
		dest = _contributions_dir() / f'{contribution_id}.json'
		dest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
		_log.info('submit_contribution: queued %s from %s', contribution_id, contributor)
		return contribution_id

	def list_pending(self) -> list[dict]:
		"""
		Return all contribution records from the contributions directory,
		sorted by created_at descending (newest first).
		"""
		contrib_dir = _contributions_dir()
		records: list[dict] = []

		for json_file in contrib_dir.glob('*.json'):
			try:
				data = json.loads(json_file.read_text(encoding='utf-8'))
				records.append(data)
			except (json.JSONDecodeError, OSError) as exc:
				_log.warning('list_pending: skipping malformed file %s: %s', json_file.name, exc)

		records.sort(key=lambda r: r.get('created_at', ''), reverse=True)
		return records

"""
Generates all company KB markdown files from structured interview answers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Each file gets its own system prompt snippet so the LLM knows exactly what to produce.
_FILE_SPECS: list[tuple[str, str, str]] = [
	(
		'profile.md',
		'Company Profile',
		"""Write a thorough company profile in markdown. Include:
- Company name, tagline, mission statement
- Website, HQ location, founding year, team size
- Legal entity type (if known)
- NAICS codes and PSC codes (if provided)
- Business certifications (8(a), WOSB, SDVOSB, HUBZone, ISO, CMMI, etc.)
- Diversity/socioeconomic status
- Areas of operation (federal, state/local, commercial, sectors)
- Brief company history / founding story

Use headers (##, ###) and bullet lists. Be specific — use the exact data from the interview.""",
	),
	(
		'capabilities.md',
		'Capabilities & Service Catalog',
		"""Write a detailed capabilities document in markdown. Include:
- Full service catalog with brief description of each offering
- Core technical competencies and platforms
- Tools, frameworks, and technologies
- Delivery methodologies (Agile, DevSecOps, ITIL, etc.)
- SLAs or performance standards you commit to
- Unique differentiators per service line
- Use cases and example applications

Organize by service line with ## headers. Be concrete and specific.""",
	),
	(
		'personnel.md',
		'Key Personnel',
		"""Write a key personnel document in markdown. For each person include:
- Full name and title
- Brief professional bio (3-5 sentences)
- Core skills and domain expertise
- Relevant certifications and clearances
- Years of experience
- Notable past projects or roles

Use ### for each person. Extract everyone mentioned in the interview.""",
	),
	(
		'past_performance.md',
		'Past Performance',
		"""Write past performance write-ups in markdown. For each project include:
- Client/agency name
- Contract number or vehicle (if known)
- Period of performance
- Contract value (approximate if not exact)
- Scope summary (2-3 sentences)
- Key deliverables
- Measurable results and outcomes
- Technologies/methods used
- Reference contact (if provided)

Use ## for each project. Make outcomes specific and quantified wherever possible.""",
	),
	(
		'pricing.md',
		'Pricing & Rate Card',
		"""Write a pricing and rate card document in markdown. Include:
- Labor categories with fully-loaded hourly rates (or ranges)
- Overhead, G&A, and profit rates
- Fringe/benefit rates
- Escalation methodology (e.g. CPI, fixed %)
- Pricing strategy narrative (value-based, competitive, cost-plus)
- Typical contract vehicle pricing (T&M, FFP, CPFF)
- Volume discount thresholds
- Subcontractor pass-through markup

If specific rates weren't provided, use reasonable placeholders marked [TBD].""",
	),
	(
		'win_themes.md',
		'Win Themes',
		"""Write a win themes library in markdown. Include 8-12 win themes. For each:
- Theme headline (bold, punchy)
- 2-3 sentence elaboration
- 3-5 concrete proof points (metrics, awards, certifications, client quotes)
- Ghosting angle (implicit weakness of competitors this theme exploits)
- Best used for: (which opportunity types this theme fits)

Base themes on differentiators and strengths mentioned in the interview. Make them specific, not generic.""",
	),
	(
		'style_guide.md',
		'Proposal Style Guide',
		"""Write a proposal writing style guide in markdown. Include:
- Tone of voice (e.g. confident, direct, government-formal, or a specific blend)
- Active vs passive voice rules
- Sentence length guidance
- Forbidden phrases and clichés to avoid
- Preferred terminology for your offerings
- Acronym handling rules (define on first use, approved acronym list)
- Number formatting (spell out under 10, etc.)
- Formatting conventions (table styles, figure captions, callout boxes)
- Executive summary guidelines
- Page / word count discipline

Keep it practical — these are rules writers will actually follow.""",
	),
	(
		'bid_criteria.md',
		'Bid / No-Bid Criteria',
		"""Write a bid/no-bid decision framework in markdown. Include:
## Must-Have Criteria (automatic go)
- Mandatory qualifications the opportunity must match
- Contract vehicle eligibility
- Minimum incumbent advantage threshold

## Automatic No-Bid Triggers
- Contract size below threshold
- Missing required certifications or clearances
- Conflict of interest rules
- Competitor blacklist (clients you won't work with)
- Geographies or sectors out of scope

## Scoring Rubric (0-100 bid score)
Include 6-10 weighted factors (mission alignment, incumbency, past performance match, etc.)

## Decision Thresholds
- 80+: Automatic go, full resource commitment
- 60-79: Leadership review required
- <60: No-bid unless strategic exception

Use the company's stated criteria from the interview. Add sensible defaults where not specified.""",
	),
	(
		'compliance_boilerplate.md',
		'Compliance Boilerplate',
		"""Write standard compliance and representations boilerplate in markdown. Include:
- Standard certifications and representations (FAR 52.212-3 type)
- SAM.gov registration status placeholder
- Insurance coverage types and minimums
- Bonding capacity
- Equal opportunity employer statement
- Non-discrimination statement
- Buy American / TAA compliance statement
- Small business representations
- Cybersecurity compliance (NIST 800-171, CMMC level if applicable)
- Data handling / privacy statement

Mark anything that needs company-specific data as [INSERT: description].""",
	),
]


class CompanyProfileGenerator:
	def __init__(self, ai_engine: Any, company_profile: Any | None = None) -> None:
		self._ai  = ai_engine
		self._profile = company_profile

	def generate(self, interview_answers: dict[str, Any]) -> dict[str, Any]:
		"""
		Takes structured interview answers and writes all 9 company KB files.
		Returns {files_written, errors, summary}.
		"""
		profile_dir = self._resolve_dir()
		context_block = self._format_context(interview_answers)

		files_written: list[str] = []
		errors: list[str] = []

		for filename, doc_type, instructions in _FILE_SPECS:
			try:
				prompt = f"""{instructions}

---
COMPANY INTERVIEW DATA:
{context_block}
---

Write the complete {doc_type} markdown document now. Start directly with the markdown — no preamble, no "Here is..." intro."""

				content = self._ai.generate(prompt)
				# Strip accidental code fence wrapping
				content = re.sub(r'^```(?:markdown)?\n', '', content.strip())
				content = re.sub(r'\n```$', '', content)

				out_path = profile_dir / filename
				out_path.write_text(content.strip() + '\n', encoding='utf-8')
				files_written.append(filename)
			except Exception as exc:  # noqa: BLE001
				errors.append(f'{filename}: {exc}')

		if self._profile is not None:
			try:
				self._profile.reload()
			except Exception:
				pass

		return {
			'files_written': files_written,
			'errors': errors,
			'total': len(files_written),
			'summary': (
				f"Generated {len(files_written)}/{len(_FILE_SPECS)} company KB files. "
				+ (f"Errors: {'; '.join(errors)}" if errors else "All files written successfully.")
			),
		}

	# ── helpers ──────────────────────────────────────────────────────────────

	def _resolve_dir(self) -> Path:
		if self._profile is not None and hasattr(self._profile, '_dir'):
			return Path(self._profile._dir)
		# fallback: relative to this file
		here = Path(__file__).parent.parent
		return here / 'data' / 'company'

	@staticmethod
	def _format_context(answers: dict[str, Any]) -> str:
		lines: list[str] = []
		for key, val in answers.items():
			label = key.replace('_', ' ').title()
			if isinstance(val, list):
				lines.append(f'{label}:')
				for item in val:
					if isinstance(item, dict):
						for k, v in item.items():
							lines.append(f'  {k}: {v}')
						lines.append('')
					else:
						lines.append(f'  - {item}')
			elif isinstance(val, dict):
				lines.append(f'{label}:')
				for k, v in val.items():
					lines.append(f'  {k}: {v}')
			elif val:
				lines.append(f'{label}: {val}')
		return '\n'.join(lines)

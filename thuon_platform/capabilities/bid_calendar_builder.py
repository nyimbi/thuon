"""
BidCalendarBuilder — fetches upcoming federal recompete opportunities from USASpending,
enriches each with AI analysis, and returns a structured calendar dict.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from thuon_platform.core.ai_engine import AIModel

logger = logging.getLogger(__name__)

_MAX_PAGES = 3
_PAGE_SIZE = 50


def extract_json(text: str) -> dict:
	"""Best-effort extraction of the first JSON object found in *text*."""
	start = text.find("{")
	end = text.rfind("}")
	if start == -1 or end == -1 or end < start:
		return {}
	try:
		return json.loads(text[start : end + 1])
	except json.JSONDecodeError:
		return {}


class BidCalendarBuilder:
	"""Build a forward-looking bid/recompete calendar from USASpending data."""

	def __init__(self, ai_engine: AIModel) -> None:
		self._ai = ai_engine

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def build_calendar(
		self,
		naics_codes: list[str],
		keywords: list[str] | None = None,
		months_ahead: int = 12,
	) -> dict:
		"""
		Fetch contracts from USASpending whose period-of-performance end date falls
		within the next *months_ahead* months, enrich each with AI analysis, and
		return the full calendar dict.
		"""
		keywords = keywords or []
		today = datetime.utcnow().date()
		cutoff = today + timedelta(days=months_ahead * 30)

		raw_results = self._fetch_awards(naics_codes, keywords)

		opportunities: list[dict] = []
		for award in raw_results:
			pop_end_str = award.get("Period of Performance Current End Date") or ""
			try:
				pop_end = datetime.strptime(pop_end_str, "%Y-%m-%d").date()
			except (ValueError, TypeError):
				continue
			if not (today <= pop_end <= cutoff):
				continue
			enriched = self._enrich_opportunity(award, pop_end_str)
			opportunities.append(enriched)

		if not opportunities:
			return self._sample_response(naics_codes, months_ahead, note="No live results — sample data shown.")

		total_pipeline_value = sum(
			(opp.get("estimated_value_min", 0) + opp.get("estimated_value_max", 0)) / 2
			for opp in opportunities
		)

		by_month: dict[str, list[dict]] = {}
		for opp in opportunities:
			key = opp.get("estimated_recompete_date", "")[:7]  # YYYY-MM
			if key:
				by_month.setdefault(key, []).append(opp)

		return {
			"generated_date": today.isoformat(),
			"naics_codes": naics_codes,
			"months_ahead": months_ahead,
			"opportunities": opportunities,
			"total_pipeline_value": total_pipeline_value,
			"by_month": by_month,
			"api_note": "Live data from api.usaspending.gov",
		}

	def get_upcoming_from(self, calendar: dict, days: int = 90) -> list[dict]:
		"""
		Filter an existing calendar dict for opportunities within the next *days* days,
		sorted ascending by estimated_recompete_date.
		"""
		today = datetime.utcnow().date()
		cutoff = today + timedelta(days=days)
		results = []
		for opp in calendar.get("opportunities", []):
			date_str = opp.get("estimated_recompete_date", "")
			try:
				opp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
			except (ValueError, TypeError):
				continue
			if today <= opp_date <= cutoff:
				results.append(opp)
		return sorted(results, key=lambda o: o.get("estimated_recompete_date", ""))

	def get_upcoming(self, days: int = 90) -> list[dict]:  # noqa: ARG002
		"""
		Not implemented — call get_upcoming_from(calendar, days) instead, passing the
		dict returned by build_calendar().
		"""
		raise NotImplementedError(
			"get_upcoming() has no internal state. "
			"Call build_calendar() first, then pass the result to get_upcoming_from(calendar, days)."
		)

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	def _fetch_awards(self, naics_codes: list[str], keywords: list[str]) -> list[dict]:
		"""Page through USASpending award search, returning raw result rows."""
		url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
		filters: dict[str, Any] = {
			"award_type_codes": ["A", "B", "C", "D"],
			"naics_codes": naics_codes,
		}
		if keywords:
			filters["keywords"] = keywords

		all_results: list[dict] = []
		for page in range(1, _MAX_PAGES + 1):
			payload = {
				"filters": filters,
				"fields": [
					"Award ID",
					"Recipient Name",
					"Award Amount",
					"Description",
					"NAICS Code",
					"NAICS Description",
					"Period of Performance Current End Date",
					"Awarding Agency",
					"Place of Performance City Code",
					"Place of Performance State Code",
				],
				"page": page,
				"limit": _PAGE_SIZE,
				"sort": "Period of Performance Current End Date",
				"order": "asc",
				"subawards": False,
				"date_type": "action_date",
			}
			try:
				resp = httpx.post(url, json=payload, timeout=30)
				resp.raise_for_status()
				data = resp.json()
				results = data.get("results", [])
				all_results.extend(results)
				if len(results) < _PAGE_SIZE:
					break
			except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as exc:
				logger.warning("USASpending API error on page %d: %s", page, exc)
				break

		return all_results

	def _enrich_opportunity(self, award: dict, pop_end_str: str) -> dict:
		"""Ask the AI engine to enrich a raw award dict with recompete analysis."""
		prompt = (
			"You are a federal contracting analyst. Given the following contract data, "
			"return ONLY a JSON object with these keys:\n"
			"  recompete_likelihood: float 0.0-1.0\n"
			"  estimated_value_min: int (USD)\n"
			"  estimated_value_max: int (USD)\n"
			"  rationale: str (1-2 sentences)\n"
			"  action_items: list[str] (2-4 concrete next steps)\n\n"
			f"Contract data:\n{json.dumps(award, indent=2)}\n\n"
			"Return ONLY the JSON object, no markdown fences."
		)
		enriched: dict = {
			"award_id": award.get("Award ID", ""),
			"recipient_name": award.get("Recipient Name", ""),
			"award_amount": award.get("Award Amount"),
			"description": award.get("Description", ""),
			"naics_code": award.get("NAICS Code", ""),
			"naics_description": award.get("NAICS Description", ""),
			"awarding_agency": award.get("Awarding Agency", ""),
			"place_of_performance": (
				f"{award.get('Place of Performance City Code', '')}, "
				f"{award.get('Place of Performance State Code', '')}"
			).strip(", "),
			"estimated_recompete_date": pop_end_str,
			"recompete_likelihood": 0.5,
			"estimated_value_min": 0,
			"estimated_value_max": 0,
			"rationale": "",
			"action_items": [],
		}
		try:
			raw = self._ai.generate(prompt)
			parsed = extract_json(raw)
			if parsed:
				enriched["recompete_likelihood"] = float(parsed.get("recompete_likelihood", 0.5))
				enriched["estimated_value_min"] = int(parsed.get("estimated_value_min", 0))
				enriched["estimated_value_max"] = int(parsed.get("estimated_value_max", 0))
				enriched["rationale"] = str(parsed.get("rationale", ""))
				enriched["action_items"] = list(parsed.get("action_items", []))
		except Exception as exc:  # noqa: BLE001
			logger.warning("AI enrichment failed for award %s: %s", enriched["award_id"], exc)
		return enriched

	def _sample_response(
		self,
		naics_codes: list[str],
		months_ahead: int,
		note: str = "Sample data",
	) -> dict:
		"""Return a structurally identical calendar dict with placeholder sample data."""
		today = datetime.utcnow().date()
		sample_date = (today + timedelta(days=45)).isoformat()
		sample_opp = {
			"award_id": "SAMPLE-0001",
			"recipient_name": "Example Contractor LLC",
			"award_amount": 500000,
			"description": "Sample IT support services contract",
			"naics_code": naics_codes[0] if naics_codes else "541512",
			"naics_description": "Computer Systems Design Services",
			"awarding_agency": "Department of Sample Affairs",
			"place_of_performance": "Washington, DC",
			"estimated_recompete_date": sample_date,
			"recompete_likelihood": 0.75,
			"estimated_value_min": 400000,
			"estimated_value_max": 600000,
			"rationale": "Sample opportunity — no live API data available.",
			"action_items": [
				"Verify NAICS codes are correct",
				"Confirm USASpending API connectivity",
				"Review contract scope when live data available",
			],
		}
		month_key = sample_date[:7]
		return {
			"generated_date": today.isoformat(),
			"naics_codes": naics_codes,
			"months_ahead": months_ahead,
			"opportunities": [sample_opp],
			"total_pipeline_value": 500000.0,
			"by_month": {month_key: [sample_opp]},
			"api_note": note,
		}

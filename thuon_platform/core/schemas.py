# core/schemas.py
"""
Typed input schemas for all capabilities.
Provides IDE completion, validation errors before LLM calls, and self-documentation.

Usage:
    from core.schemas import ResearchInput, DiagramInput, TenderInput
    result = thuon.research_assistant.perform_research(ResearchInput(query="AI in Kenya", depth="deep"))
"""

from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class _Base(BaseModel):
	model_config = ConfigDict(extra='forbid', validate_by_name=True)


# ── Research ─────────────────────────────────────────────────────────────────

class ResearchInput(_Base):
	query:       str   = Field(..., description='Research question or topic')
	depth:       Literal['quick','shallow','medium','deep','comprehensive','academic','phd'] = 'medium'
	num_sources: int   = Field(default=5, ge=1, le=20)
	output_format: Literal['dict','pdf','docx','slides'] = 'dict'


class DeepResearchInput(_Base):
	topic:  str = Field(..., description='Research topic for deep multi-phase analysis')
	depth:  Literal['quick','shallow','medium','deep','comprehensive','academic','phd'] = 'deep'
	output_format: Literal['dict','pdf','docx','slides'] = 'dict'


# ── Document ─────────────────────────────────────────────────────────────────

class DocumentInput(_Base):
	topic:      str = Field(..., description='Subject or title of the document')
	format:     Literal['docx','pdf','pptx','xlsx'] = 'docx'
	doc_type:   Literal['report','proposal','memo','presentation','spreadsheet'] = 'report'
	context:    str = ''
	output_path: str | None = None


# ── Diagram ───────────────────────────────────────────────────────────────────

class DiagramInput(_Base):
	description:  str = Field(..., description='Natural language description of what to diagram')
	diagram_type: Literal['flowchart','sequence','er','class','gantt','pie','mindmap','timeline','state'] = 'flowchart'
	output_path:  str | None = None


# ── Competitive intelligence ──────────────────────────────────────────────────

class CompetitiveInput(_Base):
	company_name:    str = Field(..., description='Primary company to analyze')
	industry:        str = ''
	area_of_interest: str = ''
	num_competitors: int = Field(default=3, ge=1, le=10)


# ── Financial ─────────────────────────────────────────────────────────────────

class FinancialInput(_Base):
	company_or_topic: str = Field(..., description='Company name or financial topic')
	forecast_horizon: int = Field(default=12, ge=1, le=60, description='Months ahead')
	data_table:        str = ''


# ── Tender ────────────────────────────────────────────────────────────────────

class TenderInput(_Base):
	sector:      str = Field(..., description='Industry sector e.g. ICT, construction, healthcare')
	countries:   list[str] | None = None
	keywords:    list[str] | None = None
	max_results: int = Field(default=20, ge=1, le=100)


# ── Contract ─────────────────────────────────────────────────────────────────

class ContractInput(_Base):
	contract_text: str = Field(..., description='Contract or subscription agreement text')
	vendor:        str = ''
	category:      Literal['saas','telecom','insurance','cloud','streaming','gym','software','office','utilities','other'] = 'other'


class DraftEmailInput(_Base):
	vendor:        str   = Field(..., description='Vendor or supplier name')
	current_price: float = Field(..., ge=0, description='Current monthly cost')
	email_type:    Literal['discount','cancel','price_match'] = 'discount'
	currency:      str   = 'KES'
	context:       str   = ''


class PortfolioInput(_Base):
	subscriptions: list[dict] = Field(..., description='List of subscription dicts: {vendor, monthly_cost, category}')


# ── Brief ─────────────────────────────────────────────────────────────────────

class BriefInput(_Base):
	topics:           list[str] | None = None
	focus_areas:      list[str] | None = None
	include_sections: list[Literal['news_summary','knowledge_highlights','market_pulse','action_items']] | None = None


# ── Receipt ──────────────────────────────────────────────────────────────────

class ReceiptInput(_Base):
	image_path: str = Field(..., description='Path to receipt or invoice image')


# ── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineInput(_Base):
	pipeline: str = Field(..., description='Pipeline name or path to YAML file')
	params:   dict[str, Any] = Field(default_factory=dict)


# ── Registry: map capability name → input schema ─────────────────────────────

CAPABILITY_SCHEMAS: dict[str, type[_Base]] = {
	'research_assistant':             ResearchInput,
	'deep_researcher':                DeepResearchInput,
	'document_generator':             DocumentInput,
	'diagram_generator':              DiagramInput,
	'competitive_intelligence_operative': CompetitiveInput,
	'financial_forecasting_analyst':  FinancialInput,
	'tender_scout':                   TenderInput,
	'contract_renegotiator':          ContractInput,
	'daily_brief':                    BriefInput,
	'receipt_analyzer':               ReceiptInput,
}

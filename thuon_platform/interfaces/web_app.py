# interfaces/web_app.py

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, request, jsonify, render_template, flash
from flask_cors import CORS

import collections
import time

from core.ai_engine import OllamaModel
from core.search_engine import DuckDuckGoSearch
from core.data_handler import DatabaseHandler
from core.rag_engine import RAGEngine
from core.knowledge_graph_manager import KnowledgeGraphManager
from core.template_manager import TemplateManager
from core.settings_manager import get_settings

# Run history — last 50 entries, shared across requests
_run_history: collections.deque = collections.deque(maxlen=50)

# Lazy Thuon instance for NL routing
_thuon_router = None


def _get_router():
	global _thuon_router
	if _thuon_router is None:
		from thuon import Thuon as _Thuon
		_thuon_router = _Thuon()
	return _thuon_router


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

CAPABILITY_REGISTRY = {
	'research_assistant': {
		'description': 'Performs in-depth research using web search and RAG, with summarization and curation.',
		'method': 'perform_research',
		'params': [
			{'name': 'research_query', 'type': 'str', 'required': True},
			{'name': 'sources', 'type': 'list', 'required': False, 'default': ['web', 'knowledge_graph']},
			{'name': 'depth', 'type': 'str', 'required': False, 'default': 'medium'},
		],
		'deps': ['ai_engine', 'search_engine', 'rag_engine', 'db_handler'],
		'module': 'capabilities.research_assistant',
		'class': 'ResearchAssistant',
	},
	'ai_report_writer': {
		'description': 'Generates structured business reports from context data using templates.',
		'method': 'generate_report',
		'params': [
			{'name': 'report_type', 'type': 'str', 'required': True},
			{'name': 'context_data', 'type': 'str', 'required': True},
			{'name': 'output_path', 'type': 'str', 'required': False, 'default': 'report.docx'},
		],
		'deps': ['ai_engine', 'template_manager'],
		'module': 'capabilities.ai_report_writer',
		'class': 'AIReportWriter',
	},
	'competitive_intelligence_operative': {
		'description': 'Analyzes competitor landscape with positioning and strategic insights.',
		'method': 'analyze_competitor_landscape',
		'params': [
			{'name': 'industry', 'type': 'str', 'required': True},
			{'name': 'competitors', 'type': 'list', 'required': True},
			{'name': 'analysis_dimensions', 'type': 'list', 'required': False, 'default': ['product', 'pricing', 'marketing']},
		],
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'module': 'capabilities.competitive_intelligence_operative',
		'class': 'CompetitiveIntelligenceOperative',
	},
	'ethical_ai_governance_engine': {
		'description': 'Assesses ethical risks in AI systems against governance frameworks.',
		'method': 'assess_ethical_risks',
		'params': [
			{'name': 'ai_system_description', 'type': 'str', 'required': True},
			{'name': 'ethical_guidelines', 'type': 'list', 'required': False, 'default': ['fairness', 'transparency', 'privacy']},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.ethical_ai_governance_engine',
		'class': 'EthicalAIGovernanceEngine',
	},
	'social_media_manager': {
		'description': 'Analyzes social media trends and generates platform-specific content strategies.',
		'method': 'analyze_social_trends',
		'params': [
			{'name': 'brand_name', 'type': 'str', 'required': True},
			{'name': 'target_audience', 'type': 'str', 'required': True},
			{'name': 'platforms', 'type': 'list', 'required': False, 'default': ['Twitter', 'LinkedIn', 'Instagram']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.social_media_manager',
		'class': 'SocialMediaManager',
	},
	'proposal_compositor': {
		'description': 'Composes professional business proposals from requirements.',
		'method': 'compose_proposal',
		'params': [
			{'name': 'proposal_type', 'type': 'str', 'required': True},
			{'name': 'client_name', 'type': 'str', 'required': True},
			{'name': 'project_description', 'type': 'str', 'required': True},
			{'name': 'budget_range', 'type': 'str', 'required': False, 'default': 'TBD'},
		],
		'deps': ['ai_engine', 'template_manager'],
		'module': 'capabilities.proposal_compositor',
		'class': 'ProposalCompositor',
	},
	'course_creator': {
		'description': 'Designs comprehensive course outlines with learning objectives and assessments.',
		'method': 'design_course_outline',
		'params': [
			{'name': 'course_topic', 'type': 'str', 'required': True},
			{'name': 'target_audience', 'type': 'str', 'required': True},
			{'name': 'course_duration_hours', 'type': 'int', 'required': False, 'default': 10},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.course_creator',
		'class': 'CourseCreator',
	},
	'regulatory_change_manager': {
		'description': 'Monitors regulatory changes and assesses business impact.',
		'method': 'monitor_regulatory_changes',
		'params': [
			{'name': 'industry_sector', 'type': 'str', 'required': True},
			{'name': 'jurisdictions', 'type': 'list', 'required': False, 'default': ['US', 'EU']},
			{'name': 'regulation_types', 'type': 'list', 'required': False, 'default': ['data_privacy', 'financial', 'environmental']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.regulatory_change_manager',
		'class': 'RegulatoryChangeManager',
	},
	'crisis_simulation_response_architect': {
		'description': 'Simulates crisis scenarios and builds response playbooks.',
		'method': 'simulate_crisis_scenario',
		'params': [
			{'name': 'crisis_type', 'type': 'str', 'required': True},
			{'name': 'organization_description', 'type': 'str', 'required': True},
			{'name': 'severity_level', 'type': 'str', 'required': False, 'default': 'high'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.crisis_simulation_response_architect',
		'class': 'CrisisSimulationResponseArchitect',
	},
	'ma_target_profiler': {
		'description': 'Profiles M&A acquisition targets with financial and strategic analysis.',
		'method': 'profile_ma_target',
		'params': [
			{'name': 'target_company', 'type': 'str', 'required': True},
			{'name': 'acquirer_profile', 'type': 'str', 'required': True},
			{'name': 'areas_of_interest', 'type': 'list', 'required': False, 'default': ['financials', 'technology', 'market_position']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.ma_target_profiler',
		'class': 'MATargetProfiler',
	},
	'internal_communications_automator': {
		'description': 'Drafts internal communications, memos, and announcements.',
		'method': 'draft_internal_communication',
		'params': [
			{'name': 'communication_type', 'type': 'str', 'required': True},
			{'name': 'key_message', 'type': 'str', 'required': True},
			{'name': 'target_audience', 'type': 'str', 'required': True},
			{'name': 'tone', 'type': 'str', 'required': False, 'default': 'professional'},
		],
		'deps': ['ai_engine', 'template_manager'],
		'module': 'capabilities.internal_communications_automator',
		'class': 'InternalCommunicationsAutomator',
	},
	'talent_analytics_succession_forecaster': {
		'description': 'Predicts succession candidates using talent analytics and HR data.',
		'method': 'predict_succession_candidates',
		'params': [
			{'name': 'role_title', 'type': 'str', 'required': True},
			{'name': 'employee_data_table', 'type': 'str', 'required': False, 'default': 'employees'},
			{'name': 'assessment_criteria', 'type': 'list', 'required': False, 'default': ['performance', 'leadership', 'skills_gap']},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.talent_analytics_succession_forecaster',
		'class': 'TalentAnalyticsSuccessionForecaster',
	},
	'brand_sentiment_orchestrator': {
		'description': 'Analyzes brand sentiment across channels and generates reputation strategies.',
		'method': 'analyze_brand_sentiment',
		'params': [
			{'name': 'brand_name', 'type': 'str', 'required': True},
			{'name': 'analysis_channels', 'type': 'list', 'required': False, 'default': ['news', 'social_media', 'reviews']},
			{'name': 'time_period_days', 'type': 'int', 'required': False, 'default': 30},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.brand_sentiment_orchestrator',
		'class': 'BrandSentimentOrchestrator',
	},
	'intellectual_property_strategist': {
		'description': 'Conducts patent landscape analysis and IP strategy development.',
		'method': 'conduct_patent_landscape_analysis',
		'params': [
			{'name': 'technology_domain', 'type': 'str', 'required': True},
			{'name': 'company_focus', 'type': 'str', 'required': True},
			{'name': 'analysis_scope', 'type': 'list', 'required': False, 'default': ['filing_trends', 'key_players', 'white_spaces']},
		],
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'module': 'capabilities.intellectual_property_strategist',
		'class': 'IntellectualPropertyStrategist',
	},
	'supply_chain_resilience_planner': {
		'description': 'Assesses supply chain risks and builds resilience strategies.',
		'method': 'assess_supply_chain_risks',
		'params': [
			{'name': 'supply_chain_description', 'type': 'str', 'required': True},
			{'name': 'risk_factors', 'type': 'list', 'required': False, 'default': ['geopolitical', 'supplier_concentration', 'logistics', 'demand_volatility']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.supply_chain_resilience_planner',
		'class': 'SupplyChainResiliencePlanner',
	},
	'sustainability_impact_simulator': {
		'description': 'Simulates environmental impact and generates sustainability roadmaps.',
		'method': 'simulate_environmental_impact',
		'params': [
			{'name': 'business_activity_description', 'type': 'str', 'required': True},
			{'name': 'simulation_parameters', 'type': 'list', 'required': False, 'default': ['carbon_emissions', 'water_usage', 'waste_generation']},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.sustainability_impact_simulator',
		'class': 'SustainabilityImpactSimulator',
	},
	'negotiation_strategy_builder': {
		'description': 'Develops BATNA-informed negotiation strategies with tactics and counterarguments.',
		'method': 'develop_negotiation_strategy',
		'params': [
			{'name': 'negotiation_context', 'type': 'str', 'required': True},
			{'name': 'desired_outcomes', 'type': 'list', 'required': True},
			{'name': 'counterparty_profile', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.negotiation_strategy_builder',
		'class': 'NegotiationStrategyBuilder',
	},
	'cultural_transformation_designer': {
		'description': 'Designs organizational culture transformation plans with KPIs and phases.',
		'method': 'design_cultural_transformation_plan',
		'params': [
			{'name': 'current_culture_description', 'type': 'str', 'required': True},
			{'name': 'desired_culture_description', 'type': 'str', 'required': True},
			{'name': 'change_objectives', 'type': 'list', 'required': False, 'default': ['improved_collaboration', 'increased_innovation']},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.cultural_transformation_designer',
		'class': 'CulturalTransformationDesigner',
	},
	'market_sales_research': {
		'description': 'Analyzes market trends, segments, and sales channel opportunities.',
		'method': 'analyze_market_trends',
		'params': [
			{'name': 'product_category', 'type': 'str', 'required': True},
			{'name': 'region', 'type': 'str', 'required': True},
			{'name': 'metrics', 'type': 'list', 'required': False, 'default': ['market_size', 'growth_rate', 'customer_segments']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.market_sales_research',
		'class': 'MarketSalesResearch',
	},
	'psychographic_profile_generator_analyzer': {
		'description': 'Generates detailed psychographic profiles for customer segments.',
		'method': 'generate_customer_psychographic_profile',
		'params': [
			{'name': 'target_segment_description', 'type': 'str', 'required': True},
			{'name': 'profile_dimensions', 'type': 'list', 'required': False, 'default': ['values', 'interests', 'lifestyle', 'personality']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.psychographic_profile_generator_analyzer',
		'class': 'PsychographicProfileGeneratorAnalyzer',
	},
	'website_creator': {
		'description': 'Generates comprehensive website content, copy, and structure.',
		'method': 'generate_website_content',
		'params': [
			{'name': 'website_purpose', 'type': 'str', 'required': True},
			{'name': 'target_audience', 'type': 'str', 'required': True},
			{'name': 'key_features', 'type': 'list', 'required': False, 'default': ['homepage', 'about_us', 'contact_form', 'product_catalog']},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.website_creator',
		'class': 'WebsiteCreator',
	},
	'financial_forecasting_analyst': {
		'description': 'Forecasts financial performance with scenario analysis from historical data.',
		'method': 'forecast_financial_performance',
		'params': [
			{'name': 'financial_data_table', 'type': 'str', 'required': True},
			{'name': 'forecast_metrics', 'type': 'list', 'required': False, 'default': ['revenue_forecast', 'profit_margin_forecast', 'cash_flow_forecast']},
			{'name': 'forecast_period_years', 'type': 'int', 'required': False, 'default': 5},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.financial_forecasting_analyst',
		'class': 'FinancialForecastingAnalyst',
	},
	'customer_support_chatbot_builder': {
		'description': 'Designs customer support chatbot flows with intents, responses, and escalation paths.',
		'method': 'design_chatbot_flow',
		'params': [
			{'name': 'support_area', 'type': 'str', 'required': True},
			{'name': 'common_customer_queries', 'type': 'list', 'required': True},
			{'name': 'desired_chatbot_persona', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.customer_support_chatbot_builder',
		'class': 'CustomerSupportChatbotBuilder',
	},
	'process_optimization_analyst': {
		'description': 'Analyzes process efficiency using Lean/Six Sigma and identifies bottlenecks.',
		'method': 'analyze_process_efficiency',
		'params': [
			{'name': 'process_description', 'type': 'str', 'required': True},
			{'name': 'process_data_table', 'type': 'str', 'required': False, 'default': 'process_data'},
			{'name': 'efficiency_metrics', 'type': 'list', 'required': False, 'default': ['cycle_time', 'resource_utilization', 'error_rate']},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.process_optimization_analyst',
		'class': 'ProcessOptimizationAnalyst',
	},
	'accessibility_compliance_verifier': {
		'description': 'Verifies digital assets against WCAG, Section 508, and ADA accessibility standards.',
		'method': 'verify_accessibility_compliance',
		'params': [
			{'name': 'digital_asset_description', 'type': 'str', 'required': True},
			{'name': 'compliance_standards', 'type': 'list', 'required': False, 'default': ['WCAG', 'Section508', 'ADA']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.accessibility_compliance_verifier',
		'class': 'AccessibilityComplianceVerifier',
	},
	'workflow_automator': {
		'description': 'Designs automated workflow definitions with triggers, actions, and decision nodes.',
		'method': 'create_workflow',
		'params': [
			{'name': 'workflow_name', 'type': 'str', 'required': True},
			{'name': 'description', 'type': 'str', 'required': True},
			{'name': 'triggers', 'type': 'list', 'required': True},
			{'name': 'actions', 'type': 'list', 'required': True},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.WorkflowAutomator',
		'class': 'WorkflowAutomator',
	},
	'customer_relationship_manager': {
		'description': 'Creates and manages customer profiles with CRM intelligence.',
		'method': 'create_customer_profile',
		'params': [
			{'name': 'customer_name', 'type': 'str', 'required': True},
			{'name': 'contact_details', 'type': 'str', 'required': False, 'default': '{}'},
			{'name': 'industry', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.CustomerRelationshipManager',
		'class': 'CustomerRelationshipManager',
	},
	'cybersecurity_guardian': {
		'description': 'Performs vulnerability assessments and generates security hardening recommendations.',
		'method': 'perform_vulnerability_scan',
		'params': [
			{'name': 'system_description', 'type': 'str', 'required': True},
			{'name': 'scan_type', 'type': 'str', 'required': False, 'default': 'quick'},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.CybersecurityGuardian',
		'class': 'CybersecurityGuardian',
	},
	'data_integrator': {
		'description': 'Connects to data sources and generates integration pipeline designs.',
		'method': 'connect_to_data_source',
		'params': [
			{'name': 'source_name', 'type': 'str', 'required': True},
			{'name': 'source_type', 'type': 'str', 'required': True},
			{'name': 'connection_parameters', 'type': 'str', 'required': False, 'default': '{}'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.DataIntegrator',
		'class': 'DataIntegrator',
	},
	'financial_accountant': {
		'description': 'Creates detailed invoices with line items, taxes, and accounting codes.',
		'method': 'create_invoice',
		'params': [
			{'name': 'customer_id', 'type': 'str', 'required': True},
			{'name': 'invoice_items', 'type': 'list', 'required': True},
			{'name': 'invoice_date', 'type': 'str', 'required': True},
			{'name': 'due_date', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.FinancialAccountant',
		'class': 'FinancialAccountant',
	},
	'human_resource_manager': {
		'description': 'Onboards employees with structured plans, training schedules, and 30/60/90-day goals.',
		'method': 'onboard_new_employee',
		'params': [
			{'name': 'employee_name', 'type': 'str', 'required': True},
			{'name': 'job_title', 'type': 'str', 'required': True},
			{'name': 'department', 'type': 'str', 'required': True},
			{'name': 'start_date', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.HumanResourceManager',
		'class': 'HumanResourceManager',
	},
	'legal_compliance_officer': {
		'description': 'Reviews contracts for GDPR, CCPA, HIPAA, and other compliance gaps.',
		'method': 'review_contract_for_compliance',
		'params': [
			{'name': 'contract_text', 'type': 'str', 'required': True},
			{'name': 'compliance_standards', 'type': 'list', 'required': False, 'default': ['GDPR', 'CCPA', 'HIPAA']},
		],
		'deps': ['ai_engine', 'search_engine', 'rag_engine'],
		'module': 'capabilities.LegalComplianceOfficer',
		'class': 'LegalComplianceOfficer',
	},
	'project_task_manager': {
		'description': 'Creates project plans with tasks, milestones, risk register, and team assignments.',
		'method': 'create_project',
		'params': [
			{'name': 'project_name', 'type': 'str', 'required': True},
			{'name': 'description', 'type': 'str', 'required': True},
			{'name': 'team_members', 'type': 'list', 'required': True},
			{'name': 'deadline', 'type': 'str', 'required': True},
		],
		'deps': ['ai_engine', 'db_handler'],
		'module': 'capabilities.ProjectTaskManager',
		'class': 'ProjectTaskManager',
	},
	'code_writer': {
		'description': 'Writes, executes, and debugs code using an agent loop. Supports Python code generation, test writing, code review, and bug fixing.',
		'method': 'write_and_run',
		'params': [
			{'name': 'task_description', 'type': 'str', 'required': True},
			{'name': 'language', 'type': 'str', 'required': False, 'default': 'python'},
			{'name': 'output_file', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.code_writer',
		'class': 'CodeWriter',
	},
	'deep_researcher': {
		'description': (
			'Multi-level research engine: quick (LLM-only), shallow (single search), '
			'medium/deep (agentic loops), comprehensive (multi-angle), '
			'academic (multi-phase orchestration), phd (systematic review + thesis output).'
		),
		'method': 'research',
		'params': [
			{'name': 'query', 'type': 'str', 'required': True},
			{
				'name': 'level',
				'type': 'str',
				'required': False,
				'default': 'medium',
				'choices': ['quick', 'shallow', 'medium', 'deep', 'comprehensive', 'academic', 'phd'],
			},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.deep_researcher',
		'class': 'DeepResearcher',
	},
	'niche_finder': {
		'description': (
			'Strategic niche-finder: maps competitive landscape, identifies underserved user needs, '
			'spots product-market gaps, and synthesises 1-3 concrete niche propositions with '
			'revenue models, GTM paths, and risk assessment.'
		),
		'method': 'find_niches',
		'params': [
			{'name': 'industry', 'type': 'str', 'required': True},
			{
				'name': 'mode',
				'type': 'str',
				'required': False,
				'default': 'research',
				'choices': ['quick', 'research'],
			},
			{'name': 'num_niches', 'type': 'int', 'required': False, 'default': 3},
			{'name': 'focus_area', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.niche_finder',
		'class': 'NicheFinder',
	},
}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_CATEGORY_MAP = {
	'research_assistant': 'research',
	'competitive_intelligence_operative': 'research',
	'ma_target_profiler': 'research',
	'market_sales_research': 'research',
	'psychographic_profile_generator_analyzer': 'research',
	'ai_report_writer': 'content',
	'proposal_compositor': 'content',
	'internal_communications_automator': 'content',
	'website_creator': 'content',
	'course_creator': 'content',
	'customer_support_chatbot_builder': 'content',
	'financial_forecasting_analyst': 'analytics',
	'financial_accountant': 'analytics',
	'process_optimization_analyst': 'analytics',
	'sustainability_impact_simulator': 'analytics',
	'human_resource_manager': 'hr',
	'talent_analytics_succession_forecaster': 'hr',
	'cultural_transformation_designer': 'hr',
	'project_task_manager': 'hr',
	'ethical_ai_governance_engine': 'risk',
	'regulatory_change_manager': 'risk',
	'cybersecurity_guardian': 'risk',
	'legal_compliance_officer': 'risk',
	'accessibility_compliance_verifier': 'risk',
	'crisis_simulation_response_architect': 'risk',
	'negotiation_strategy_builder': 'strategy',
	'brand_sentiment_orchestrator': 'strategy',
	'intellectual_property_strategist': 'strategy',
	'supply_chain_resilience_planner': 'strategy',
	'social_media_manager': 'strategy',
	'workflow_automator': 'strategy',
	'customer_relationship_manager': 'data',
	'data_integrator': 'data',
	'code_writer': 'dev',
	'deep_researcher': 'research',
	'niche_finder': 'strategy',
}


def create_app() -> Flask:
	settings = get_settings()
	app = Flask(__name__, template_folder='templates')
	app.secret_key = settings.get_setting('flask.secret_key', 'thuon-dev-secret-key')
	CORS(app)

	_ICON_MAP = {
		'research': ('🔬', 'rgba(124,106,247,0.15)', '#7c6af7'),
		'content': ('✍️', 'rgba(62,207,207,0.12)', '#3ecfcf'),
		'analytics': ('📊', 'rgba(251,191,36,0.12)', '#fbbf24'),
		'hr': ('👥', 'rgba(52,211,153,0.12)', '#34d399'),
		'risk': ('🛡️', 'rgba(248,113,113,0.12)', '#f87171'),
		'strategy': ('♟️', 'rgba(167,139,250,0.12)', '#a78bfa'),
		'data': ('🔗', 'rgba(96,165,250,0.12)', '#60a5fa'),
		'other': ('⚙️', 'rgba(100,116,139,0.12)', '#64748b'),
	}

	@app.template_filter('categorize')
	def categorize_filter(cap_name: str) -> str:
		return _CATEGORY_MAP.get(cap_name, 'other')

	@app.template_filter('cap_icon')
	def cap_icon_filter(cap_name: str) -> str:
		cat = _CATEGORY_MAP.get(cap_name, 'other')
		return _ICON_MAP.get(cat, _ICON_MAP['other'])[0]

	@app.template_filter('cap_icon_style')
	def cap_icon_style_filter(cap_name: str) -> str:
		cat = _CATEGORY_MAP.get(cap_name, 'other')
		_, bg, color = _ICON_MAP.get(cat, _ICON_MAP['other'])
		return f'background:{bg};border-color:{color}33;'

	# Shared service instances (lazy — created once per process)
	_services: dict = {}

	def _get_services() -> dict:
		if _services:
			return _services
		_services['ai_engine'] = OllamaModel()
		_services['search_engine'] = DuckDuckGoSearch()
		_services['template_manager'] = TemplateManager()
		try:
			_services['db_handler'] = DatabaseHandler()
			_services['db_handler'].connect()
		except Exception:
			_services['db_handler'] = None
		try:
			_services['kg_manager'] = KnowledgeGraphManager.from_settings()
			_services['rag_engine'] = RAGEngine(_services['ai_engine'], _services['kg_manager'])
		except Exception:
			_services['rag_engine'] = None
		return _services

	def _build_instance(cap_name: str):
		cfg = CAPABILITY_REGISTRY[cap_name]
		svc = _get_services()
		import importlib
		mod = importlib.import_module(cfg['module'])
		cls = getattr(mod, cfg['class'])

		dep_map = {
			'ai_engine': svc.get('ai_engine'),
			'search_engine': svc.get('search_engine'),
			'db_handler': svc.get('db_handler'),
			'rag_engine': svc.get('rag_engine'),
			'template_manager': svc.get('template_manager'),
		}
		needed = {d: dep_map[d] for d in cfg['deps'] if d in dep_map and dep_map[d] is not None}

		# Map dep keys to constructor param names
		param_rename = {'db_handler': 'data_handler'}
		kwargs = {param_rename.get(k, k): v for k, v in needed.items()}
		return cls(**kwargs)

	# ---------------------------------------------------------------------------
	# Routes
	# ---------------------------------------------------------------------------

	@app.route('/')
	def index():
		return render_template('index.html', capabilities=CAPABILITY_REGISTRY, category_map=_CATEGORY_MAP)

	@app.route('/capability/<cap_name>')
	def capability_page(cap_name):
		if cap_name not in CAPABILITY_REGISTRY:
			flash(f'Capability "{cap_name}" not found.', 'error')
			return render_template('index.html', capabilities=CAPABILITY_REGISTRY), 404
		return render_template('capability.html', cap_name=cap_name, cap_info=CAPABILITY_REGISTRY[cap_name])

	@app.route('/api/capabilities')
	def list_capabilities():
		return jsonify({
			name: {
				'description': cfg['description'],
				'method': cfg['method'],
				'params': cfg['params'],
				'endpoint': f'/api/{name}',
			}
			for name, cfg in CAPABILITY_REGISTRY.items()
		})

	@app.route('/api/<cap_name>', methods=['POST'])
	def run_capability(cap_name):
		if cap_name not in CAPABILITY_REGISTRY:
			return jsonify({'error': f'Capability "{cap_name}" not found'}), 404

		cfg = CAPABILITY_REGISTRY[cap_name]
		body = request.get_json(force=True, silent=True) or {}

		# Coerce types for list params that arrive as JSON strings
		for p in cfg['params']:
			val = body.get(p['name'])
			if val is not None and p['type'] == 'list' and isinstance(val, str):
				try:
					body[p['name']] = json.loads(val)
				except Exception:
					body[p['name']] = [v.strip() for v in val.split(',') if v.strip()]
				val = body[p['name']]
			elif p['name'] == 'contact_details' and isinstance(val, str):
				try:
					body[p['name']] = json.loads(val)
				except Exception:
					body[p['name']] = {}
			elif p['name'] == 'connection_parameters' and isinstance(val, str):
				try:
					body[p['name']] = json.loads(val)
				except Exception:
					body[p['name']] = {}
			if val is None and not p['required'] and 'default' in p:
				body[p['name']] = p['default']

		t0 = time.time()
		try:
			instance = _build_instance(cap_name)
			method = getattr(instance, cfg['method'])
			import inspect
			sig = inspect.signature(method)
			call_kwargs = {k: v for k, v in body.items() if k in sig.parameters}
			result = method(**call_kwargs)
			elapsed = round(time.time() - t0, 2)
			_run_history.appendleft({
				'cap_name': cap_name, 'params': body,
				'status': 'success', 'elapsed': elapsed,
				'ts': time.time(),
			})
			return jsonify(result)
		except Exception as exc:
			elapsed = round(time.time() - t0, 2)
			_run_history.appendleft({
				'cap_name': cap_name, 'params': body,
				'status': 'error', 'elapsed': elapsed,
				'ts': time.time(),
			})
			return jsonify({'error': str(exc), 'capability': cap_name}), 500

	@app.route('/health')
	def health():
		svc = _get_services()
		status = {
			'status': 'ok',
			'ollama': 'connected' if svc.get('ai_engine') else 'unavailable',
			'postgres': 'connected' if svc.get('db_handler') else 'unavailable',
			'weaviate': 'connected' if svc.get('rag_engine') else 'unavailable',
			'capabilities_registered': len(CAPABILITY_REGISTRY),
		}
		return jsonify(status)

	# ── Natural-language dispatch ──────────────────────────────────────────

	@app.route('/api/do', methods=['POST'])
	def nl_dispatch():
		body = request.get_json(force=True, silent=True) or {}
		instruction = (body.get('instruction') or '').strip()
		if not instruction:
			return jsonify({'error': 'instruction is required'}), 400

		try:
			cap_name, params = _get_router()._route(instruction)
		except Exception:
			cap_name, params = 'research_assistant', {'research_query': instruction}

		if cap_name not in CAPABILITY_REGISTRY:
			return jsonify({'error': f'Could not route instruction to a known capability', 'instruction': instruction}), 422

		cfg = CAPABILITY_REGISTRY[cap_name]
		# Merge any default params
		for p in cfg['params']:
			if p['name'] not in params and not p['required'] and 'default' in p:
				params[p['name']] = p['default']

		t0 = time.time()
		try:
			instance = _build_instance(cap_name)
			method   = getattr(instance, cfg['method'])
			import inspect
			sig        = inspect.signature(method)
			call_kwargs = {k: v for k, v in params.items() if k in sig.parameters}
			result     = method(**call_kwargs)
			elapsed    = round(time.time() - t0, 2)
			_run_history.appendleft({
				'cap_name': cap_name, 'params': params,
				'status': 'success', 'elapsed': elapsed,
				'ts': time.time(),
			})
			return jsonify({'capability': cap_name, 'params': params, 'result': result, 'elapsed': elapsed})
		except Exception as exc:
			elapsed = round(time.time() - t0, 2)
			_run_history.appendleft({
				'cap_name': cap_name, 'params': params,
				'status': 'error', 'elapsed': elapsed,
				'ts': time.time(),
			})
			return jsonify({'error': str(exc), 'capability': cap_name}), 500

	# ── Run history ────────────────────────────────────────────────────────

	@app.route('/api/history')
	def run_history():
		return jsonify(list(_run_history))

	# ── Streaming SSE ──────────────────────────────────────────────────────

	@app.route('/api/stream/<cap_name>', methods=['POST'])
	def stream_capability(cap_name):
		if cap_name not in CAPABILITY_REGISTRY:
			return jsonify({'error': f'Capability "{cap_name}" not found'}), 404

		cfg  = CAPABILITY_REGISTRY[cap_name]
		body = request.get_json(force=True, silent=True) or {}
		for p in cfg['params']:
			val = body.get(p['name'])
			if val is None and not p['required'] and 'default' in p:
				body[p['name']] = p['default']

		def _generate():
			import json as _json, inspect as _inspect
			yield f"data: {_json.dumps({'type': 'start', 'capability': cap_name})}\n\n"
			t0 = time.time()
			try:
				instance    = _build_instance(cap_name)
				method      = getattr(instance, cfg['method'])
				sig         = _inspect.signature(method)
				call_kwargs = {k: v for k, v in body.items() if k in sig.parameters}
				result      = method(**call_kwargs)
				elapsed     = round(time.time() - t0, 2)
				_run_history.appendleft({
					'cap_name': cap_name, 'params': body,
					'status': 'success', 'elapsed': elapsed,
					'ts': time.time(),
				})
				# Yield text fields as token chunks before the done event
				if isinstance(result, dict):
					for _k in ('content', 'report', 'analysis', 'result', 'text', 'summary', 'answer', 'brief'):
						_v = result.get(_k)
						if isinstance(_v, str) and _v:
							for _i in range(0, len(_v), 120):
								yield f"data: {_json.dumps({'type': 'token', 'text': _v[_i:_i+120]})}\n\n"
							break
				yield f"data: {_json.dumps({'type': 'done', 'result': result, 'elapsed': elapsed})}\n\n"
			except Exception as exc:
				yield f"data: {_json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

		from flask import Response
		return Response(_generate(), mimetype='text/event-stream',
		                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

	# ── Export (download file) ─────────────────────────────────────────────

	@app.route('/api/export', methods=['POST'])
	def export_result():
		import tempfile, os as _os
		from flask import send_file
		body   = request.get_json(force=True, silent=True) or {}
		fmt    = body.get('format', 'docx').lower()
		data   = body.get('data') or {}
		title  = body.get('title', 'Thuon Export')

		allowed = {'docx', 'pdf', 'xlsx', 'pptx'}
		if fmt not in allowed:
			return jsonify({'error': f'Unsupported format: {fmt}'}), 400

		try:
			from core.result import ThuonResult
			from flask import after_this_request
			result = ThuonResult(data, 'export')
			import os as _os
			_fd, tmp = tempfile.mkstemp(suffix=f'.{fmt}')
			_os.close(_fd)
			@after_this_request
			def _remove_tmp(response):
				try: _os.unlink(tmp)
				except OSError: pass
				return response
			if fmt == 'docx':
				result.to_docx(tmp)
			elif fmt == 'pdf':
				result.to_pdf(tmp)
			elif fmt == 'xlsx':
				result.to_xlsx(output_path=tmp)
			elif fmt == 'pptx':
				result.to_slides(tmp)
			mime_map = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
			            'pdf':  'application/pdf',
			            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
			            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
			return send_file(tmp, mimetype=mime_map[fmt],
			                 as_attachment=True,
			                 download_name=f'thuon_export.{fmt}')
		except Exception as exc:
			return jsonify({'error': str(exc)}), 500

	# ── Pipelines UI ───────────────────────────────────────────────────────

	@app.route('/pipelines')
	def pipelines_index():
		import glob, yaml as _yaml
		pipelines_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipelines')
		specs = []
		for path in sorted(glob.glob(os.path.join(pipelines_dir, '*.yaml')) +
		                   glob.glob(os.path.join(pipelines_dir, '*.yml'))):
			try:
				with open(path) as f:
					spec = _yaml.safe_load(f)
				specs.append({'name': spec.get('name', os.path.basename(path)),
				              'description': spec.get('description', ''),
				              'steps': spec.get('steps', [])})
			except Exception:
				pass
		return render_template('pipelines.html', pipelines=specs)

	@app.route('/pipeline/<pipe_name>')
	def pipeline_page(pipe_name):
		import yaml as _yaml
		pipelines_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipelines')
		for ext in ('.yaml', '.yml'):
			path = os.path.join(pipelines_dir, pipe_name + ext)
			if os.path.exists(path):
				with open(path) as f:
					spec = _yaml.safe_load(f)
				# Extract {input.x} template vars
				import re
				raw = str(spec)
				inputs = sorted(set(re.findall(r'\{input\.(\w+)\}', raw)))
				return render_template('pipeline_run.html', spec=spec, inputs=inputs, pipe_name=pipe_name)
		flash(f'Pipeline "{pipe_name}" not found.', 'error')
		return render_template('pipelines.html', pipelines=[]), 404

	@app.route('/api/pipeline/<pipe_name>', methods=['POST'])
	def run_pipeline(pipe_name):
		import yaml as _yaml
		body = request.get_json(force=True, silent=True) or {}
		pipelines_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipelines')
		spec = None
		for ext in ('.yaml', '.yml'):
			path = os.path.join(pipelines_dir, pipe_name + ext)
			if os.path.exists(path):
				with open(path) as f:
					spec = _yaml.safe_load(f)
				break
		if spec is None:
			return jsonify({'error': f'Pipeline "{pipe_name}" not found'}), 404

		try:
			sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
			from core.pipeline_runner import PipelineRunner

			class _PlatformShim:
				"""Thin shim so PipelineRunner can call capabilities via web_app._build_instance."""
				def __getattr__(self, name):
					if name in CAPABILITY_REGISTRY:
						cfg = CAPABILITY_REGISTRY[name]
						instance = _build_instance(name)
						method   = getattr(instance, cfg['method'])
						import inspect
						sig = inspect.signature(method)
						def _call(**kwargs):
							call_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
							return method(**call_kwargs)
						return _call
					raise AttributeError(name)

			runner = PipelineRunner(_PlatformShim())
			t0 = time.time()
			step_results = runner.run(spec, body)
			elapsed = round(time.time() - t0, 2)
			return jsonify({'pipeline': pipe_name, 'steps': step_results, 'elapsed': elapsed})
		except Exception as exc:
			return jsonify({'error': str(exc), 'pipeline': pipe_name}), 500

	return app


def run_app(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
	app = create_app()
	app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
	run_app(debug=True)

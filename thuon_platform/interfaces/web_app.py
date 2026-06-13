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
	# ── RFP capabilities ──────────────────────────────────────────────────────
	'rfp_ingester': {
		'description': 'Parse an RFP from URL, file path, or pasted text into structured JSON.',
		'method': 'ingest',
		'params': [{'name': 'rfp_source', 'type': 'str', 'required': True}],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_ingester',
		'class': 'RFPIngester',
	},
	'rfp_compliance_matrix_builder': {
		'description': 'Build a compliance matrix mapping every RFP requirement to a response location.',
		'method': 'build_matrix',
		'params': [
			{'name': 'requirements', 'type': 'str', 'required': True},
			{'name': 'rfp_title', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_compliance_matrix_builder',
		'class': 'RFPComplianceMatrixBuilder',
	},
	'rfp_bid_evaluator': {
		'description': 'Score an RFP for bid/no-bid with win probability and risk assessment.',
		'method': 'evaluate',
		'params': [
			{'name': 'scope_summary', 'type': 'str', 'required': True},
			{'name': 'requirements', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'evaluation_criteria', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'budget', 'type': 'str', 'required': False, 'default': 'Not disclosed'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_bid_evaluator',
		'class': 'RFPBidEvaluator',
	},
	'rfp_customer_researcher': {
		'description': 'Research the RFP issuer\'s strategic priorities, pain points, and budget environment.',
		'method': 'research',
		'params': [
			{'name': 'issuer', 'type': 'str', 'required': True},
			{'name': 'scope_summary', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.rfp_customer_researcher',
		'class': 'RFPCustomerResearcher',
	},
	'rfp_competitor_analyst': {
		'description': 'Identify incumbents, likely bidders, and competitive differentiation angles.',
		'method': 'analyze',
		'params': [
			{'name': 'rfp_title', 'type': 'str', 'required': True},
			{'name': 'scope_summary', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'issuer', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.rfp_competitor_analyst',
		'class': 'RFPCompetitorAnalyst',
	},
	'rfp_win_strategy_builder': {
		'description': 'Build win themes, solution outline, and discriminators from research and criteria.',
		'method': 'build_strategy',
		'params': [
			{'name': 'evaluation_criteria', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'customer_research', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'competitor_analysis', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'rfp_title', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_win_strategy_builder',
		'class': 'RFPWinStrategyBuilder',
	},
	'rfp_section_writer': {
		'description': 'Write one proposal section (executive summary, technical approach, management plan, etc.).',
		'method': 'write_section',
		'params': [
			{'name': 'section_name', 'type': 'str', 'required': True},
			{'name': 'requirements', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'win_themes', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'company_context', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'sow_excerpt', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_section_writer',
		'class': 'RFPSectionWriter',
	},
	'rfp_consistency_checker': {
		'description': 'Red-team check: verify all sections cover the compliance matrix and flag inconsistencies.',
		'method': 'check',
		'params': [
			{'name': 'sections', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'compliance_matrix', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'rfp_title', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_consistency_checker',
		'class': 'RFPConsistencyChecker',
	},
	'rfp_assembler': {
		'description': 'Assemble all proposal sections into a single markdown document and save to disk.',
		'method': 'assemble',
		'params': [
			{'name': 'sections', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'rfp_title', 'type': 'str', 'required': False, 'default': 'RFP Response'},
			{'name': 'rfp_id', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.rfp_assembler',
		'class': 'RFPAssembler',
	},
	# ── Blog capabilities ─────────────────────────────────────────────────────
	'blog_topic_researcher': {
		'description': 'Generate SEO-informed blog topic ideas for a domain and audience.',
		'method': 'research',
		'params': [
			{'name': 'domain', 'type': 'str', 'required': True},
			{'name': 'audience', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'num_topics', 'type': 'int', 'required': False, 'default': 5},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.blog_topic_researcher',
		'class': 'BlogTopicResearcher',
	},
	'blog_outliner': {
		'description': 'Create a structured, SEO-optimized outline for a blog post.',
		'method': 'outline',
		'params': [
			{'name': 'topic', 'type': 'str', 'required': True},
			{'name': 'audience', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'target_length', 'type': 'int', 'required': False, 'default': 1200},
			{'name': 'seo_keyword', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.blog_outliner',
		'class': 'BlogOutliner',
	},
	'blog_section_writer': {
		'description': 'Write a blog section or full post from an outline.',
		'method': 'write',
		'params': [
			{'name': 'heading', 'type': 'str', 'required': True},
			{'name': 'subheadings', 'type': 'list', 'required': False, 'default': []},
			{'name': 'seo_keyword', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'tone', 'type': 'str', 'required': False, 'default': 'authoritative-friendly'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.blog_section_writer',
		'class': 'BlogSectionWriter',
	},
	'blog_seo_optimizer': {
		'description': 'SEO-optimize a complete blog post and save to data/blog/.',
		'method': 'optimize',
		'params': [
			{'name': 'full_content', 'type': 'str', 'required': True},
			{'name': 'target_keyword', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'meta_description', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.blog_seo_optimizer',
		'class': 'BlogSEOOptimizer',
	},
	# ── Website capabilities ──────────────────────────────────────────────────
	'website_content_auditor': {
		'description': 'Fetch and analyze current website page content for quality and SEO.',
		'method': 'audit',
		'params': [
			{'name': 'url', 'type': 'str', 'required': True},
			{'name': 'page_path', 'type': 'str', 'required': False, 'default': '/'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.website_content_auditor',
		'class': 'WebsiteContentAuditor',
	},
	'website_gap_analyzer': {
		'description': 'Identify content gaps, outdated claims, and SEO opportunities on a page.',
		'method': 'analyze',
		'params': [
			{'name': 'current_content', 'type': 'str', 'required': True},
			{'name': 'target_audience', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'page_path', 'type': 'str', 'required': False, 'default': '/'},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.website_gap_analyzer',
		'class': 'WebsiteGapAnalyzer',
	},
	'website_section_writer': {
		'description': 'Rewrite or create compelling website copy for a page or section.',
		'method': 'write',
		'params': [
			{'name': 'section_name', 'type': 'str', 'required': True},
			{'name': 'current_content', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'improvements', 'type': 'list', 'required': False, 'default': []},
			{'name': 'target_audience', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.website_section_writer',
		'class': 'WebsiteSectionWriter',
	},
	'website_seo_optimizer': {
		'description': 'Apply SEO optimization to website page content, generating title tags and meta descriptions.',
		'method': 'optimize',
		'params': [
			{'name': 'content', 'type': 'str', 'required': True},
			{'name': 'page_path', 'type': 'str', 'required': False, 'default': '/'},
			{'name': 'target_keywords', 'type': 'list', 'required': False, 'default': []},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.website_seo_optimizer',
		'class': 'WebsiteSEOOptimizer',
	},
	'website_change_assembler': {
		'description': 'Write finalized website content to the static site repo (human reviews and pushes).',
		'method': 'assemble',
		'params': [
			{'name': 'page_path', 'type': 'str', 'required': False, 'default': '/'},
			{'name': 'optimized_content', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'title_tag', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'meta_description', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.website_change_assembler',
		'class': 'WebsiteChangeAssembler',
	},
	# ── Social media capabilities ─────────────────────────────────────────────
	'social_trend_researcher': {
		'description': 'Research trending context for a social media post idea across platforms.',
		'method': 'research',
		'params': [
			{'name': 'idea', 'type': 'str', 'required': True},
			{'name': 'platforms', 'type': 'list', 'required': False, 'default': ['linkedin', 'twitter']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.social_trend_researcher',
		'class': 'SocialTrendResearcher',
	},
	'social_post_writer': {
		'description': 'Write a platform-specific social media post (LinkedIn, Twitter/X, Instagram).',
		'method': 'write',
		'params': [
			{'name': 'idea', 'type': 'str', 'required': True},
			{'name': 'platform', 'type': 'str', 'required': False, 'default': 'linkedin'},
			{'name': 'context', 'type': 'str', 'required': False, 'default': ''},
			{'name': 'tone', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.social_post_writer',
		'class': 'SocialPostWriter',
	},
	# ── Daily brief ───────────────────────────────────────────────────────────
	'daily_brief': {
		'description': 'Generate a structured daily/weekly digest of news, market signals, and KB highlights.',
		'method': 'generate',
		'params': [
			{'name': 'topics', 'type': 'list', 'required': False, 'default': []},
			{'name': 'focus_areas', 'type': 'list', 'required': False, 'default': []},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.daily_brief',
		'class': 'DailyBrief',
	},
	'company_profile_generator': {
		'description': 'Generate all company KB markdown files from structured interview answers.',
		'method': 'generate',
		'params': [
			{'name': 'interview_answers', 'type': 'dict', 'required': True},
		],
		'deps': ['ai_engine', 'company_profile'],
		'module': 'capabilities.company_profile_generator',
		'class': 'CompanyProfileGenerator',
	},
	'meeting_notes_extractor': {
		'description': 'Extract decisions, action items, and follow-ups from meeting transcripts. Auto-creates tasks and calendar events.',
		'method': 'extract',
		'params': [
			{'name': 'transcript',        'type': 'text',   'required': True},
			{'name': 'meeting_title',     'type': 'string', 'required': False, 'default': ''},
			{'name': 'attendees',         'type': 'string', 'required': False, 'default': ''},
			{'name': 'meeting_date',      'type': 'string', 'required': False, 'default': ''},
			{'name': 'auto_create_tasks', 'type': 'bool',   'required': False, 'default': True},
		],
		'deps': ['ai_engine', 'company_profile'],
		'module': 'capabilities.meeting_notes_extractor',
		'class': 'MeetingNotesExtractor',
	},
	'pre_meeting_brief': {
		'description': 'Generate a pre-meeting brief: attendee profiles, relationship history, talking points, open action items.',
		'method': 'generate',
		'params': [
			{'name': 'attendees',         'type': 'string', 'required': True},
			{'name': 'meeting_purpose',   'type': 'string', 'required': False, 'default': ''},
			{'name': 'meeting_date',      'type': 'string', 'required': False, 'default': ''},
			{'name': 'duration_minutes',  'type': 'int',    'required': False, 'default': 60},
		],
		'deps': ['ai_engine', 'search_engine', 'company_profile'],
		'module': 'capabilities.pre_meeting_brief',
		'class': 'PreMeetingBrief',
	},
	'weekly_review_generator': {
		'description': 'Generate an executive weekly review aggregating RFP pipeline, tasks, calendar, and memory.',
		'method': 'generate',
		'params': [
			{'name': 'week_ending', 'type': 'string', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine', 'company_profile'],
		'module': 'capabilities.weekly_review_generator',
		'class': 'WeeklyReviewGenerator',
	},
	'memory_consolidator': {
		'description': 'Background memory consolidation: extract durable facts from recent activity into USER.md and MEMORY.md.',
		'method': 'consolidate',
		'params': [
			{'name': 'conversation',    'type': 'text', 'required': False, 'default': ''},
			{'name': 'force_full_scan', 'type': 'bool', 'required': False, 'default': False},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.memory_consolidator',
		'class': 'MemoryConsolidator',
	},
	'consulting_research_engine': {
		'description': (
			'McKinsey/BCG-grade research reports from Ollama models. '
			'8-stage pipeline: SCQA framing → MECE issue tree → evidence-first parallel gathering '
			'→ competing hypotheses testing → pyramid synthesis (self-consistency N=3) '
			'→ action title validation → G-Eval quality gate → two-layer output '
			'(executive summary + full analysis).'
		),
		'method': 'research',
		'params': [
			{'name': 'question',        'type': 'text',   'required': True,  'default': ''},
			{'name': 'industry',        'type': 'text',   'required': False, 'default': ''},
			{'name': 'company_context', 'type': 'text',   'required': False, 'default': ''},
			{'name': 'report_type',     'type': 'select', 'required': False, 'default': 'strategy',
			 'options': ['strategy', 'market', 'competitive', 'operational', 'technology', 'ma']},
			{'name': 'output_format',   'type': 'select', 'required': False, 'default': 'both',
			 'options': ['both', 'executive', 'full']},
		],
		'deps': ['ai_engine', 'search_engine'],
		'module': 'capabilities.consulting_research_engine',
		'class': 'ConsultingResearchEngine',
	},
	'long_form_document_engine': {
		'description': (
			'Generates 50,000–200,000-word (100–400+ page) documents of consulting-grade quality. '
			'Architecture: hierarchical outline planning → LaTeX-style two-pass exhibit numbering '
			'→ serial section generation (rolling context + entity-state consistency) '
			'→ cross-reference token resolution → ToC assembly → optional Pandoc PDF render. '
			'Supports Mermaid diagrams, GFM tables, and self-consistency N=3 for key sections.'
		),
		'method': 'generate',
		'params': [
			{'name': 'topic',           'type': 'text',   'required': True,  'default': ''},
			{'name': 'document_type',   'type': 'select', 'required': False, 'default': 'report',
			 'options': ['report', 'whitepaper', 'proposal', 'strategy']},
			{'name': 'target_audience', 'type': 'text',   'required': False, 'default': ''},
			{'name': 'context',         'type': 'textarea', 'required': False, 'default': ''},
			{'name': 'target_pages',    'type': 'number', 'required': False, 'default': 50},
			{'name': 'sections_hint',   'type': 'text',   'required': False, 'default': ''},
			{'name': 'render_pdf',      'type': 'checkbox', 'required': False, 'default': False},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.long_form_document_engine',
		'class': 'LongFormDocumentEngine',
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
	# RFP
	'rfp_ingester': 'strategy',
	'rfp_compliance_matrix_builder': 'strategy',
	'rfp_bid_evaluator': 'strategy',
	'rfp_customer_researcher': 'strategy',
	'rfp_competitor_analyst': 'strategy',
	'rfp_win_strategy_builder': 'strategy',
	'rfp_section_writer': 'strategy',
	'rfp_consistency_checker': 'strategy',
	'rfp_assembler': 'strategy',
	# Blog
	'blog_topic_researcher': 'content',
	'blog_outliner': 'content',
	'blog_section_writer': 'content',
	'blog_seo_optimizer': 'content',
	# Website
	'website_content_auditor': 'content',
	'website_gap_analyzer': 'content',
	'website_section_writer': 'content',
	'website_seo_optimizer': 'content',
	'website_change_assembler': 'content',
	# Social
	'social_trend_researcher': 'content',
	'social_post_writer': 'content',
	# Other
	'daily_brief': 'research',
	'company_profile_generator': 'strategy',
	# Productivity / memory
	'meeting_notes_extractor': 'research',
	'pre_meeting_brief':       'research',
	'weekly_review_generator': 'research',
	'memory_consolidator':     'research',
	# Consulting research engine
	'consulting_research_engine':   'research',
	'long_form_document_engine':    'content',
}


def create_app() -> Flask:
	settings = get_settings()
	app = Flask(__name__, template_folder='templates')
	app.secret_key = settings.get_setting('flask.secret_key', 'thuon-dev-secret-key')
	CORS(app)

	# Start background scheduler (idempotent)
	from core.scheduler import start as _start_scheduler
	_start_scheduler(app)

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
		try:
			from core.company_profile import get_company_profile
			_services['company_profile'] = get_company_profile()
		except Exception:
			_services['company_profile'] = None
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
			'company_profile': svc.get('company_profile'),
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

	# ── RFP tracker ────────────────────────────────────────────────────────────

	@app.route('/rfps')
	def rfps_index():
		from core.rfp_tracker import get_rfp_tracker, RFPStatus
		tracker = get_rfp_tracker()
		by_status = {s.value: tracker.all(status=s.value) for s in RFPStatus}
		return render_template('rfps.html', by_status=by_status, RFPStatus=RFPStatus)

	@app.route('/rfp/<rfp_id>')
	def rfp_detail(rfp_id):
		from core.rfp_tracker import get_rfp_tracker
		tracker = get_rfp_tracker()
		record  = tracker.get(rfp_id)
		if record is None:
			flash(f'RFP {rfp_id!r} not found.', 'error')
			return render_template('rfps.html', by_status={}, RFPStatus=None), 404
		return render_template('rfp_detail.html', record=record)

	@app.route('/api/rfp/discover', methods=['POST'])
	def rfp_discover():
		body   = request.get_json(force=True, silent=True) or {}
		source = body.get('rfp_source', '')
		if not source:
			return jsonify({'error': 'rfp_source required'}), 400
		from core.rfp_tracker import get_rfp_tracker
		from core.notification_bus import get_notification_bus
		tracker = get_rfp_tracker()
		bus     = get_notification_bus()
		try:
			instance = _build_instance('rfp_ingester')
			parsed   = instance.ingest(rfp_source=source)
			record   = tracker.create(
				title=parsed.get('title', 'Untitled RFP'),
				issuer=parsed.get('issuer', 'Unknown'),
				summary=parsed.get('scope_summary', ''),
				source_url=source,
				deadline=parsed.get('deadline'),
			)
			bus.publish('rfp_found', f'New RFP: {record.title}',
			            body=f'Issuer: {record.issuer}', url=f'/rfp/{record.id}')
			return jsonify({'rfp_id': record.id, 'title': record.title,
			                'issuer': record.issuer, 'status': record.status.value})
		except Exception as exc:
			return jsonify({'error': str(exc)}), 500

	@app.route('/api/rfp/<rfp_id>/approve', methods=['POST'])
	def rfp_approve(rfp_id):
		from core.rfp_tracker import get_rfp_tracker
		body   = request.get_json(force=True, silent=True) or {}
		phase  = body.get('phase', '')
		tracker = get_rfp_tracker()
		record  = tracker.get(rfp_id)
		if record is None:
			return jsonify({'error': 'RFP not found'}), 404
		if phase not in ('bid', 'strategy', 'review'):
			return jsonify({'error': f'Unknown phase {phase!r}. Use: bid, strategy, review'}), 400
		try:
			# 'bid' requires two FSM hops: discovered→evaluating→awaiting_strategy
			if phase == 'bid':
				if record.status.value == 'discovered':
					tracker.advance_status(rfp_id, 'evaluating')
				updated = tracker.advance_status(rfp_id, 'awaiting_strategy')
			elif phase == 'strategy':
				updated = tracker.advance_status(rfp_id, 'responding')
			else:  # review
				updated = tracker.advance_status(rfp_id, 'submitted')
			return jsonify(updated.to_dict())
		except ValueError as exc:
			return jsonify({'error': str(exc)}), 422

	@app.route('/api/rfp/<rfp_id>', methods=['PATCH'])
	def rfp_update(rfp_id):
		from core.rfp_tracker import get_rfp_tracker
		body    = request.get_json(force=True, silent=True) or {}
		tracker = get_rfp_tracker()
		record  = tracker.get(rfp_id)
		if record is None:
			return jsonify({'error': 'RFP not found'}), 404
		allowed = {'title', 'issuer', 'summary', 'deadline', 'bid_score',
		           'bid_recommendation', 'response_dir', 'pipeline_step'}
		fields  = {k: v for k, v in body.items() if k in allowed}
		updated = tracker.update(rfp_id, **fields)
		return jsonify(updated.to_dict())

	@app.route('/api/rfps')
	def rfp_list_api():
		from core.rfp_tracker import get_rfp_tracker
		tracker = get_rfp_tracker()
		status  = request.args.get('status')
		return jsonify([r.to_dict() for r in tracker.all(status=status)])

	# ── Content hub ────────────────────────────────────────────────────────────

	@app.route('/content')
	def content_hub():
		from pathlib import Path as _Path
		blog_posts = sorted(
			(_Path(__file__).parent.parent / 'data' / 'blog').glob('*.md'),
			reverse=True,
		)[:10]
		posts = [{'name': p.stem, 'path': str(p)} for p in blog_posts]
		return render_template('content_hub.html', posts=posts)

	@app.route('/content/blog')
	def content_blog():
		from pathlib import Path as _Path
		blog_dir = _Path(__file__).parent.parent / 'data' / 'blog'
		posts    = sorted(blog_dir.glob('*.md'), reverse=True)
		post_list = [{'name': p.stem, 'size': p.stat().st_size} for p in posts]
		return render_template('content_blog.html', posts=post_list)

	@app.route('/content/social')
	def content_social():
		from pathlib import Path as _Path
		ideas_dir = _Path(__file__).parent.parent / 'data' / 'ideas'
		ideas     = []
		if ideas_dir.is_dir():
			ideas = [
				{'name': p.stem, 'text': p.read_text(encoding='utf-8')[:200]}
				for p in sorted(ideas_dir.glob('*.md'), reverse=True)
			]
		return render_template('content_social.html', ideas=ideas)

	@app.route('/content/website')
	def content_website():
		from core.settings_manager import get_settings as _gs
		s     = _gs()
		url   = s.get_setting('website.url', '')
		pages = s.get_setting('website.pages_to_refresh', [])
		from pathlib import Path as _Path
		out_dir  = _Path(__file__).parent.parent / 'data' / 'website_output'
		outfiles = list(out_dir.glob('*.md')) if out_dir.is_dir() else []
		return render_template('content_website.html', url=url, pages=pages,
		                       outfiles=[f.name for f in outfiles])

	@app.route('/api/ideas', methods=['POST'])
	def save_idea():
		import time as _time
		from pathlib import Path as _Path
		body  = request.get_json(force=True, silent=True) or {}
		text  = (body.get('text') or '').strip()
		if not text:
			return jsonify({'error': 'text required'}), 400
		ideas_dir = _Path(__file__).parent.parent / 'data' / 'ideas'
		ideas_dir.mkdir(parents=True, exist_ok=True)
		fname = ideas_dir / f'{_time.strftime("%Y%m%d-%H%M%S")}.md'
		fname.write_text(text, encoding='utf-8')
		return jsonify({'saved': str(fname)})

	# ── Company settings ───────────────────────────────────────────────────────

	@app.route('/settings/company/wizard')
	def company_wizard():
		return render_template('company_wizard.html')

	@app.route('/settings/company')
	def company_settings():
		from core.company_profile import get_company_profile
		profile = get_company_profile()
		files   = profile.list_files()
		selected = request.args.get('file', files[0] if files else '')
		content  = profile.get_file(selected) if selected else ''
		return render_template('company_settings.html',
		                       files=files, selected=selected, content=content)

	@app.route('/api/settings/company/<filename>', methods=['POST'])
	def save_company_file(filename):
		import re as _re
		from pathlib import Path as _Path
		from core.company_profile import get_company_profile
		if not _re.match(r'^[\w\-]+\.md$', filename):
			return jsonify({'error': 'Invalid filename'}), 400
		body    = request.get_json(force=True, silent=True) or {}
		content = body.get('content', '')
		profile = get_company_profile()
		out     = profile._dir / filename
		out.write_text(content, encoding='utf-8')
		profile.reload()
		return jsonify({'saved': filename})

	# ── Notifications (SSE) ────────────────────────────────────────────────────

	@app.route('/api/notifications/stream')
	def notifications_stream():
		from flask import Response
		from core.notification_bus import get_notification_bus
		bus = get_notification_bus()
		return Response(
			bus.stream(),
			mimetype='text/event-stream',
			headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
		)

	@app.route('/api/notifications')
	def notifications_list():
		from core.notification_bus import get_notification_bus
		bus   = get_notification_bus()
		limit = int(request.args.get('limit', 20))
		return jsonify({
			'notifications': bus.history(limit=limit),
			'unread_count':  bus.unread_count(),
		})

	@app.route('/api/notifications/read', methods=['POST'])
	def notifications_mark_read():
		from core.notification_bus import get_notification_bus
		get_notification_bus().mark_all_read()
		return jsonify({'ok': True})

	# ── neditor webhook ────────────────────────────────────────────────────────

	@app.route('/api/neditor/webhook', methods=['POST'])
	def neditor_webhook():
		from core.notification_bus import get_notification_bus
		body  = request.get_json(force=True, silent=True) or {}
		event = body.get('event', '')
		path  = body.get('path', '')
		bus   = get_notification_bus()
		if event == 'exported':
			bus.publish('neditor_exported', 'Document exported', body=path, url='/rfps')
		elif event == 'approved':
			bus.publish('neditor_approved', 'Document approved', body=path)
		return jsonify({'ok': True})

	# ── Jinja2 filters ─────────────────────────────────────────────────────────

	@app.template_filter('todelta')
	def todelta_filter(date_str: str) -> int:
		from datetime import date
		try:
			return (date.fromisoformat(date_str) - date.today()).days
		except Exception:
			return 0

	@app.template_filter('fromts')
	def fromts_filter(ts: int) -> str:
		from datetime import datetime
		try:
			return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
		except Exception:
			return ''

	# ── Tasks ──────────────────────────────────────────────────────────────────

	@app.route('/tasks')
	def tasks_view():
		from core.task_store import get_task_store
		from datetime import date
		store = get_task_store()
		return render_template(
			'tasks.html',
			by_status=store.by_status(),
			stats=store.stats(),
			now_date=date.today().isoformat(),
		)

	@app.route('/api/tasks', methods=['POST'])
	def tasks_create():
		from core.task_store import get_task_store
		body = request.get_json(force=True, silent=True) or {}
		title = body.get('title', '').strip()
		if not title:
			return jsonify({'error': 'title required'}), 400
		task = get_task_store().create(
			title=title,
			notes=body.get('notes', ''),
			priority=int(body.get('priority', 2)),
			due_date=body.get('due_date') or None,
			project=body.get('project', ''),
			tags=body.get('tags', ''),
		)
		return jsonify(task)

	@app.route('/api/tasks/<task_id>', methods=['PATCH'])
	def tasks_update(task_id: str):
		from core.task_store import get_task_store
		body = request.get_json(force=True, silent=True) or {}
		task = get_task_store().update(task_id, **body)
		if task is None:
			return jsonify({'error': 'not found'}), 404
		return jsonify(task)

	@app.route('/api/tasks/<task_id>', methods=['DELETE'])
	def tasks_delete(task_id: str):
		from core.task_store import get_task_store
		ok = get_task_store().delete(task_id)
		return jsonify({'ok': ok})

	@app.route('/api/tasks')
	def tasks_list():
		from core.task_store import get_task_store
		store  = get_task_store()
		status = request.args.get('status')
		tasks  = store.all(status=status, include_completed=request.args.get('all') == '1')
		return jsonify(tasks)

	# ── Calendar ───────────────────────────────────────────────────────────────

	@app.route('/calendar')
	def calendar_view():
		from core.calendar_store import get_calendar_store, EVENT_TYPES
		from datetime import date
		cal   = get_calendar_store()
		today = date.today()
		year  = int(request.args.get('year',  today.year))
		month = int(request.args.get('month', today.month))
		month_evs  = cal.for_month(year, month)
		upcoming   = cal.upcoming(days=30)
		past_cutoff = today.isoformat()
		overdue_evs = [e for e in cal.all(include_past=True) if e['date'] < past_cutoff][-5:]
		return render_template(
			'calendar.html',
			month_events=month_evs,
			upcoming=upcoming,
			overdue_events=overdue_evs,
			upcoming_count=len(upcoming),
			event_types=EVENT_TYPES,
			current_year=year,
			current_month=month,
		)

	@app.route('/api/events', methods=['GET'])
	def events_list():
		from core.calendar_store import get_calendar_store
		cal   = get_calendar_store()
		year  = request.args.get('year')
		month = request.args.get('month')
		if year and month:
			return jsonify(cal.for_month(int(year), int(month)))
		return jsonify(cal.upcoming(days=60))

	@app.route('/api/events', methods=['POST'])
	def events_create():
		from core.calendar_store import get_calendar_store
		body = request.get_json(force=True, silent=True) or {}
		if not body.get('title') or not body.get('date'):
			return jsonify({'error': 'title and date required'}), 400
		ev = get_calendar_store().create(
			title=body['title'],
			date=body['date'],
			event_type=body.get('event_type', 'other'),
			time=body.get('time'),
			notes=body.get('notes', ''),
			ref_id=body.get('ref_id'),
			ref_type=body.get('ref_type'),
			alert_days=body.get('alert_days', '7,1'),
		)
		return jsonify(ev)

	@app.route('/api/events/<event_id>', methods=['PATCH'])
	def events_update(event_id: str):
		from core.calendar_store import get_calendar_store
		body = request.get_json(force=True, silent=True) or {}
		ev   = get_calendar_store().update(event_id, **body)
		if ev is None:
			return jsonify({'error': 'not found'}), 404
		return jsonify(ev)

	@app.route('/api/events/<event_id>', methods=['DELETE'])
	def events_delete(event_id: str):
		from core.calendar_store import get_calendar_store
		ok = get_calendar_store().delete(event_id)
		return jsonify({'ok': ok})

	@app.route('/api/events/sync_rfp', methods=['POST'])
	def events_sync_rfp():
		from core.calendar_store import get_calendar_store
		added = get_calendar_store().sync_rfp_deadlines()
		return jsonify({'added': added})

	# ── Memory ─────────────────────────────────────────────────────────────────

	@app.route('/memory')
	def memory_view():
		from core.memory_store import get_memory_store
		ms = get_memory_store()
		return render_template(
			'memory.html',
			user_content=ms.read_user(),
			mem_content=ms.read_memory(),
			episodes=ms.recent_episodes(limit=30),
			stats=ms.stats(),
		)

	@app.route('/api/memory/<mem_type>', methods=['POST'])
	def memory_save(mem_type: str):
		from core.memory_store import get_memory_store
		if mem_type not in ('user', 'memory'):
			return jsonify({'error': 'invalid type'}), 400
		body    = request.get_json(force=True, silent=True) or {}
		content = body.get('content', '')
		ms      = get_memory_store()
		if mem_type == 'user':
			ms.write_user(content)
		else:
			ms.write_memory(content)
		return jsonify({'saved': mem_type})

	@app.route('/api/memory/<mem_type>/add_fact', methods=['POST'])
	def memory_add_fact(mem_type: str):
		from core.memory_store import get_memory_store
		if mem_type not in ('user', 'memory'):
			return jsonify({'error': 'invalid type'}), 400
		body = request.get_json(force=True, silent=True) or {}
		fact = body.get('fact', '').strip()
		if not fact:
			return jsonify({'error': 'fact required'}), 400
		ms = get_memory_store()
		if mem_type == 'user':
			ms.add_user_fact(fact)
		else:
			ms.add_memory_fact(fact)
		return jsonify({'added': fact})

	@app.route('/api/memory/episodes')
	def memory_episodes():
		from core.memory_store import get_memory_store
		ms    = get_memory_store()
		query = request.args.get('q', '').strip()
		limit = int(request.args.get('limit', 20))
		if query:
			results = ms.search_episodes(query, limit=limit)
		else:
			results = ms.recent_episodes(limit=limit)
		return jsonify(results)

	@app.route('/api/memory/consolidate', methods=['POST'])
	def memory_consolidate():
		from core.memory_store import get_memory_store
		body         = request.get_json(force=True, silent=True) or {}
		conversation = body.get('conversation', '')
		svc          = _get_services()
		try:
			import importlib
			mod  = importlib.import_module('capabilities.memory_consolidator')
			inst = mod.MemoryConsolidator(ai_engine=svc['ai_engine'])
			result = inst.consolidate(
				conversation=conversation,
				force_full_scan=body.get('force_full_scan', not conversation),
			)
		except Exception as exc:
			return jsonify({'error': str(exc)}), 500
		return jsonify(result)

	return app


def run_app(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
	app = create_app()
	app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
	run_app(debug=True)

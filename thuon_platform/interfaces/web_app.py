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
			{'name': 'naics', 'type': 'str', 'required': False, 'default': ''},
		],
		'deps': ['ai_engine', 'search_engine', 'market_signal_provider'],
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
		'deps': ['ai_engine', 'search_engine', 'market_signal_provider'],
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
	'web_fetcher': {
		'description': 'Fetch a URL and return clean extracted text, page title, word count, and outbound links. Supports CSS selector targeting for focused extraction.',
		'method': 'fetch',
		'params': [
			{'name': 'url', 'type': 'str', 'required': True, 'description': 'URL to fetch'},
			{'name': 'extract_text', 'type': 'bool', 'required': False, 'default': True, 'description': 'Use trafilatura to extract clean article text (ignored when selector is set)'},
			{'name': 'selector', 'type': 'str', 'required': False, 'default': '', 'description': 'CSS selector; if provided, extract only matching elements instead of full-page text'},
		],
		'deps': [],
		'module': 'tools.web_fetch',
		'class': 'WebFetcher',
	},
	'web_crawler': {
		'description': 'BFS web crawler that fetches pages starting from a seed URL, extracts title and text content, and follows links up to a configurable page limit.',
		'method': 'crawl',
		'params': [
			{'name': 'seed_url', 'type': 'str', 'required': True, 'description': 'Starting URL for the crawl'},
			{'name': 'max_pages', 'type': 'int', 'required': False, 'default': 5, 'description': 'Maximum number of pages to fetch'},
			{'name': 'same_domain', 'type': 'bool', 'required': False, 'default': True, 'description': 'Restrict crawl to the same domain as seed_url'},
		],
		'deps': [],
		'module': 'tools.web_crawler',
		'class': 'WebCrawler',
	},
	'news_searcher': {
		'description': 'Search recent news articles via DuckDuckGo, filtered to a rolling time window.',
		'method': 'search',
		'params': [
			{'name': 'query', 'type': 'str', 'required': True, 'description': 'News search query string'},
			{'name': 'max_results', 'type': 'int', 'required': False, 'default': 10, 'description': 'Maximum number of raw results to fetch from DuckDuckGo'},
			{'name': 'days_back', 'type': 'int', 'required': False, 'default': 7, 'description': 'Only return articles published within this many days'},
		],
		'deps': [],
		'module': 'tools.news_search',
		'class': 'NewsSearcher',
	},
	'arxiv_searcher': {
		'description': 'Search arXiv for academic papers by query string, with optional category filtering and sort order.',
		'method': 'search',
		'params': [
			{'name': 'query', 'type': 'str', 'required': True, 'description': 'Search terms to look up on arXiv'},
			{'name': 'max_results', 'type': 'int', 'required': False, 'default': 10, 'description': 'Maximum number of papers to return'},
			{'name': 'sort_by', 'type': 'str', 'required': False, 'default': 'relevance', 'description': "Sort order: 'relevance', 'date', or 'citations'"},
			{'name': 'categories', 'type': 'list', 'required': False, 'default': [], 'description': "arXiv category filters, e.g. ['cs.LG', 'stat.ML']"},
		],
		'deps': [],
		'module': 'tools.arxiv_search',
		'class': 'ArxivSearcher',
	},
	'sec_edgar_tool': {
		'description': 'Search SEC EDGAR for company filings (10-K, 10-Q, 8-K, etc.) and retrieve structured XBRL company facts including recent financials.',
		'method': 'search_filings',
		'params': [
			{'name': 'company', 'type': 'str', 'required': True, 'description': 'Company name to search for in SEC EDGAR'},
			{'name': 'form_type', 'type': 'str', 'required': False, 'default': '10-K', 'description': 'SEC form type (e.g. 10-K, 10-Q, 8-K)'},
			{'name': 'max_results', 'type': 'int', 'required': False, 'default': 5, 'description': 'Maximum number of filings to return'},
		],
		'deps': [],
		'module': 'tools.sec_edgar',
		'class': 'SECEdgarTool',
	},
	'pdf_extractor': {
		'description': 'Extract text and metadata from a PDF given a local file path or URL. Supports page range and max_pages limits.',
		'method': 'extract',
		'params': [
			{'name': 'source', 'type': 'str', 'required': True, 'description': 'Local file path or HTTP/HTTPS URL to a PDF file'},
			{'name': 'max_pages', 'type': 'int', 'required': False, 'default': 0, 'description': 'Maximum pages to extract; 0 means all pages'},
			{'name': 'page_range', 'type': 'str', 'required': False, 'default': '', 'description': 'Page range to extract, e.g. "1-5" or "3" (1-indexed); overrides max_pages'},
		],
		'deps': [],
		'module': 'tools.pdf_extractor',
		'class': 'PDFExtractor',
	},
	'excel_reader': {
		'description': 'Read .xlsx and .csv files, returning headers and row data per sheet with optional sheet filtering and row limit.',
		'method': 'read',
		'params': [
			{'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Absolute or relative path to the .xlsx or .csv file.'},
			{'name': 'sheet_name', 'type': 'str', 'required': False, 'default': '', 'description': 'Sheet name to read (xlsx only). Empty string reads all sheets.'},
			{'name': 'max_rows', 'type': 'int', 'required': False, 'default': 500, 'description': 'Maximum rows to return per sheet.'},
		],
		'deps': [],
		'module': 'tools.excel_reader',
		'class': 'ExcelReader',
	},
	'file_writer': {
		'description': 'Read, write, list, and delete files on the local filesystem using stdlib pathlib only.',
		'method': 'write',
		'params': [
			{'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Destination file path to write.'},
			{'name': 'content', 'type': 'str', 'required': True, 'description': 'Text content to write to the file.'},
			{'name': 'mode', 'type': 'str', 'required': False, 'default': 'w', 'description': "File open mode: 'w' (overwrite) or 'a' (append)."},
			{'name': 'create_dirs', 'type': 'bool', 'required': False, 'default': True, 'description': 'Create parent directories if they do not exist.'},
		],
		'deps': [],
		'module': 'tools.file_writer',
		'class': 'FileWriter',
	},
	'whisper_transcriber': {
		'description': 'Transcribe audio/video files to text using OpenAI Whisper, returning full transcript, detected language, timestamped segments, and duration.',
		'method': 'transcribe',
		'params': [
			{'name': 'file_path', 'type': 'str', 'required': True, 'description': 'Path to the audio or video file to transcribe'},
			{'name': 'language', 'type': 'str', 'required': False, 'default': '', 'description': 'BCP-47 language code to force (e.g. "en", "fr"). Empty string lets Whisper auto-detect.'},
			{'name': 'model_size', 'type': 'str', 'required': False, 'default': 'base', 'description': 'Whisper model size: tiny, base, small, medium, large'},
		],
		'deps': [],
		'module': 'tools.whisper_transcribe',
		'class': 'WhisperTranscriber',
	},
	'python_executor': {
		'description': 'Execute arbitrary Python code in an isolated subprocess and return stdout, stderr, returncode, and timing.',
		'method': 'execute',
		'params': [
			{'name': 'code', 'type': 'str', 'required': True, 'description': 'Python source code to execute'},
			{'name': 'timeout', 'type': 'int', 'required': False, 'default': 30, 'description': 'Max execution time in seconds before killing the subprocess'},
		],
		'deps': [],
		'module': 'tools.python_executor',
		'class': 'PythonExecutor',
	},
	'calculator': {
		'description': 'Safe AST-based expression evaluator with math builtins and financial helpers (npv, irr, compound interest, loan payment). Accepts optional variable substitution. Rejects all unsafe AST nodes, attribute access, comprehensions, and unknown names.',
		'method': 'calculate',
		'params': [
			{'name': 'expression', 'type': 'str', 'required': True, 'description': 'Mathematical or financial expression to evaluate, e.g. "sqrt(16) + pi" or "npv(0.1, [100, 200, 300])"'},
			{'name': 'variables', 'type': 'dict', 'required': False, 'default': {}, 'description': 'Optional mapping of variable names to numeric values, e.g. {"x": 3, "y": 7}'},
		],
		'deps': [],
		'module': 'tools.calculator',
		'class': 'Calculator',
	},
	'chart_generator': {
		'description': 'Generate charts (line, bar, pie, scatter, histogram) from data using matplotlib. Returns the image as a file path and base64-encoded PNG.',
		'method': 'generate',
		'params': [
			{'name': 'chart_type', 'type': 'str', 'required': True, 'description': "Chart type: 'line', 'bar', 'pie', 'scatter', or 'histogram'"},
			{'name': 'data', 'type': 'dict', 'required': True, 'description': "Data dict. line/bar: {'labels': list, 'datasets': [{'label': str, 'data': list}]}. pie: {'labels': list, 'values': list}. scatter: {'points': [{'x': float, 'y': float}]} or {'x': list, 'y': list}. histogram: {'values': list, 'bins': int}"},
			{'name': 'title', 'type': 'str', 'required': False, 'default': '', 'description': 'Chart title'},
			{'name': 'xlabel', 'type': 'str', 'required': False, 'default': '', 'description': 'X-axis label'},
			{'name': 'ylabel', 'type': 'str', 'required': False, 'default': '', 'description': 'Y-axis label'},
			{'name': 'output_path', 'type': 'str', 'required': False, 'default': '', 'description': 'Output file path. Defaults to /tmp/thuon_chart_{uuid}.png'},
		],
		'deps': [],
		'module': 'tools.chart_generator',
		'class': 'ChartGenerator',
	},
	'email_reader': {
		'description': 'Read emails from an IMAP mailbox. Returns messages with from, to, subject, date, body (plain text preferred, HTML stripped as fallback), and attachment flag.',
		'method': 'read_inbox',
		'params': [
			{'name': 'folder', 'type': 'str', 'required': False, 'default': 'INBOX', 'description': 'IMAP folder to read from'},
			{'name': 'max_messages', 'type': 'int', 'required': False, 'default': 20, 'description': 'Maximum number of messages to fetch (latest N matching the filter)'},
			{'name': 'search_filter', 'type': 'str', 'required': False, 'default': 'UNSEEN', 'description': 'IMAP search filter (e.g. UNSEEN, ALL, FROM "user@example.com")'},
			{'name': 'mark_read', 'type': 'bool', 'required': False, 'default': False, 'description': 'Mark fetched messages as read (\\Seen flag)'},
		],
		'deps': [],
		'module': 'tools.email_reader',
		'class': 'EmailReader',
	},
	'email_sender': {
		'description': 'Send email via SMTP with optional HTML body, CC recipients, and file attachments.',
		'method': 'send',
		'params': [
			{'name': 'to', 'type': 'str', 'required': True, 'description': 'Recipient email address'},
			{'name': 'subject', 'type': 'str', 'required': True, 'description': 'Email subject line'},
			{'name': 'body', 'type': 'str', 'required': True, 'description': 'Plain text email body'},
			{'name': 'attachments', 'type': 'list', 'required': False, 'default': [], 'description': 'List of file paths to attach'},
			{'name': 'cc', 'type': 'str', 'required': False, 'default': '', 'description': 'CC recipient email address'},
			{'name': 'html_body', 'type': 'str', 'required': False, 'default': '', 'description': 'Optional HTML version of the email body'},
		],
		'deps': [],
		'module': 'tools.email_sender',
		'class': 'EmailSender',
	},
	'calendar_tool': {
		'description': 'Read and create calendar events from/to .ics files. get_events returns upcoming events within a configurable window; create_event appends a new VEVENT to an existing or new .ics file.',
		'method': 'get_events',
		'params': [
			{'name': 'days_ahead', 'type': 'int', 'required': False, 'default': 7, 'description': 'Number of days ahead from now to include events'},
			{'name': 'calendar_path', 'type': 'str', 'required': False, 'default': '', 'description': 'Path to .ics file; falls back to tools.calendar.ics_path config setting'},
		],
		'deps': [],
		'module': 'tools.calendar_tool',
		'class': 'CalendarTool',
	},
	'slack_tool': {
		'description': 'Send a message to a Slack channel via an incoming webhook URL.',
		'method': 'send_message',
		'params': [
			{'name': 'channel', 'type': 'str', 'required': True, 'description': 'Slack channel to post to (e.g. #general)'},
			{'name': 'message', 'type': 'str', 'required': True, 'description': 'Message text to send'},
			{'name': 'webhook_url', 'type': 'str', 'required': False, 'default': '', 'description': 'Incoming webhook URL; overrides tools.slack.webhook_url from config'},
			{'name': 'username', 'type': 'str', 'required': False, 'default': 'Thuon', 'description': 'Display name for the bot message'},
			{'name': 'icon_emoji', 'type': 'str', 'required': False, 'default': ':robot_face:', 'description': 'Emoji icon for the bot message'},
		],
		'deps': [],
		'module': 'tools.slack_tool',
		'class': 'SlackTool',
	},
	'vector_search': {
		'description': 'Semantic vector search and document indexing via chromadb or injected rag_engine',
		'method': 'search',
		'params': [
			{'name': 'query', 'type': 'str', 'required': True, 'description': 'Search query text'},
			{'name': 'collection', 'type': 'str', 'required': False, 'default': 'default', 'description': 'Collection name to search within'},
			{'name': 'max_results', 'type': 'int', 'required': False, 'default': 10, 'description': 'Maximum number of results to return'},
		],
		'deps': ['rag_engine'],
		'module': 'tools.vector_search',
		'class': 'VectorSearchTool',
	},
	'sql_executor': {
		'description': 'Execute SQL queries against the configured database, with readonly mode enforcement and row-count limiting.',
		'method': 'query',
		'params': [
			{'name': 'sql', 'type': 'str', 'required': True, 'description': 'SQL query to execute'},
			{'name': 'params', 'type': 'dict', 'required': False, 'default': {}, 'description': 'Query parameters for parameterised execution'},
			{'name': 'readonly', 'type': 'bool', 'required': False, 'default': True, 'description': 'If True, reject any query not starting with SELECT, WITH, or EXPLAIN'},
			{'name': 'max_rows', 'type': 'int', 'required': False, 'default': 1000, 'description': 'Maximum number of rows to return; excess rows set truncated=True'},
		],
		'deps': ['db_handler'],
		'module': 'tools.sql_executor',
		'class': 'SQLExecutor',
	},
	'browser_agent': {
		'description': 'Headless Chromium browser agent — navigate to a URL, perform actions (click, fill, scroll, press, wait), extract page title and body text, optionally capture a base64-encoded PNG screenshot.',
		'method': 'navigate',
		'params': [
			{'name': 'url', 'type': 'str', 'required': True, 'description': 'URL to navigate to'},
			{'name': 'actions', 'type': 'list', 'required': False, 'default': [], 'description': 'Ordered list of action dicts; each has "type" (click/fill/wait/scroll/press) plus type-specific keys'},
			{'name': 'screenshot', 'type': 'bool', 'required': False, 'default': False, 'description': 'If True, capture a PNG screenshot and return it as base64'},
			{'name': 'timeout', 'type': 'int', 'required': False, 'default': 30, 'description': 'Page load timeout in seconds'},
		],
		'deps': [],
		'module': 'tools.browser_agent',
		'class': 'BrowserAgent',
	},
	'fx_rates_tool': {
		'description': 'Fetch live foreign exchange rates from the ECB XML feed (free, no key) with automatic fallback to exchangerate-api. Supports arbitrary base currency via cross-rate calculation and optional currency filtering.',
		'method': 'get_rates',
		'params': [
			{'name': 'base', 'type': 'str', 'required': False, 'default': 'USD', 'description': 'Base currency code (e.g. USD, EUR, GBP). Cross-rates are computed from the EUR-denominated ECB feed.'},
			{'name': 'currencies', 'type': 'list', 'required': False, 'default': [], 'description': 'Optional list of currency codes to return. Empty list returns all available currencies.'},
			{'name': 'include_metals', 'type': 'bool', 'required': False, 'default': False, 'description': 'If True, adds a note that ECB does not provide metals and points to an alternative source.'},
		],
		'deps': [],
		'module': 'tools.fx_rates',
		'class': 'FXRatesTool',
	},
	# ── World-class additions ─────────────────────────────────────────────────
	'proposal_win_probability': {
		'description': 'Predict win probability for an RFP using historical bid outcomes and AI analysis. Returns predicted win %, confidence, risk factors, and suggested win themes.',
		'method': 'predict',
		'params': [
			{'name': 'scope_summary',  'type': 'str',   'required': True,  'description': 'RFP scope summary'},
			{'name': 'issuer',         'type': 'str',   'required': True,  'description': 'Issuing agency or company'},
			{'name': 'naics',          'type': 'str',   'required': False, 'default': '', 'description': 'NAICS code'},
			{'name': 'bid_score',      'type': 'float', 'required': False, 'default': 0,  'description': 'Bid score from evaluator (0-100)'},
			{'name': 'win_themes',     'type': 'list',  'required': False, 'default': [], 'description': 'Proposed win themes'},
			{'name': 'budget_est',     'type': 'float', 'required': False, 'default': 0,  'description': 'Estimated contract value'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.proposal_win_probability',
		'class': 'ProposalWinProbability',
	},
	'capability_judge': {
		'description': 'A/B test judge: evaluate two capability outputs blind, score both, declare a winner, and auto-promote when one variant has enough wins.',
		'method': 'run_trial',
		'params': [
			{'name': 'capability_name', 'type': 'str', 'required': True,  'description': 'Capability being A/B tested'},
			{'name': 'input_text',      'type': 'str', 'required': True,  'description': 'Input given to both variants'},
			{'name': 'output_a',        'type': 'str', 'required': True,  'description': 'Output from variant A'},
			{'name': 'output_b',        'type': 'str', 'required': True,  'description': 'Output from variant B'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.capability_judge',
		'class': 'CapabilityJudge',
	},
	'pipeline_planner': {
		'description': 'Adaptive pipeline compiler: given a plain-language task description, select and sequence capabilities dynamically. Returns an executable pipeline plan.',
		'method': 'plan',
		'params': [
			{'name': 'task_description',  'type': 'str',  'required': True,  'description': 'What needs to be accomplished'},
			{'name': 'available_inputs',  'type': 'dict', 'required': False, 'default': {}, 'description': 'Known input values'},
			{'name': 'context',           'type': 'str',  'required': False, 'default': '', 'description': 'Additional context'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.pipeline_planner',
		'class': 'PipelinePlanner',
	},
	'proposal_red_team': {
		'description': 'Adversarial proposal evaluation: play the government evaluator, score the proposal, find weaknesses, identify ghosting vulnerabilities before submission.',
		'method': 'evaluate',
		'params': [
			{'name': 'proposal_sections',   'type': 'dict', 'required': True,  'description': 'Dict of {section_name: content}'},
			{'name': 'evaluation_criteria', 'type': 'list', 'required': True,  'description': 'Evaluation criteria from RFP'},
			{'name': 'rfp_requirements',    'type': 'list', 'required': False, 'default': [], 'description': 'Full requirements list'},
			{'name': 'company_context',     'type': 'str',  'required': False, 'default': '', 'description': 'Company KB context'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.proposal_red_team',
		'class': 'ProposalRedTeam',
	},
	'bid_calendar_builder': {
		'description': 'Build a 12-month forward pipeline of likely solicitations by analyzing USASpending.gov contract end-dates and predicting recompetes.',
		'method': 'build_calendar',
		'params': [
			{'name': 'naics_codes',   'type': 'list', 'required': True,  'description': 'NAICS codes to search (e.g. ["541511","541512"])'},
			{'name': 'keywords',      'type': 'list', 'required': False, 'default': [], 'description': 'Additional keywords to filter contracts'},
			{'name': 'months_ahead',  'type': 'int',  'required': False, 'default': 12, 'description': 'How many months forward to look'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.bid_calendar_builder',
		'class': 'BidCalendarBuilder',
	},
	'knowledge_reviewer': {
		'description': 'Review proposed additions to the company knowledge base for consistency and quality before merging. Supports federated team contributions.',
		'method': 'review_contribution',
		'params': [
			{'name': 'file_name',         'type': 'str', 'required': True,  'description': 'Target company KB file (e.g. capabilities.md)'},
			{'name': 'proposed_content',  'type': 'str', 'required': True,  'description': 'New or updated content to review'},
			{'name': 'contributor',       'type': 'str', 'required': False, 'default': 'unknown', 'description': 'Who is submitting this'},
		],
		'deps': ['ai_engine'],
		'module': 'capabilities.knowledge_reviewer',
		'class': 'KnowledgeReviewer',
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
	# Tools
	'web_fetcher':        'research',
	'web_crawler':        'research',
	'news_searcher':      'research',
	'arxiv_searcher':     'research',
	'sec_edgar_tool':     'research',
	'pdf_extractor':      'data',
	'excel_reader':       'data',
	'file_writer':        'data',
	'whisper_transcriber': 'data',
	'python_executor':    'dev',
	'calculator':         'analytics',
	'chart_generator':    'analytics',
	'email_reader':       'data',
	'email_sender':       'data',
	'calendar_tool':      'data',
	'slack_tool':         'data',
	'vector_search':      'research',
	'sql_executor':       'data',
	'browser_agent':      'dev',
	'fx_rates_tool':            'analytics',
	# World-class additions
	'proposal_win_probability': 'strategy',
	'capability_judge':         'dev',
	'pipeline_planner':         'dev',
	'proposal_red_team':        'strategy',
	'bid_calendar_builder':     'strategy',
	'knowledge_reviewer':       'research',
}


def create_app() -> Flask:
	settings = get_settings()
	app = Flask(__name__, template_folder='templates')
	app.secret_key = settings.get_setting('flask.secret_key', 'thuon-dev-secret-key')
	CORS(app)

	# Bootstrap unified skill registry from both hardcoded dicts + SKILL.md discovery
	from core.skill_registry import SkillRegistry
	SkillRegistry.get_instance().bootstrap(CAPABILITY_REGISTRY, _CATEGORY_MAP)

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

	@app.context_processor
	def _inject_sidebar():
		from collections import defaultdict
		cats: dict[str, list[str]] = defaultdict(list)
		for name in CAPABILITY_REGISTRY:
			cat = _CATEGORY_MAP.get(name, 'other')
			cats[cat].append(name)
		_CAT_ORDER = ['research', 'content', 'strategy', 'analytics', 'hr', 'risk', 'data', 'dev', 'other']
		sidebar_groups = [
			(cat, sorted(cats[cat]))
			for cat in _CAT_ORDER
			if cat in cats
		]
		return dict(
			sidebar_groups=sidebar_groups,
			current_path=request.path,
			icon_map=_ICON_MAP,
		)

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
		try:
			from core.memory_store import get_memory_store
			_services['memory_store'] = get_memory_store()
		except Exception:
			_services['memory_store'] = None
		try:
			from core.calendar_store import CalendarStore
			_services['calendar_store'] = CalendarStore()
		except Exception:
			_services['calendar_store'] = None
		try:
			from core.notification_bus import get_notification_bus
			_services['notification_bus'] = get_notification_bus()
		except Exception:
			_services['notification_bus'] = None
		try:
			from core.session_store import SessionStore
			_services['session_store'] = SessionStore(data_handler=_services.get('db_handler'))
		except Exception:
			_services['session_store'] = None
		try:
			from core.market_signal_provider import get_market_signal_provider
			_services['market_signal_provider'] = get_market_signal_provider(
				search_engine=_services.get('search_engine'),
			)
		except Exception:
			_services['market_signal_provider'] = None
		return _services

	def _build_instance(cap_name: str, ai_engine_override=None):
		cfg = CAPABILITY_REGISTRY[cap_name]
		svc = _get_services()
		import importlib
		mod = importlib.import_module(cfg['module'])
		cls = getattr(mod, cfg['class'])

		# Route to the correct model tier when the skill declares one
		if ai_engine_override is None:
			try:
				from core.skill_registry import SkillRegistry
				from core.ai_engine import get_ai_engine
				manifest = SkillRegistry.get_instance().get(cap_name)
				tier = getattr(manifest, 'model_tier', 'standard') if manifest else 'standard'
				if tier and tier != 'standard':
					ai_engine_override = get_ai_engine(tier)
			except Exception:
				pass

		dep_map = {
			'ai_engine': ai_engine_override or svc.get('ai_engine'),
			'search_engine': svc.get('search_engine'),
			'db_handler': svc.get('db_handler'),
			'rag_engine': svc.get('rag_engine'),
			'template_manager': svc.get('template_manager'),
			'company_profile': svc.get('company_profile'),
			'market_signal_provider': svc.get('market_signal_provider'),
		}
		needed = {d: dep_map[d] for d in cfg['deps'] if d in dep_map and dep_map[d] is not None}

		# Map dep keys to constructor param names
		param_rename = {'db_handler': 'data_handler'}
		kwargs = {param_rename.get(k, k): v for k, v in needed.items()}
		return cls(**kwargs)

	# Register MCP blueprint — exposes all capabilities as MCP tools at POST /mcp
	from core.mcp_server import build_mcp_blueprint
	app.register_blueprint(build_mcp_blueprint(_build_instance))
	# Expose factory so the stdio MCP transport (main.py mcp) can reuse it
	app.instance_factory = _build_instance  # type: ignore[attr-defined]

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
		import inspect
		from core.skill_context import build_context
		from core.skill_router import SkillRouter

		body = request.get_json(force=True, silent=True) or {}
		instruction = (body.get('instruction') or '').strip()
		if not instruction:
			return jsonify({'error': 'instruction is required'}), 400

		svc = _get_services()
		router = SkillRouter(ai_engine=svc.get('ai_engine'))

		# Single call returns both name and params atomically — avoids the split-brain
		# where route() and route_with_params() could independently resolve different caps.
		cap_name, params = router.route_with_params(
			instruction,
			allowed_names=set(CAPABILITY_REGISTRY),
		)

		if cap_name not in CAPABILITY_REGISTRY:
			return jsonify({
				'error': 'Could not route instruction to a known capability',
				'instruction': instruction,
			}), 422

		cfg = CAPABILITY_REGISTRY[cap_name]
		for p in cfg['params']:
			if p['name'] not in params and not p.get('required') and 'default' in p:
				params[p['name']] = p['default']

		# Render SKILL.md body — substitute $ARGUMENTS with the original instruction
		# and inject into any 'prompt' param the capability accepts.
		from core.skill_registry import SkillRegistry
		manifest   = SkillRegistry.get_instance().get(cap_name)
		skill_prompt: str | None = None
		if manifest and manifest.body:
			skill_prompt = manifest.body.replace('$ARGUMENTS', instruction)

		t0 = time.time()
		try:
			instance = _build_instance(cap_name)
			method   = getattr(instance, cfg['method'])
			sig      = inspect.signature(method)

			# Inject SkillContext if the method declares a `context` parameter
			call_kwargs = {k: v for k, v in params.items() if k in sig.parameters}
			# Inject rendered SKILL.md body as 'prompt' without polluting params
			if skill_prompt and 'prompt' in sig.parameters and 'prompt' not in call_kwargs:
				call_kwargs['prompt'] = skill_prompt
			if 'context' in sig.parameters:
				session_id = request.headers.get('X-Session-Id', '')
				call_kwargs['context'] = build_context(svc, session_id=session_id)

			result  = method(**call_kwargs)
			elapsed = round(time.time() - t0, 2)
			_run_history.appendleft({
				'cap_name': cap_name, 'params': params,
				'status': 'success', 'elapsed': elapsed,
				'ts': time.time(),
			})
			return jsonify({
				'capability':   cap_name,
				'params':       params,
				'result':       result,
				'elapsed':      elapsed,
				'routed_by':    'skill_router',
				'skill_prompt': skill_prompt,
			})
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

			class _StreamProxy:
				"""Wraps an AIModel; intercepts generate_text to emit live tokens."""
				def __init__(self, real_engine, token_buf: list):
					self._real    = real_engine
					self._buf     = token_buf
				def generate_text(self, prompt, generation_parameters={}):
					if hasattr(self._real, 'generate_stream'):
						full = ''
						for tok in self._real.generate_stream(prompt):
							full += tok
							self._buf.append(tok)
						return full
					return self._real.generate_text(prompt, generation_parameters)
				def __getattr__(self, name):
					return getattr(self._real, name)

			yield f"data: {_json.dumps({'type': 'start', 'capability': cap_name})}\n\n"
			t0 = time.time()
			token_buf: list[str] = []
			real_engine = _get_services().get('ai_engine')
			proxy = _StreamProxy(real_engine, token_buf) if real_engine is not None else None
			try:
				instance    = _build_instance(cap_name, ai_engine_override=proxy)
				method      = getattr(instance, cfg['method'])
				sig         = _inspect.signature(method)
				call_kwargs = {k: v for k, v in body.items() if k in sig.parameters}

				# For live streaming: run the capability and interleave tokens as they arrive
				# token_buf is populated by _StreamProxy.generate_text during method execution
				result = method(**call_kwargs)
				elapsed = round(time.time() - t0, 2)
				_run_history.appendleft({
					'cap_name': cap_name, 'params': body,
					'status': 'success', 'elapsed': elapsed,
					'ts': time.time(),
				})
				# Emit tokens collected during generation (live if model streamed, post-hoc otherwise)
				if token_buf:
					for tok in token_buf:
						if tok:
							yield f"data: {_json.dumps({'type': 'token', 'text': tok})}\n\n"
				elif isinstance(result, dict):
					# Fallback chunking for non-streaming engines
					for _k in ('content', 'report', 'analysis', 'result', 'text', 'summary', 'answer', 'brief'):
						_v = result.get(_k)
						if isinstance(_v, str) and _v:
							for _i in range(0, len(_v), 80):
								yield f"data: {_json.dumps({'type': 'token', 'text': _v[_i:_i+80]})}\n\n"
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
		from core.bundle import writable_data_dir as _wdd
		blog_posts = sorted((_wdd() / 'blog').glob('*.md'), reverse=True)[:10]
		posts = [{'name': p.stem, 'path': str(p)} for p in blog_posts]
		return render_template('content_hub.html', posts=posts)

	@app.route('/content/blog')
	def content_blog():
		from core.bundle import writable_data_dir as _wdd
		blog_dir = _wdd() / 'blog'
		posts    = sorted(blog_dir.glob('*.md'), reverse=True)
		post_list = [{'name': p.stem, 'size': p.stat().st_size} for p in posts]
		return render_template('content_blog.html', posts=post_list)

	@app.route('/content/social')
	def content_social():
		from core.bundle import writable_data_dir as _wdd
		ideas_dir = _wdd() / 'ideas'
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
		from core.bundle import writable_data_dir as _wdd
		out_dir  = _wdd() / 'website_output'
		outfiles = list(out_dir.glob('*.md')) if out_dir.is_dir() else []
		return render_template('content_website.html', url=url, pages=pages,
		                       outfiles=[f.name for f in outfiles])

	@app.route('/api/ideas', methods=['POST'])
	def save_idea():
		import time as _time
		from core.bundle import writable_data_dir as _wdd
		body  = request.get_json(force=True, silent=True) or {}
		text  = (body.get('text') or '').strip()
		if not text:
			return jsonify({'error': 'text required'}), 400
		ideas_dir = _wdd() / 'ideas'
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
		import hashlib, hmac as _hmac
		from core.notification_bus import get_notification_bus
		from core.settings_manager import get_settings

		secret = (get_settings().get('neditor', {}).get('webhook_secret') or '').encode()
		if secret:
			sig   = request.headers.get('X-Neditor-Signature', '')
			body_bytes = request.get_data(cache=True)
			expected = 'sha256=' + _hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
			if not _hmac.compare_digest(sig, expected):
				return jsonify({'error': 'invalid signature'}), 401
			body = (request.get_json(force=True, silent=True) or {})
		else:
			body = request.get_json(force=True, silent=True) or {}

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

	# ── CRM ────────────────────────────────────────────────────────────────────

	@app.route('/crm')
	def crm_index():
		from core.crm_store import get_crm_store
		store = get_crm_store()
		contacts = store.search_contacts(limit=50)
		return render_template('crm.html', contacts=contacts)

	@app.route('/api/crm/contacts', methods=['GET'])
	def crm_contacts_list():
		from core.crm_store import get_crm_store
		store = get_crm_store()
		q     = request.args.get('q', '')
		limit = int(request.args.get('limit', 50))
		contacts = store.search_contacts(query=q, limit=limit) if q else store.search_contacts(limit=limit)
		return jsonify({'contacts': contacts})

	@app.route('/api/crm/contacts', methods=['POST'])
	def crm_contact_create():
		from core.crm_store import get_crm_store
		body  = request.get_json(force=True, silent=True) or {}
		store = get_crm_store()
		cid   = store.upsert_contact(
			name=body.get('name', ''),
			email=body.get('email', ''),
			phone=body.get('phone', ''),
			org_name=body.get('org_name', ''),
			role=body.get('role', ''),
			notes=body.get('notes', ''),
		)
		return jsonify({'id': cid}), 201

	@app.route('/api/crm/contacts/<contact_id>', methods=['GET'])
	def crm_contact_get(contact_id):
		from core.crm_store import get_crm_store
		c = get_crm_store().get_contact(contact_id)
		if c is None:
			return jsonify({'error': 'not found'}), 404
		return jsonify(c)

	@app.route('/api/crm/contacts/<contact_id>/interactions', methods=['POST'])
	def crm_log_interaction(contact_id):
		from core.crm_store import get_crm_store
		body  = request.get_json(force=True, silent=True) or {}
		store = get_crm_store()
		iid   = store.log_interaction(
			contact_id=contact_id,
			interaction_type=body.get('type', 'note'),
			summary=body.get('summary', ''),
			rfp_id=body.get('rfp_id'),
		)
		return jsonify({'id': iid}), 201

	@app.route('/api/crm/orgs', methods=['POST'])
	def crm_org_upsert():
		from core.crm_store import get_crm_store
		body  = request.get_json(force=True, silent=True) or {}
		store = get_crm_store()
		oid   = store.upsert_org(
			name=body.get('name', ''),
			org_type=body.get('type', 'agency'),
			certifications=body.get('certifications', []),
			notes=body.get('notes', ''),
		)
		return jsonify({'id': oid}), 201

	# ── Voice / audio intake ────────────────────────────────────────────────────

	@app.route('/api/voice', methods=['POST'])
	def voice_invoke():
		"""
		Transcribe an audio file then route the text through the SkillRegistry.
		Accepts multipart/form-data with an 'audio' file field, or JSON with
		{'audio_path': '/abs/path/to/file.wav'}.
		Returns the capability result plus the transcription.
		"""
		import tempfile, os
		from core.skill_registry import SkillRegistry

		# Resolve audio bytes or path
		audio_path: str | None = None
		tmp_path:   str | None = None

		if 'audio' in request.files:
			f = request.files['audio']
			suffix = os.path.splitext(f.filename or '.wav')[1] or '.wav'
			with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
				f.save(tmp)
				audio_path = tmp.name
				tmp_path   = tmp.name
		else:
			body = request.get_json(force=True, silent=True) or {}
			audio_path = body.get('audio_path')

		if not audio_path:
			return jsonify({'error': 'No audio provided. Send multipart audio field or JSON audio_path.'}), 400

		try:
			# Step 1: transcribe
			svc = _get_services()
			import importlib
			whisper_mod  = importlib.import_module('tools.whisper_transcriber')
			transcription = whisper_mod.WhisperTranscriber().transcribe(audio_path)
			text = transcription if isinstance(transcription, str) else transcription.get('text', '')

			# Step 2: route through skill registry
			registry = SkillRegistry.get_instance()
			match     = registry.find_best(text)
			if match is None:
				return jsonify({'transcription': text, 'error': 'No matching capability found'}), 200

			cap_name = match['name']
			proxy    = getattr(svc['platform'], cap_name, None)
			if proxy is None:
				return jsonify({'transcription': text, 'error': f'Capability {cap_name} not available'}), 200

			result = proxy(text)
			return jsonify({
				'transcription': text,
				'capability':    cap_name,
				'result':        result if isinstance(result, dict) else {'output': str(result)},
			})
		finally:
			if tmp_path and os.path.exists(tmp_path):
				os.unlink(tmp_path)

	# ── Federated KB contribution ───────────────────────────────────────────────

	@app.route('/settings/company/contribute')
	def kb_contribute_page():
		from core.company_profile import get_company_profile
		files = get_company_profile().list_files()
		return render_template('kb_contribute.html', files=files)

	@app.route('/api/kb/contribute', methods=['POST'])
	def kb_contribute():
		"""
		Submit a proposed KB update for AI review before merging.
		Body: {file_name, proposed_content, contributor}
		Returns the KnowledgeReviewer verdict.
		"""
		body        = request.get_json(force=True, silent=True) or {}
		file_name   = body.get('file_name', '')
		proposed    = body.get('proposed_content', '')
		contributor = body.get('contributor', 'anonymous')

		if not file_name or not proposed:
			return jsonify({'error': 'file_name and proposed_content are required'}), 400

		svc = _get_services()
		try:
			import importlib
			mod  = importlib.import_module('capabilities.knowledge_reviewer')
			inst = mod.KnowledgeReviewer(ai_engine=svc['ai_engine'])
			result = inst.review_contribution(
				file_name=file_name,
				proposed_content=proposed,
				contributor=contributor,
			)
		except Exception as exc:
			return jsonify({'error': str(exc)}), 500
		return jsonify(result)

	# ── Pipeline resume ─────────────────────────────────────────────────────────

	@app.route('/api/pipeline/<run_id>/resume', methods=['POST'])
	def pipeline_resume(run_id):
		"""Resume a checkpointed pipeline run from the last successful step."""
		from core.pipeline_checkpoint_store import get_checkpoint_store
		store = get_checkpoint_store()
		run   = store.get_run(run_id)
		if run is None:
			return jsonify({'error': f'Run {run_id} not found'}), 404

		svc          = _get_services()
		pipeline_name = run['pipeline_name']
		inputs        = run.get('inputs') or {}
		try:
			result = svc['platform'].pipeline_runner.run(
				pipeline_name,
				inputs=inputs,
				run_id=run_id,
			)
		except Exception as exc:
			return jsonify({'error': str(exc)}), 500

		return jsonify({'run_id': run_id, 'result': result if isinstance(result, dict) else {'output': str(result)}})

	return app


def run_app(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
	app = create_app()
	app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
	run_app(debug=True)

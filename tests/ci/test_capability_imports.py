# tests/ci/test_capability_imports.py
# Verify all capability modules import without error and have expected class/method

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import importlib
import inspect

CAPABILITY_MAP = {
	'capabilities.research_assistant': ('ResearchAssistant', 'perform_research'),
	'capabilities.ai_report_writer': ('AIReportWriter', 'generate_report'),
	'capabilities.competitive_intelligence_operative': ('CompetitiveIntelligenceOperative', 'analyze_competitor_landscape'),
	'capabilities.ethical_ai_governance_engine': ('EthicalAIGovernanceEngine', 'assess_ethical_risks'),
	'capabilities.social_media_manager': ('SocialMediaManager', 'analyze_social_trends'),
	'capabilities.proposal_compositor': ('ProposalCompositor', 'compose_proposal'),
	'capabilities.course_creator': ('CourseCreator', 'design_course_outline'),
	'capabilities.regulatory_change_manager': ('RegulatoryChangeManager', 'monitor_regulatory_changes'),
	'capabilities.crisis_simulation_response_architect': ('CrisisSimulationResponseArchitect', 'simulate_crisis_scenario'),
	'capabilities.ma_target_profiler': ('MATargetProfiler', 'profile_ma_target'),
	'capabilities.internal_communications_automator': ('InternalCommunicationsAutomator', 'draft_internal_communication'),
	'capabilities.talent_analytics_succession_forecaster': ('TalentAnalyticsSuccessionForecaster', 'predict_succession_candidates'),
	'capabilities.brand_sentiment_orchestrator': ('BrandSentimentOrchestrator', 'analyze_brand_sentiment'),
	'capabilities.intellectual_property_strategist': ('IntellectualPropertyStrategist', 'conduct_patent_landscape_analysis'),
	'capabilities.supply_chain_resilience_planner': ('SupplyChainResiliencePlanner', 'assess_supply_chain_risks'),
	'capabilities.sustainability_impact_simulator': ('SustainabilityImpactSimulator', 'simulate_environmental_impact'),
	'capabilities.negotiation_strategy_builder': ('NegotiationStrategyBuilder', 'develop_negotiation_strategy'),
	'capabilities.cultural_transformation_designer': ('CulturalTransformationDesigner', 'design_cultural_transformation_plan'),
	'capabilities.market_sales_research': ('MarketSalesResearch', 'analyze_market_trends'),
	'capabilities.psychographic_profile_generator_analyzer': ('PsychographicProfileGeneratorAnalyzer', 'generate_customer_psychographic_profile'),
	'capabilities.website_creator': ('WebsiteCreator', 'generate_website_content'),
	'capabilities.financial_forecasting_analyst': ('FinancialForecastingAnalyst', 'forecast_financial_performance'),
	'capabilities.customer_support_chatbot_builder': ('CustomerSupportChatbotBuilder', 'design_chatbot_flow'),
	'capabilities.process_optimization_analyst': ('ProcessOptimizationAnalyst', 'analyze_process_efficiency'),
	'capabilities.accessibility_compliance_verifier': ('AccessibilityComplianceVerifier', 'verify_accessibility_compliance'),
	'capabilities.WorkflowAutomator': ('WorkflowAutomator', 'create_workflow'),
	'capabilities.CustomerRelationshipManager': ('CustomerRelationshipManager', 'create_customer_profile'),
	'capabilities.CybersecurityGuardian': ('CybersecurityGuardian', 'perform_vulnerability_scan'),
	'capabilities.DataIntegrator': ('DataIntegrator', 'connect_to_data_source'),
	'capabilities.FinancialAccountant': ('FinancialAccountant', 'create_invoice'),
	'capabilities.HumanResourceManager': ('HumanResourceManager', 'onboard_new_employee'),
	'capabilities.LegalComplianceOfficer': ('LegalComplianceOfficer', 'review_contract_for_compliance'),
	'capabilities.ProjectTaskManager': ('ProjectTaskManager', 'create_project'),
}


def test_all_capabilities_importable():
	failures = []
	for module_path, (class_name, method_name) in CAPABILITY_MAP.items():
		try:
			mod = importlib.import_module(module_path)
			cls = getattr(mod, class_name, None)
			assert cls is not None, f'{module_path}: class {class_name} not found'
			assert hasattr(cls, method_name), f'{module_path}.{class_name}: method {method_name} not found'
			assert callable(getattr(cls, method_name)), f'{method_name} is not callable'
		except Exception as e:
			failures.append(f'{module_path}: {e}')
	assert not failures, '\n'.join(failures)

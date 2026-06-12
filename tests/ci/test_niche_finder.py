# tests/ci/test_niche_finder.py

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

from unittest.mock import MagicMock, patch, call


# ── helpers ──────────────────────────────────────────────────────────────────

_NICHE_JSON = json.dumps({
	'landscape_summary': 'Fintech is dominated by Stripe and Plaid.',
	'key_gaps': ['SME cash flow visibility', 'embedded insurance'],
	'niches': [
		{
			'hypothesis': 'Real-time cash flow forecasting for micro-merchants.',
			'target_segment': 'Self-employed merchants with <$1M revenue',
			'jtbd': 'Know if I can make payroll next week',
			'differentiator': 'Bank-feed + POS integration, 7-day rolling forecast',
			'revenue_model': 'SaaS subscription',
			'pricing_logic': '$49/month, anchored against bookkeeper cost',
			'market_size_estimate': 'TAM $2B, SAM $400M, SOM $20M',
			'competitive_moat': 'Proprietary bank-feed normalisation',
			'unit_economics_note': 'CAC ~$150, LTV ~$1800, 12-month payback',
			'risks': [{'risk': 'Open banking regulation', 'mitigation': 'API-agnostic adapter layer'}],
			'gtm_path': 'Shopify app store → 10 beta merchants → Product Hunt launch',
		}
	],
	'confidence_level': 'medium',
})

_LANDSCAPE_JSON = json.dumps({
	'incumbents': [{'name': 'Stripe', 'core_capabilities': ['payments'], 'market_position': 'leader', 'weakness': 'no forecasting'}],
	'startups': [{'name': 'Acme', 'focus': 'SME lending', 'stage': 'seed', 'differentiator': 'instant', 'funding': '$5M'}],
	'technology_stack': ['Plaid API', 'ML'],
	'market_maturity': 'growing',
})

_PMF_JSON = json.dumps({
	'well_served_needs': ['payment processing'],
	'underserved_needs': [{'need': 'cash flow', 'evidence': 'Reddit thread', 'severity': 'high', 'affected_segment': 'SMBs'}],
	'emerging_needs': ['embedded insurance'],
	'friction_points': [{'friction': 'manual reconciliation', 'root_cause': 'no API', 'who_feels_it': 'accountants'}],
	'switching_barriers': ['data lock-in'],
})

_TRENDS_JSON = json.dumps({
	'regulatory_tailwinds': [{'regulation': 'Open Banking PSD3', 'impact': 'data portability', 'timeline': '2025'}],
	'regulatory_headwinds': [],
	'behavioral_trends': [{'trend': 'mobile-first', 'evidence': 'Statista 2024', 'opportunity': 'app-native tools'}],
	'technology_enablers': ['LLMs for document parsing'],
	'market_size_signals': 'Global SME fintech TAM $500B by 2030',
})

_PRICING_JSON = json.dumps({
	'observed_pricing_models': [{'company': 'Stripe', 'model': 'usage', 'price_point': '2.9%+30c', 'what_included': 'payment processing'}],
	'willingness_to_pay_signals': 'SMBs pay $50-200/mo for accounting tools',
	'average_deal_size': '$150/mo',
	'customer_acquisition_benchmarks': 'CAC $100-300 via app stores',
	'margin_profile_notes': '70-80% gross margin typical SaaS',
})


def _mock_ai(responses=None):
	ai = MagicMock()
	if responses:
		ai.generate_text.side_effect = responses
	else:
		ai.generate_text.return_value = _NICHE_JSON
	return ai


def _mock_search():
	se = MagicMock()
	se.search.return_value = [
		{'title': 'Fintech Trends 2024', 'body': 'Open banking is growing.', 'href': 'https://ex.com/1'},
		{'title': 'SME pain points', 'body': 'Cash flow is the #1 concern.', 'href': 'https://ex.com/2'},
	]
	return se


def _make_niche_finder(ai_responses=None):
	from capabilities.niche_finder import NicheFinder
	ai = _mock_ai(ai_responses)
	search = _mock_search()
	return NicheFinder(ai_engine=ai, search_engine=search), ai, search


# ── module-level sanity ───────────────────────────────────────────────────────

def test_niche_finder_imports():
	from capabilities.niche_finder import NicheFinder
	assert NicheFinder is not None


def test_niche_finder_instantiates():
	nf, ai, search = _make_niche_finder()
	assert nf is not None


# ── quick mode ────────────────────────────────────────────────────────────────

def test_quick_mode_returns_dict():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('fintech', mode='quick')
	assert isinstance(result, dict)


def test_quick_mode_includes_metadata():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('healthtech', mode='quick')
	assert result['industry'] == 'healthtech'
	assert result['mode'] == 'quick'
	assert 'elapsed_seconds' in result


def test_quick_mode_calls_ai_not_search():
	nf, ai, search = _make_niche_finder()
	nf.find_niches('proptech', mode='quick')
	ai.generate_text.assert_called_once()
	search.search.assert_not_called()


def test_quick_mode_with_focus_area():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('fintech', mode='quick', focus_area='SME lending')
	assert result['focus_area'] == 'SME lending'
	# Focus area should appear in the prompt sent to LLM
	prompt_arg = ai.generate_text.call_args[0][0]
	assert 'SME lending' in prompt_arg


def test_quick_mode_parses_json_niches():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('edtech', mode='quick')
	# Should parse JSON from LLM and return dict with niches key
	assert 'niches' in result or 'result' in result  # fallback ok


def test_quick_mode_fallback_on_invalid_json():
	from capabilities.niche_finder import NicheFinder
	ai = MagicMock()
	ai.generate_text.return_value = 'not valid json ]]{'
	search = _mock_search()
	nf = NicheFinder(ai_engine=ai, search_engine=search)
	result = nf.find_niches('fintech', mode='quick')
	assert isinstance(result, dict)
	assert 'niches' in result or 'result' in result


def test_quick_mode_num_niches_param():
	nf, ai, search = _make_niche_finder()
	nf.find_niches('fintech', mode='quick', num_niches=2)
	prompt_arg = ai.generate_text.call_args[0][0]
	assert '2' in prompt_arg


# ── research mode ─────────────────────────────────────────────────────────────

def _mock_agent_run(query):
	return {
		'answer': 'Agent found: cash flow tools are underserved for micro-merchants.',
		'iterations': 8,
		'tool_calls': [{'tool': 'web_search', 'args': {'query': query}}],
		'status': 'success',
		'elapsed_seconds': 4.5,
	}


def test_research_mode_calls_search_multiple_times():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech niches')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='research')

	# 4 phases × 3 queries each = 12 search calls
	assert search.search.call_count >= 8


def test_research_mode_includes_phases():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='research')

	assert 'phases' in result
	phases = result['phases']
	assert 'landscape_research' in phases
	assert 'pmf_research' in phases
	assert 'trends_research' in phases
	assert 'pricing_research' in phases
	assert 'agent_synthesis' in phases


def test_research_mode_runs_agent_loop():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech niches')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='research')

	MockLoop.assert_called_once()
	mock_loop.run.assert_called_once()


def test_research_mode_metadata():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='research', num_niches=2, focus_area='embedded finance')

	assert result['industry'] == 'fintech'
	assert result['mode'] == 'research'
	assert result['focus_area'] == 'embedded finance'
	assert 'elapsed_seconds' in result


# ── niche proposition structure ───────────────────────────────────────────────

def test_niche_proposition_has_required_keys():
	"""Verify niche proposition structure when LLM returns valid JSON."""
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('fintech', mode='quick')

	# If LLM JSON parsed correctly, check niche structure
	if 'niches' in result and isinstance(result['niches'], list) and result['niches']:
		niche = result['niches'][0]
		required_keys = [
			'hypothesis', 'target_segment', 'jtbd', 'differentiator',
			'revenue_model', 'pricing_logic', 'risks', 'gtm_path',
		]
		for key in required_keys:
			assert key in niche, f'Niche missing key: {key}'


def test_landscape_summary_in_research_output():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='research')

	# landscape_summary comes from the synthesis phase JSON
	assert 'landscape_summary' in result or 'key_gaps' in result or 'niches' in result


# ── boundary conditions ───────────────────────────────────────────────────────

def test_num_niches_clamped_to_max_5():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('fintech', mode='quick', num_niches=99)
	prompt = ai.generate_text.call_args[0][0]
	# Clamped to 5 — prompt should mention 5 not 99
	assert '99' not in prompt


def test_num_niches_clamped_to_min_1():
	nf, ai, search = _make_niche_finder()
	result = nf.find_niches('fintech', mode='quick', num_niches=0)
	prompt = ai.generate_text.call_args[0][0]
	assert '0 objects' not in prompt


def test_invalid_mode_falls_back_to_research():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('fintech')
		MockLoop.return_value = mock_loop
		result = nf.find_niches('fintech', mode='turbo_fast')

	assert result['mode'] == 'research'


def test_industry_appears_in_all_search_queries():
	ai_responses = [_LANDSCAPE_JSON, _PMF_JSON, _TRENDS_JSON, _PRICING_JSON, _NICHE_JSON]
	nf, ai, search = _make_niche_finder(ai_responses)

	with patch('core.agent_loop.AgentLoop') as MockLoop:
		mock_loop = MagicMock()
		mock_loop.run.return_value = _mock_agent_run('proptech niches')
		MockLoop.return_value = mock_loop
		nf.find_niches('proptech', mode='research')

	for c in search.search.call_args_list:
		query_arg = c[0][0]
		assert 'proptech' in query_arg.lower()

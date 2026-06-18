# interfaces/cli.py

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.ai_engine import OllamaModel
from core.search_engine import DuckDuckGoSearch
from core.data_handler import DatabaseHandler
from core.rag_engine import RAGEngine
from core.knowledge_graph_manager import KnowledgeGraphManager
from core.template_manager import TemplateManager


def _build_common_deps(with_search=True, with_db=False, with_rag=False, with_templates=False):
	deps = {'ai_engine': OllamaModel()}
	if with_search:
		deps['search_engine'] = DuckDuckGoSearch()
	if with_db:
		try:
			db = DatabaseHandler()
			db.connect()
			deps['data_handler'] = db
		except Exception:
			deps['data_handler'] = None
	if with_rag:
		try:
			kg = KnowledgeGraphManager.from_settings()
			deps['rag_engine'] = RAGEngine(deps['ai_engine'], kg)
		except Exception:
			deps['rag_engine'] = None
	if with_templates:
		deps['template_manager'] = TemplateManager()
	return deps


def _print_result(result: dict):
	print(json.dumps(result, indent=2, default=str))


def cli_research_assistant(args):
	from capabilities.research_assistant import ResearchAssistant
	deps = _build_common_deps(with_search=True, with_db=True, with_rag=True)
	assistant = ResearchAssistant(**deps)
	result = assistant.perform_research(
		research_query=args.query,
		sources=args.sources,
		depth=args.depth,
	)
	_print_result(result)


def cli_report_writer(args):
	from capabilities.ai_report_writer import AIReportWriter
	deps = _build_common_deps(with_templates=True)
	context_data = args.context_data
	if os.path.isfile(context_data):
		with open(context_data) as f:
			context_data = f.read()
	writer = AIReportWriter(ai_engine=deps['ai_engine'], template_manager=deps['template_manager'])
	result = writer.generate_report(
		report_type=args.report_type,
		context_data=context_data,
		output_path=args.output_path,
	)
	_print_result(result)


def cli_competitive_intel(args):
	from capabilities.competitive_intelligence_operative import CompetitiveIntelligenceOperative
	deps = _build_common_deps(with_search=True, with_rag=True)
	ci = CompetitiveIntelligenceOperative(**deps)
	result = ci.analyze_competitor_landscape(
		industry=args.industry,
		competitors=args.competitors,
	)
	_print_result(result)


def cli_social_media(args):
	from capabilities.social_media_manager import SocialMediaManager
	deps = _build_common_deps(with_search=True)
	sm = SocialMediaManager(ai_engine=deps['ai_engine'], search_engine=deps['search_engine'])
	result = sm.analyze_social_trends(
		brand_name=args.brand,
		target_audience=args.audience,
		platforms=args.platforms,
	)
	_print_result(result)


def cli_market_research(args):
	from capabilities.market_sales_research import MarketSalesResearch
	deps = _build_common_deps(with_search=True)
	mr = MarketSalesResearch(ai_engine=deps['ai_engine'], search_engine=deps['search_engine'])
	result = mr.analyze_market_trends(
		product_category=args.category,
		region=args.region,
	)
	_print_result(result)


def cli_proposal(args):
	from capabilities.proposal_compositor import ProposalCompositor
	deps = _build_common_deps(with_templates=True)
	pc = ProposalCompositor(ai_engine=deps['ai_engine'], template_manager=deps['template_manager'])
	result = pc.compose_proposal(
		proposal_type=args.proposal_type,
		client_name=args.client,
		project_description=args.description,
	)
	_print_result(result)


def cli_cybersecurity(args):
	from capabilities.CybersecurityGuardian import CybersecurityGuardian
	deps = _build_common_deps(with_search=True)
	cg = CybersecurityGuardian(ai_engine=deps['ai_engine'], search_engine=deps['search_engine'])
	result = cg.perform_vulnerability_scan(
		system_description=args.system,
		scan_type=args.scan_type,
	)
	_print_result(result)


def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description='Thuon Platform CLI — AI-powered business capabilities',
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	subparsers = parser.add_subparsers(dest='capability', help='Capability to run')

	# research
	p = subparsers.add_parser('research', help='Research Assistant')
	p.add_argument('query', help='Research query')
	p.add_argument('--sources', nargs='+', default=['web', 'knowledge_graph'], help='Data sources')
	p.add_argument('--depth', default='medium', choices=['shallow', 'medium', 'deep'])

	# report
	p = subparsers.add_parser('report', help='AI Report Writer')
	p.add_argument('report_type', help='Type of report (e.g. executive_report)')
	p.add_argument('context_data', help='Context data string or path to a file')
	p.add_argument('--output-path', dest='output_path', default='report.docx')

	# competitive-intel
	p = subparsers.add_parser('competitive-intel', help='Competitive Intelligence')
	p.add_argument('industry', help='Industry sector')
	p.add_argument('competitors', nargs='+', help='List of competitor names')

	# social-media
	p = subparsers.add_parser('social-media', help='Social Media Manager')
	p.add_argument('brand', help='Brand name')
	p.add_argument('audience', help='Target audience description')
	p.add_argument('--platforms', nargs='+', default=['Twitter', 'LinkedIn', 'Instagram'])

	# market-research
	p = subparsers.add_parser('market-research', help='Market & Sales Research')
	p.add_argument('category', help='Product category')
	p.add_argument('region', help='Target region')

	# proposal
	p = subparsers.add_parser('proposal', help='Proposal Compositor')
	p.add_argument('proposal_type', help='Proposal type (e.g. business_proposal)')
	p.add_argument('client', help='Client name')
	p.add_argument('description', help='Project description')

	# cybersecurity
	p = subparsers.add_parser('cybersecurity', help='Cybersecurity Guardian')
	p.add_argument('system', help='System or application description')
	p.add_argument('--scan-type', dest='scan_type', default='quick', choices=['quick', 'deep'])

	# install — skill pack installation
	p = subparsers.add_parser('install', help='Install a skill pack (.spack file or URL)')
	p.add_argument('source', help='Path to .spack file or HTTPS URL')
	p.add_argument('--sha256', dest='expected_sha256', default=None,
	               help='Expected SHA-256 checksum for verification')

	# packs — manage installed packs
	p = subparsers.add_parser('packs', help='Manage installed skill packs')
	p.add_argument('action', choices=['list', 'remove'], help='Action to perform')
	p.add_argument('name', nargs='?', default=None, help='Pack name (required for remove)')

	return parser.parse_args()


def cli_install(args: argparse.Namespace) -> None:
	from tools.skill_pack_manager import install
	try:
		pack = install(args.source, expected_sha256=args.expected_sha256)
		print(f"Installed pack '{pack['name']}' v{pack['version']}")
		print(f"  Capabilities: {', '.join(pack['capabilities']) or 'none'}")
		print(f"  Skills:       {', '.join(pack['skills']) or 'none'}")
	except Exception as exc:
		print(f'Error: {exc}')
		sys.exit(1)


def cli_packs(args: argparse.Namespace) -> None:
	from tools.skill_pack_manager import list_packs, remove
	if args.action == 'list':
		packs = list_packs()
		if not packs:
			print('No skill packs installed.')
			return
		for p in packs:
			print(f"  {p['name']} v{p['version']} — {p['description']}")
			if p['capabilities']:
				print(f"    caps:   {', '.join(p['capabilities'])}")
			if p['skills']:
				print(f"    skills: {', '.join(p['skills'])}")
	elif args.action == 'remove':
		if not args.name:
			print('Error: pack name required for remove')
			sys.exit(1)
		try:
			remove(args.name)
			print(f"Removed pack '{args.name}'")
		except KeyError as exc:
			print(f'Error: {exc}')
			sys.exit(1)


def main_cli():
	args = parse_arguments()
	dispatch = {
		'research': cli_research_assistant,
		'report': cli_report_writer,
		'competitive-intel': cli_competitive_intel,
		'social-media': cli_social_media,
		'market-research': cli_market_research,
		'proposal': cli_proposal,
		'cybersecurity': cli_cybersecurity,
		'install': cli_install,
		'packs':   cli_packs,
	}
	if args.capability in dispatch:
		dispatch[args.capability](args)
	else:
		print('No capability specified. Run with --help for usage.')
		sys.exit(1)


if __name__ == '__main__':
	main_cli()

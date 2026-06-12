# core/data_sources — real structured data APIs
# All clients are stateless module-level functions; no auth required for basic tiers.
from core.data_sources.semantic_scholar import search_papers, get_citations, get_references, format_papers_for_context
from core.data_sources.arxiv_client import search as arxiv_search, format_papers as format_arxiv
from core.data_sources.nvd import search_cves, get_cve, format_cves_for_context
from core.data_sources.sec_edgar import search_filings, get_company_facts, search_company_cik
from core.data_sources.patents import search_patents, format_patents_for_context
from core.data_sources.opencorporates import search_company

__all__ = [
	'search_papers', 'get_citations', 'get_references', 'format_papers_for_context',
	'arxiv_search', 'format_arxiv',
	'search_cves', 'get_cve', 'format_cves_for_context',
	'search_filings', 'get_company_facts', 'search_company_cik',
	'search_patents', 'format_patents_for_context',
	'search_company',
]

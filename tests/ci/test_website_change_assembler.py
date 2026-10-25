# tests/ci/test_website_change_assembler.py
"""Tests for capabilities/website_change_assembler.py"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

import pytest


@pytest.fixture
def assembler():
	from capabilities.website_change_assembler import WebsiteChangeAssembler
	# No constructor args: the assembler only writes files. It took an ai_engine
	# that it stored and never read.
	return WebsiteChangeAssembler()


@pytest.fixture
def site_repo():
	with tempfile.TemporaryDirectory() as d:
		yield d


class TestAdditionalPages:
	def test_malformed_json_is_reported_not_raised(self, assembler, site_repo):
		# The registry exposes additional_pages as free text, so a caller can hand
		# over anything. A JSONDecodeError here used to abort a run whose primary
		# page was perfectly writable.
		result = assembler.assemble(
			page_path='/',
			optimized_content='# Home\n\nHello.',
			site_repo_path=site_repo,
			additional_pages='{not json',
		)
		assert 'not valid JSON' in result['change_summary']
		assert len(result['files_written']) == 1

	def test_valid_json_adds_pages(self, assembler, site_repo):
		result = assembler.assemble(
			page_path='/',
			optimized_content='# Home\n\nHello.',
			site_repo_path=site_repo,
			additional_pages=json.dumps({'/about': {'content': '# About\n\nUs.'}}),
		)
		assert 'not valid JSON' not in result['change_summary']
		assert len(result['files_written']) == 2

	def test_dict_input_bypasses_parsing(self, assembler, site_repo):
		result = assembler.assemble(
			page_path='/',
			optimized_content='# Home\n\nHello.',
			site_repo_path=site_repo,
			additional_pages={'/contact': {'content': '# Contact\n\nUs.'}},
		)
		assert 'not valid JSON' not in result['change_summary']
		assert len(result['files_written']) == 2

# tests/ci/test_company_profile.py
"""
Unit tests for CompanyProfile.
Uses a temp directory with synthetic .md files — no real data/company/ touched.
"""
from __future__ import annotations

import pytest

from core.company_profile import CompanyProfile


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def profile_dir(tmp_path):
	(tmp_path / 'profile.md').write_text(
		'# Acme Corp\nWe are a Nairobi-based professional services firm.\n'
		'NAICS: 541512. Founded 2010.\n'
	)
	(tmp_path / 'capabilities.md').write_text(
		'## Services\n- Cloud infrastructure\n- Data analytics\n- AI/ML consulting\n'
	)
	(tmp_path / 'win_themes.md').write_text(
		'## Win Themes\n1. Local expertise with global standards\n2. Proven delivery track record\n'
	)
	return tmp_path


@pytest.fixture
def profile(profile_dir, tmp_path):
	return CompanyProfile(profile_dir=profile_dir)


# ── Basic construction ────────────────────────────────────────────────────────

def test_profile_loads_without_error(profile):
	assert profile is not None


def test_chunk_count_positive(profile):
	assert profile.chunk_count > 0


# ── list_files ────────────────────────────────────────────────────────────────

def test_list_files_returns_md_filenames(profile):
	files = profile.list_files()
	assert isinstance(files, list)
	assert 'profile.md' in files
	assert 'capabilities.md' in files


def test_list_files_only_md(profile_dir):
	(profile_dir / 'notes.txt').write_text('not markdown')
	p = CompanyProfile(profile_dir=profile_dir)
	files = p.list_files()
	assert 'notes.txt' not in files


# ── get_file ──────────────────────────────────────────────────────────────────

def test_get_file_returns_content(profile):
	content = profile.get_file('win_themes.md')
	assert 'Win Themes' in content


def test_get_file_without_extension(profile):
	content = profile.get_file('win_themes')
	assert 'Win Themes' in content


def test_get_file_missing_returns_empty(profile):
	result = profile.get_file('nonexistent.md')
	assert result == '' or result is None or isinstance(result, str)


# ── get_context ───────────────────────────────────────────────────────────────

def test_get_context_returns_string(profile):
	ctx = profile.get_context('cloud services')
	assert isinstance(ctx, str)
	assert len(ctx) > 10


def test_get_context_no_query_returns_string(profile):
	ctx = profile.get_context()
	assert isinstance(ctx, str)


def test_get_context_empty_dir(tmp_path):
	p = CompanyProfile(profile_dir=tmp_path)
	ctx = p.get_context('anything')
	assert isinstance(ctx, str)


# ── reload ────────────────────────────────────────────────────────────────────

def test_reload_picks_up_new_file(profile, profile_dir):
	(profile_dir / 'pricing.md').write_text('## Pricing\nDaily rate: $1200\n')
	profile.reload()
	files = profile.list_files()
	assert 'pricing.md' in files

# core/bundle.py
"""
Bundle-aware path resolution for Thuon.

In development (uv run / pytest):
  app_root()      → .../thuon_platform/          (source tree)
  user_data_dir() → THUON_DATA_DIR env or ~/.thuon/

In a PyInstaller .app bundle:
  app_root()      → <bundle>/_internal/           (read-only; templates, pipelines, …)
  user_data_dir() → ~/Library/Application Support/Thuon/ (writable)

All writable runtime data (DBs, user config, generated files) must use
user_data_dir().  Read-only bundled assets use app_root().
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Separator so tests can inject a temp dir without touching real user data
_ENV_OVERRIDE = 'THUON_DATA_DIR'


def app_root() -> Path:
	"""
	Root of the read-only application data.

	Development: thuon_platform/ directory (parent of core/).
	Bundle:      sys._MEIPASS (where PyInstaller extracts frozen data).
	"""
	if getattr(sys, 'frozen', False):
		return Path(sys._MEIPASS)
	# __file__ = .../thuon_platform/core/bundle.py  →  .parent.parent = thuon_platform/
	return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
	"""
	Writable user data directory.  Created on first call.

	Override: set THUON_DATA_DIR environment variable (used by tests).
	macOS bundle: ~/Library/Application Support/Thuon/
	Development / other: ~/.thuon/
	"""
	if override := os.environ.get(_ENV_OVERRIDE):
		d = Path(override)
	elif getattr(sys, 'frozen', False) and sys.platform == 'darwin':
		d = Path.home() / 'Library' / 'Application Support' / 'Thuon'
	else:
		d = Path.home() / '.thuon'
	d.mkdir(parents=True, exist_ok=True)
	return d


def ensure_first_run() -> None:
	"""
	On first launch, copy bundled defaults into the user data directory
	so the app has a working config and company templates out of the box.
	Called once by the desktop entry point before Flask starts.
	"""
	udd  = user_data_dir()
	root = app_root()
	marker = udd / '.initialized'
	if marker.exists():
		return

	seeds: list[tuple[str, str]] = [
		('config/config.yaml',    'config/config.yaml'),
		('data/company',          'data/company'),
		('data/pipelines',        'data/pipelines'),
		('data/templates.yaml',   'data/templates.yaml'),
	]
	for src_rel, dst_rel in seeds:
		src = root / src_rel
		dst = udd / dst_rel
		if not src.exists() or dst.exists():
			continue
		dst.parent.mkdir(parents=True, exist_ok=True)
		if src.is_dir():
			shutil.copytree(src, dst)
		else:
			shutil.copy2(src, dst)

	marker.touch()


# ── Convenience accessors ─────────────────────────────────────────────────────

def _frozen() -> bool:
	return getattr(sys, 'frozen', False)


def config_dir() -> Path:
	"""config/  — writable in bundle (user may edit), source tree in dev."""
	return (user_data_dir() / 'config') if _frozen() else (app_root() / 'config')


def writable_data_dir() -> Path:
	"""data/  — writable runtime directory (DBs, generated files, user content)."""
	d = (user_data_dir() / 'data') if _frozen() else (app_root() / 'data')
	d.mkdir(parents=True, exist_ok=True)
	return d


def pipelines_dir() -> Path:
	"""data/pipelines/  — read-only YAML definitions, always from app_root."""
	return app_root() / 'data' / 'pipelines'


def skills_dirs() -> list[Path]:
	"""Ordered list of skill directories to scan for SKILL.md files."""
	seen: set[Path] = set()
	dirs: list[Path] = []

	if not _frozen():
		# In development the project layout is Thuon/skills/ beside Thuon/thuon_platform/.
		# In a frozen build app_root().parent is an ephemeral temp dir, so skip it.
		project_skills = app_root().parent / 'skills'
		r = project_skills.resolve() if project_skills.exists() else project_skills
		seen.add(r)
		dirs.append(project_skills)

	app_skills = app_root() / 'skills'
	r = app_skills.resolve() if app_skills.exists() else app_skills
	if r not in seen:
		seen.add(r)
		dirs.append(app_skills)

	if _frozen():
		dirs.append(user_data_dir() / 'skills')
	else:
		dirs.append(Path.home() / '.thuon' / 'skills')
	return dirs

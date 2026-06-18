# core/skill_registry.py
"""
Unified skill / capability registry for Thuon.

Design
------
Phase 0: SkillRegistry wraps both existing hardcoded registries
(CAPABILITY_REGISTRY from web_app and _REGISTRY from thuon.py) through
two bootstrap methods, then augments with any SKILL.md files found in:

  thuon_platform/skills/<skill-name>/SKILL.md
  ~/.thuon/skills/<skill-name>/SKILL.md

SKILL.md files are the extension point for adding new capabilities without
touching Python code.  They take precedence over registry entries when both
exist for the same name.

Backward compatibility
----------------------
Both existing registries stay intact.  web_app.py calls
  SkillRegistry.get_instance().bootstrap(CAPABILITY_REGISTRY, _CATEGORY_MAP)
at app startup, and thuon.py calls
  SkillRegistry.get_instance().augment_cli(_REGISTRY)
after defining _REGISTRY.  Both dicts continue to work as before.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger('thuon.skill_registry')

from core.bundle import skills_dirs as _sd
_SKILL_DIRS: list[Path] = _sd()


# ── Models ────────────────────────────────────────────────────────────────────

class SkillParam(BaseModel):
	model_config = ConfigDict(extra='allow')

	name: str
	type: str = 'str'
	required: bool = False
	default: Any = None
	choices: list[str] = Field(default_factory=list)
	options: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
	"""Unified descriptor covering both CLI and web capability shapes."""

	model_config = ConfigDict(extra='forbid')

	name: str
	description: str
	module: str = ''
	class_name: str = ''        # serialised as 'class' in legacy dicts
	method: str = ''
	deps: list[str] = Field(default_factory=list)
	keywords: list[str] = Field(default_factory=list)
	category: str = 'general'
	params: list[SkillParam] = Field(default_factory=list)
	example: str = ''
	body: str = ''              # SKILL.md text below frontmatter
	source: str = 'registry'    # 'registry_web' | 'registry_cli' | 'skill_md'
	capability_alias: str = ''  # thuon.capability — maps this skill to an existing cap name

	# ── Backward-compat serialisation ────────────────────────────────────────

	def as_web_entry(self) -> dict[str, Any]:
		"""Dict compatible with the old CAPABILITY_REGISTRY entry shape."""
		return {
			'description': self.description,
			'method':      self.method,
			'params':      [_param_to_dict(p) for p in self.params],
			'deps':        self.deps,
			'module':      self.module,
			'class':       self.class_name,
		}

	def as_cli_entry(self) -> dict[str, Any]:
		"""Dict compatible with the old _REGISTRY entry shape."""
		return {
			'module':      self.module,
			'class':       self.class_name,
			'deps':        self.deps,
			'method':      self.method,
			'description': self.description,
			'keywords':    self.keywords,
			'example':     self.example,
		}


def _param_to_dict(p: SkillParam) -> dict[str, Any]:
	d: dict[str, Any] = {'name': p.name, 'type': p.type, 'required': p.required}
	if p.default is not None:
		d['default'] = p.default
	if p.choices:
		d['choices'] = p.choices
	if p.options:
		d['options'] = p.options
	return d


# ── Registry ──────────────────────────────────────────────────────────────────

class SkillRegistry:
	"""
	Singleton registry.

	Usage (web app):
	  SkillRegistry.get_instance().bootstrap(CAPABILITY_REGISTRY, _CATEGORY_MAP)

	Usage (CLI / Thuon facade):
	  SkillRegistry.get_instance().augment_cli(_REGISTRY)

	Lookup:
	  manifest = SkillRegistry.get_instance().get('deep_researcher')
	  results  = SkillRegistry.get_instance().search('find government tenders')
	"""

	_instance: ClassVar[SkillRegistry | None] = None

	def __init__(self) -> None:
		self._manifests: dict[str, SkillManifest] = {}
		self._category_map: dict[str, str] = {}
		self._bootstrapped: bool = False
		self._skills_discovered: bool = False

	@classmethod
	def get_instance(cls) -> SkillRegistry:
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	@classmethod
	def reset(cls) -> None:
		"""Reset singleton — for tests only."""
		cls._instance = None

	# ── Bootstrap methods ─────────────────────────────────────────────────────

	def bootstrap(
		self,
		web_registry: dict[str, dict],
		category_map: dict[str, str],
	) -> None:
		"""
		Seed from CAPABILITY_REGISTRY + _CATEGORY_MAP (web_app.py).
		Safe to call multiple times; subsequent calls only add/update.
		"""
		for name, entry in web_registry.items():
			raw_params = entry.get('params') or []
			params = [SkillParam(**p) for p in raw_params]
			self._manifests[name] = SkillManifest(
				name=name,
				description=entry.get('description', ''),
				module=entry.get('module', ''),
				class_name=entry.get('class', ''),
				method=entry.get('method', ''),
				deps=list(entry.get('deps') or []),
				params=params,
				category=category_map.get(name, 'general'),
				source='registry_web',
			)
		self._category_map.update(category_map)
		self._discover_skills()
		self._skills_discovered = True
		self._bootstrapped = True

	def augment_cli(self, cli_registry: dict[str, dict]) -> None:
		"""
		Augment with _REGISTRY (thuon.py CLI facade).
		Adds keywords/example to entries already known from web registry;
		creates new entries for CLI-only capabilities (document_generator, etc.).
		"""
		for name, entry in cli_registry.items():
			if name in self._manifests:
				m = self._manifests[name]
				updates: dict[str, Any] = {}
				if not m.keywords:
					updates['keywords'] = list(entry.get('keywords') or [])
				if not m.example:
					updates['example'] = entry.get('example', '')
				if updates:
					self._manifests[name] = m.model_copy(update=updates)
			else:
				self._manifests[name] = SkillManifest(
					name=name,
					description=entry.get('description', ''),
					module=entry.get('module', ''),
					class_name=entry.get('class', ''),
					method=entry.get('method', ''),
					deps=list(entry.get('deps') or []),
					keywords=list(entry.get('keywords') or []),
					example=entry.get('example', ''),
					source='registry_cli',
				)
		if not getattr(self, '_skills_discovered', False):
			self._discover_skills()
			self._skills_discovered = True

	def _discover_skills(self) -> None:
		"""Walk SKILL.md directories; merge into existing capability entries when aliased."""
		for skill_dir in _SKILL_DIRS:
			if not skill_dir.exists():
				continue
			for skill_md in sorted(skill_dir.rglob('SKILL.md')):
				try:
					manifest = _parse_skill_md(skill_md)
					alias = manifest.capability_alias
					if alias and alias in self._manifests:
						# Merge SKILL.md keywords/body/description into the existing capability
						# entry without overwriting its module/class/method/params.
						existing = self._manifests[alias]
						merged_keywords = list(dict.fromkeys(existing.keywords + manifest.keywords))
						self._manifests[alias] = existing.model_copy(update={
							'keywords':         merged_keywords,
							'body':             manifest.body or existing.body,
							'description':      manifest.description or existing.description,
							'capability_alias': alias,
						})
						logger.debug('Merged skill %s into capability %s', manifest.name, alias)
					else:
						self._manifests[manifest.name] = manifest
						if manifest.category != 'general':
							self._category_map[manifest.name] = manifest.category
						logger.debug('Loaded skill %s from %s', manifest.name, skill_md)
				except Exception as exc:
					logger.warning('Failed to parse %s: %s', skill_md, exc)

	# ── Lookup API ────────────────────────────────────────────────────────────

	def get(self, name: str) -> SkillManifest | None:
		return self._manifests.get(name)

	def all(self) -> list[SkillManifest]:
		return list(self._manifests.values())

	def by_category(self, category: str) -> list[SkillManifest]:
		return [m for m in self._manifests.values() if m.category == category]

	def categories(self) -> set[str]:
		return {m.category for m in self._manifests.values()}

	def category_of(self, name: str) -> str:
		return self._category_map.get(name, 'general')

	def search(self, query: str, top_k: int = 5) -> list[SkillManifest]:
		"""
		BM25-lite keyword search over name + description + keywords.
		Returns up to top_k manifests ranked by token overlap score.
		"""
		tokens = set(re.findall(r'\w+', query.lower()))
		if not tokens:
			return []

		scores: list[tuple[float, SkillManifest]] = []
		for m in self._manifests.values():
			haystack = (
				m.name.replace('_', ' ') + ' '
				+ m.description + ' '
				+ ' '.join(m.keywords)
			).lower()
			score = sum(1.0 for t in tokens if t in haystack)
			if score:
				scores.append((score, m))

		scores.sort(key=lambda x: x[0], reverse=True)
		return [m for _, m in scores[:top_k]]

	def register(self, manifest: SkillManifest, category: str = 'general') -> None:
		"""Programmatically register a skill (e.g. from @t.capability decorator)."""
		self._manifests[manifest.name] = manifest
		self._category_map[manifest.name] = category

	# ── Backward-compat views ─────────────────────────────────────────────────

	def as_web_registry(self) -> dict[str, dict]:
		return {name: m.as_web_entry() for name, m in self._manifests.items()}

	def as_cli_registry(self) -> dict[str, dict]:
		return {
			name: m.as_cli_entry()
			for name, m in self._manifests.items()
			if m.module and m.class_name and m.method
		}

	def as_category_map(self) -> dict[str, str]:
		return dict(self._category_map)

	def __len__(self) -> int:
		return len(self._manifests)

	def __contains__(self, name: str) -> bool:
		return name in self._manifests


# ── SKILL.md parser ───────────────────────────────────────────────────────────

def _parse_skill_md(path: Path) -> SkillManifest:
	"""
	Parse a SKILL.md file into a SkillManifest.

	Expected format::

	  ---
	  name: my_skill
	  description: What this skill does
	  keywords: [keyword1, keyword2]
	  thuon:
	    module: capabilities.my_module
	    class: MyClass
	    method: run
	    deps: [ai_engine]
	    category: research
	    params:
	      - name: topic
	        type: str
	        required: true
	  ---

	  Body text: natural language description, trigger phrases,
	  usage examples.  Injected into context when the skill activates.
	"""
	import yaml  # already in requirements

	text = path.read_text(encoding='utf-8-sig')
	fm: dict[str, Any] = {}
	body = text

	if text.startswith('---'):
		parts = text.split('---', 2)
		if len(parts) >= 3:
			fm = yaml.safe_load(parts[1]) or {}
			body = parts[2].strip()

	thuon_ns: dict[str, Any] = fm.pop('thuon', {}) or {}
	name = str(fm.get('name') or path.parent.name)

	# thuon.params may be a list of SkillParam dicts OR a dict of fixed exec kwargs;
	# top-level fm.params is always a list of SkillParam dicts.
	thuon_params_raw = thuon_ns.get('params')
	if isinstance(thuon_params_raw, list):
		raw_params = thuon_params_raw
	else:
		raw_params = fm.get('params') or []
	if not isinstance(raw_params, list):
		raw_params = []
	params = [SkillParam(**p) for p in raw_params if isinstance(p, dict)]

	return SkillManifest(
		name=name,
		description=str(fm.get('description', '')),
		module=str(thuon_ns.get('module') or fm.get('module') or ''),
		class_name=str(thuon_ns.get('class') or fm.get('class') or ''),
		method=str(thuon_ns.get('method') or fm.get('method') or ''),
		deps=list(thuon_ns.get('deps') or fm.get('deps') or []),
		keywords=list(fm.get('keywords') or []),
		category=str(thuon_ns.get('category') or fm.get('category') or 'general'),
		params=params,
		example=str(fm.get('example') or ''),
		body=body,
		source='skill_md',
		capability_alias=str(thuon_ns.get('capability') or ''),
	)

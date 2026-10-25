# tests/ci/test_registry_contracts.py
# The capability registry is the contract between the web UI, the pipeline
# runner, and every capability class. It drifts silently: a param renamed in
# a capability leaves the registry advertising the old name, the UI renders
# the wrong form, and the call raises TypeError at runtime. These tests assert
# the contract directly against the live objects.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'thuon_platform'))

import importlib
import inspect
import pathlib

import yaml

import interfaces.web_app as web_app

REGISTRY = web_app.CAPABILITY_REGISTRY
_WEB_APP_FILE = web_app.__file__
assert _WEB_APP_FILE is not None  # a real module always has one
_PIPELINES_DIR = pathlib.Path(_WEB_APP_FILE).parent.parent / 'data' / 'pipelines'


def _resolve(name):
	"""Return (callable, signature) for a registry entry, or raise."""
	cfg = REGISTRY[name]
	mod = importlib.import_module(cfg['module'])
	return getattr(getattr(mod, cfg['class']), cfg['method'])


def _accepts_kwargs(fn) -> bool:
	return any(p.kind is p.VAR_KEYWORD for p in inspect.signature(fn).parameters.values())


def test_every_registry_entry_loads():
	broken = []
	for name, cfg in REGISTRY.items():
		if not cfg.get('module'):
			continue
		try:
			_resolve(name)
		except Exception as exc:
			broken.append(f'{name}: {type(exc).__name__}: {exc}')
	assert broken == [], 'unloadable registry entries:\n' + '\n'.join(broken)


def test_declared_params_match_signatures():
	"""A declared param the method does not accept is a form field that always TypeErrors."""
	drift = []
	for name in REGISTRY:
		if not REGISTRY[name].get('module'):
			continue
		fn = _resolve(name)
		if _accepts_kwargs(fn):
			continue
		accepted = set(inspect.signature(fn).parameters)
		declared = {p['name'] for p in REGISTRY[name].get('params', [])}
		if declared - accepted:
			drift.append(f'{name}: declared-but-not-accepted {sorted(declared - accepted)}')
	assert drift == [], 'registry/signature drift:\n' + '\n'.join(drift)


def test_every_required_signature_param_is_declared():
	"""A required signature param absent from the registry is one no form can ever supply.

	Undeclared *optional* params are fine — the method has a default, so the
	registry simply does not expose that knob.
	"""
	bad = []
	for name in REGISTRY:
		if not REGISTRY[name].get('module'):
			continue
		fn = _resolve(name)
		if _accepts_kwargs(fn):
			continue
		sig = inspect.signature(fn)
		declared = {p['name'] for p in REGISTRY[name].get('params', [])}
		for pname, param in sig.parameters.items():
			if pname == 'self' or param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
				continue
			if param.default is inspect.Parameter.empty and pname not in declared:
				bad.append(f'{name}: required signature param {pname!r} is not declared')
	assert bad == [], 'undeclared required params:\n' + '\n'.join(bad)


def test_every_pipeline_step_resolves():
	"""Pipelines name capabilities and params that must exist in the registry."""
	problems = []
	files = sorted(_PIPELINES_DIR.glob('*.yaml'))
	assert files, f'no pipelines found under {_PIPELINES_DIR}'
	for f in files:
		spec = yaml.safe_load(f.read_text(encoding='utf-8')) or {}
		for step in spec.get('steps', []):
			cap = step.get('capability')
			params = step.get('params') or {}
			label = f'{f.name}:{step.get("name")}'
			if cap not in REGISTRY:
				problems.append(f'{label}: capability {cap!r} is not registered')
				continue
			declared = {p['name']: p for p in REGISTRY[cap]['params']}
			for key in params:
				if key not in declared:
					problems.append(f'{label}: param {key!r} not declared by {cap}')
			for pname, p in declared.items():
				if p.get('required') and pname not in params:
					problems.append(f'{label}: missing required param {pname!r} for {cap}')
	assert problems == [], 'pipeline/registry mismatch:\n' + '\n'.join(problems)

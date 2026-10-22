"""
Gate: no function in the platform mutates a mutable default argument.

`ruff`'s B006 flags every mutable default, but it cannot tell a read-only
default from one that leaks state between calls. All 36 sites in this
codebase are read-only today, so B006 is ignored in pyproject.toml. This
test is the part that would actually catch the bug: it resolves each
mutable default and inspects the function body for anything that could
write to it.

Anchored on the AST rather than on runtime behaviour so it covers
functions that no test happens to call.
"""

from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2] / 'thuon_platform'

# Methods that mutate their receiver. A default appearing as `default.<m>(…)`
# is a live bug.
_MUTATORS = frozenset({
	'append', 'extend', 'insert', 'pop', 'popitem', 'remove', 'clear',
	'sort', 'reverse', 'update', 'setdefault', '__setitem__', '__delitem__',
})


def _mutable_default_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
	"""Names bound to a list/dict/set default in *func*'s signature."""
	args = func.args
	n = len(args.defaults)
	if not n:
		return set()
	positional = args.args[len(args.args) - n:]
	return {
		arg.arg
		for arg, default in zip(positional, args.defaults, strict=True)
		if isinstance(default, (ast.List, ast.Dict, ast.Set))
	}


def _writes_to(func: ast.AST, names: set[str]) -> list[str]:
	"""Return a description of each write to a name in *names* inside *func*."""
	hits: list[str] = []
	for node in ast.walk(func):
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
			recv = node.func.value
			if isinstance(recv, ast.Name) and recv.id in names and node.func.attr in _MUTATORS:
				hits.append(f'line {node.lineno}: {recv.id}.{node.func.attr}()')
		elif isinstance(node, ast.Assign):
			for target in node.targets:
				if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
					if target.value.id in names:
						hits.append(f'line {node.lineno}: {target.value.id}[…] = …')
		elif isinstance(node, ast.AugAssign):
			if isinstance(node.target, ast.Subscript) and isinstance(node.target.value, ast.Name):
				if node.target.value.id in names:
					hits.append(f'line {node.lineno}: {node.target.value.id}[…] op= …')
		elif isinstance(node, ast.Delete):
			for target in node.targets:
				if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
					if target.value.id in names:
						hits.append(f'line {node.lineno}: del {target.value.id}[…]')
	return hits


def _iter_functions(path: pathlib.Path):
	for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))):
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			yield node


def _scan(root: pathlib.Path) -> tuple[int, list[str]]:
	offenders: list[str] = []
	sites = 0
	for path in sorted(root.rglob('*.py')):
		for func in _iter_functions(path):
			names = _mutable_default_names(func)
			if not names:
				continue
			sites += 1
			for hit in _writes_to(func, names):
				offenders.append(f'{path.name}::{func.name} {hit}')
	return sites, offenders


def test_no_mutable_default_is_mutated():
	"""Every list/dict/set default is treated as read-only by its own body."""
	sites, offenders = _scan(_ROOT)
	assert sites > 0, 'scan found no mutable defaults — the walker is broken, not the codebase'
	assert not offenders, (
		'These functions mutate a mutable default argument, so state leaks '
		'between calls:\n  ' + '\n  '.join(offenders)
	)


def test_gate_detects_a_planted_mutation(tmp_path):
	"""
	Canary: the same scanner must flag a file that does mutate its default.
	A gate that has never been seen to fail is not evidence.
	"""
	(tmp_path / 'planted.py').write_text(
		'def leaky(items: list = []):\n'
		'\titems.append(1)\n'
		'\treturn items\n'
		'\n'
		'def subscripted(opts: dict = {}):\n'
		"\topts['k'] = 1\n"
		'\n'
		'def clean(items: list = []):\n'
		'\treturn list(items)\n',
		encoding='utf-8',
	)
	sites, offenders = _scan(tmp_path)
	assert sites == 3, f'expected 3 mutable-default sites, scanned {sites}'
	assert len(offenders) == 2, offenders
	assert any('leaky' in o and 'append' in o for o in offenders), offenders
	assert any('subscripted' in o for o in offenders), offenders
	assert not any('clean' in o for o in offenders), 'read-only default was flagged'

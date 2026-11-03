# tests/ci/test_skill_runner.py
"""Tests for core/skill_runner.py (runtime for markdown-only skills)."""
import os, sys, textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../thuon_platform'))

import pytest
from unittest.mock import MagicMock


def _make_skill(tmp_path, monkeypatch, name, body_extra='You are an analyst. Output bullet summary.\nBody saw arg: $ARGUMENTS'):
	skill_dir = tmp_path / 'skills' / name
	skill_dir.mkdir(parents=True)
	(skill_dir / 'SKILL.md').write_text(textwrap.dedent(f"""\
		---
		name: {name}
		description: A markdown-only skill
		keywords: [pure, demo]
		category: research
		---
		{body_extra}
		"""))
	import core.skill_registry as sr
	monkeypatch.setattr(sr, '_SKILL_DIRS', [tmp_path / 'skills'])
	SkillRegistry = sr.SkillRegistry
	SkillRegistry.reset()
	reg = SkillRegistry.get_instance()
	reg._discover_skills()
	return reg


def test_skill_runner_returns_llm_text(tmp_path, monkeypatch):
	reg = _make_skill(tmp_path, monkeypatch, 'pure-skill')
	assert 'pure-skill' in reg
	from core.skill_runner import SkillRunner
	ai = MagicMock()
	ai.generate_text.return_value = 'bulleted result'
	runner = SkillRunner('pure-skill', ai)
	out = runner.run(instruction='analyze X')
	assert out['skill'] == 'pure-skill'
	assert out['result'] == 'bulleted result'
	prompt = ai.generate_text.call_args.args[0]
	assert 'Output bullet summary' in prompt
	assert 'analyze X' in prompt


def test_skill_runner_unknown_skill_raises(tmp_path, monkeypatch):
	from core.skill_runner import SkillRunner
	ai = MagicMock()
	with pytest.raises(ValueError):
		SkillRunner('does-not-exist', ai)


def test_skill_runner_error_path(tmp_path, monkeypatch):
	reg = _make_skill(tmp_path, monkeypatch, 'err-skill', body_extra='Body.')
	from core.skill_runner import SkillRunner
	ai = MagicMock()
	ai.generate_text.side_effect = RuntimeError('boom')
	runner = SkillRunner('err-skill', ai)
	out = runner.run(instruction='x')
	assert out['status'] == 'error'
	assert 'boom' in out['error']

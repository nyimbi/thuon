# Thuon Markdown Skills — Integration

Thuon now ingests `SKILL.md` files the way Hermes/OpenClaw do — instruction documents with YAML frontmatter and Markdown bodies — and executes them as prompt-driven skills in addition to typed Python capabilities.

## Where skills come from

Skill roots resolved by `core.bundle.skills_roots()` (ordered, deduped):

1. `THUON_SKILLS_DIRS` env var (colon-separated roots) — enables external bundles.
2. In-dev: `Thuon/skills/` (none).
3. Bundled: `thuon_platform/skills/`.
4. User: `~/.thuon/skills/` (dev) or `~/Library/Application Support/Thuon/skills` (bundle).

An external bundle (e.g. the 149-skill strategy bundle) is consumed by:

    export THUON_SKILLS_DIRS=/path/to/bundle/skills

## Discovery

- `core/skill_registry.py::_discover_skills()` walks every root via `rglob('SKILL.md')`.
- `_parse_skill_md` uses PyYAML with a line-oriented fallback for malformed frontmatter.
- Pure skills (no `thuon:` block) get added as SkillManifests with source='skill_md'.
- Frontmatter may declare `thuon:` (module/class/method/deps/params/category) to alias a typed capability.

## Execution paths

- Capability registry entry: `_build_instance` (Python capability) — original path.
- Pure skill: `core.skill_runner.SkillRunner`, invoked from `Thuon._instantiate`
  and web `/api/do` skill-only branch.

## Tolerant frontmatter

Many upstream skills use block scalars with prose merged onto the folded
indicator line (`description: >- For ...`), which PyYAML rejects. The fallback
`_tolerant_frontmatter` extracts `name`, `description`, `keywords`, `category`,
`thuon`. If no `name` is recovered, the file is logged and skipped (per test).

## Routing

Skill-only capabilities must not shadow typed ones. `route_with_params` chooses
a typed capability whenever one appears in top-k, reserving skills for genuine
skill-exclusive matches (or explicit names like `thuon-research-brief`).

## Reference

- Inspired by Hermes Agent SKILL.md (Nous Research) and OpenClaw skills.
- Surveys: `github.com/nousresearch/hermes-agent`; `github.com/openclaw/openclaw`.

## Status

- env-based roots done.
- 149-skill bundle ingest tested (205 discovered; ~18 tolerated).
- 2 bundled Thuon-authored skills for reporting/research: `thuon-research-brief`, `market-sizing`.
- progressive disclosure of `references/` not yet implemented; bodies are loaded wholesale.

## Future work

1. Settings-driven `skills.roots`.
2. Progressive disclosure (index - pull references on demand).
3. Evaluating tool-calling skills that map markdown instructions to a backing capability via `thuon:` blocks.
4. Skill editing UI in web app.
5. Bundle vendored curated copy (instead of env-dependent) for offline use.
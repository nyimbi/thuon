---
name: _example_new_skill
description: Template — copy this directory to create a new skill without touching Python code
version: "1.0"
keywords:
  - example
  - template
thuon:
  # Point to an existing Python capability:
  module: capabilities.my_module
  class: MyClass
  method: run
  deps: [ai_engine, search_engine]
  category: general

  # OR define a YAML pipeline (no Python class needed):
  # pipeline: data/pipelines/my_pipeline.yaml

  params:
    - name: topic
      type: str
      required: true
    - name: depth
      type: str
      required: false
      default: medium
      choices: [quick, medium, deep]
---

## How to create a new skill

1. Copy this directory: `cp -r skills/_example_new_skill skills/my_skill`
2. Edit `SKILL.md` — set `name`, `description`, `keywords`, and the `thuon:` block
3. Restart Thuon — the registry auto-discovers `skills/*/SKILL.md` on startup
4. Test: `t.do("your trigger phrase")`

### Progressive disclosure tiers

**Tier 1 (catalog)** — only `name` and `description` are shown in the capability list.
Keep `description` under 120 chars.  Write it as "Use when: ..." trigger phrases.

**Tier 2 (activation)** — the full SKILL.md body is injected into LLM context when
this skill is selected.  Put detailed instructions, examples, and caveats here.

**Tier 3 (resources)** — link to external docs, schemas, or data files the skill
needs at runtime.

### User-level skills

Drop a `SKILL.md` in `~/.thuon/skills/<name>/SKILL.md` for personal skills that
don't belong in the project repo (API keys, personal workflows, client-specific).

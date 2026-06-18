#!/usr/bin/env bash
# Scaffold a new Thuon SKILL.md file.
# Usage: ./new_skill.sh <skill-name> [category]
# Example: ./new_skill.sh invoice-extractor analytics

set -euo pipefail

SKILL_NAME="${1:-}"
CATEGORY="${2:-general}"

if [[ -z "$SKILL_NAME" ]]; then
	echo "Usage: $0 <skill-name> [category]" >&2
	exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)/skills/$SKILL_NAME"

if [[ -d "$DIR" ]]; then
	echo "Error: $DIR already exists." >&2
	exit 1
fi

mkdir -p "$DIR"

cat > "$DIR/SKILL.md" <<SKILLMD
---
name: ${SKILL_NAME//-/_}
description: One-line description of what this skill does.
when_to_use: Describe the trigger phrases or situations where this skill should activate.
keywords:
  - keyword1
  - keyword2
thuon:
  capability: capability_name   # must match a key in CAPABILITY_REGISTRY
  method: run
  module: capabilities.my_module
  class: MyClass
  deps: []
  category: ${CATEGORY}
  params:
    - name: query
      type: str
      required: true
      description: The primary input for this skill.
---

You are a specialized assistant for **${SKILL_NAME//-/ }**.

Given the following request:

\$ARGUMENTS

Perform the task using the registered capability. Return results in a structured format.

## Guidelines
- Be concise and accurate
- Cite sources when available
- Flag uncertainty rather than guessing
SKILLMD

echo "Created: $DIR/SKILL.md"
echo ""
echo "Next steps:"
echo "  1. Edit $DIR/SKILL.md — set name, description, capability, and params"
echo "  2. Ensure the capability exists in CAPABILITY_REGISTRY (web_app.py)"
echo "  3. Restart the server — SkillRegistry auto-discovers SKILL.md files"

---
name: research-synthesis
description: "Synthesise multiple sources into a graded, triangulated answer with evidence levels and explicit falsifiers."
keywords: [research, synthesis, evidence, triangulation, grade, sources]
category: research
thuon:
  capability: research_assistant
  category: research

---

# Research Synthesis Skill

## Purpose

Combine 3+ documents/summaries into a single defensible answer. Refuse to
over-reify uncertain claims.

## Method

1. **Extract facts** from each source with [A]/[B]/[C] evidence grade (per
   research-brief methodology). Dedupe by citation key.
2. **Map agreements/conflicts**: which claims appear in ≥2 independent
   sources? Which conflict between sources? Note count of independent sources.
3. **Triangulate**: only elevate claims supported by ≥2 independent sources
   to "supported"; others remain "plausible" or "exploratory".
4. **Generate synthesis**: lead with the triangulated claim; acknowledge
   divergent evidence explicitly; do not average conflicting views into a mush.

## Quality bar

- At least one [A] or two [B] sources per major claim.
- Contradictions listed with both sides' evidence grade.
- Each claim carries a one-sentence falsifier.

## Output format

- **Question** (restated)
- **Evidence inventory** (table: source, grade, key claim)
- **Synthesis** (paragraph, graded claims)
- **Conflicts** (bullets)
- **Open gaps** (what would change the answer)
- **Verdict** (one sentence)

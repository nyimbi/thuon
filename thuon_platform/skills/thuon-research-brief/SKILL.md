---
name: thuon-research-brief
description: Write a structured, citation-grounded research brief for a business question, matching Thuon reporting conventions.
keywords: research brief report structure citations
category: research
thuon:
  capability: research_assistant
  category: research

---

# Thuon Research Brief Skill

You are producing a **research brief** for a business decision. Follow these rules exactly.

## Method

1. Frame the question in one sentence, stating whether it is **factual, integrative, or evaluative**.
2. Identify required evidence types: primary, market, competitive, financial, regulatory.
3. For every claim, attach **[A]/[B]/[C]** evidence grades:
   - A: primary, observable fact
   - B: expert-inferred, plausible
   - C: assumption, needs verification
4. Output structure:
   - **TL;DR** (3 bullets max)
   - **Question** (restated)
   - **Evidence** (table or list, graded)
   - **Analysis** (mechanism, not summary)
   - **Risks & falsifiers** (3)
   - **Recommendation** (one sentence + strongest next action)
   - **Open gaps** (what would change the conclusion)

## Do NOT

- State conclusions without evidence grades.
- Re-quote marketing copy as fact.
- Forget to list what would change your answer.

Use as much of the user's $ARGUMENTS context as possible.

---
name: research-assistant
description: |
  Research any topic in depth: find sources, synthesize information, verify
  facts, compare options, and produce structured research summaries. Use when
  the user asks to "research", "investigate", "find out about", "what do we
  know about", "look into", "deep dive on", or "give me a comprehensive
  overview of" any topic.
when_to_use: |
  Invoke for: multi-source research synthesis, competitive intelligence,
  market research, technology evaluation, literature review, due diligence,
  academic topic surveys, or any task requiring gathering and synthesizing
  information from multiple sources into a coherent summary.
argument-hint: "research topic or question"
arguments:
  - name: topic
    description: "Topic or question to research"
    required: true
  - name: depth
    description: "quick | standard | deep (default: standard)"
    required: false
    default: "standard"
  - name: focus
    description: "Specific angle: market | academic | competitive | technical"
    required: false
    default: "general"
  - name: output_format
    description: "summary | report | bullet_points | comparison (default: summary)"
    required: false
    default: "summary"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [research, investigate, synthesize, sources, analysis, report, summary, intelligence]

thuon:
  capability: research_assistant
  method: research
  deps: [ai_engine, search_engine, rag_engine]
  params:
    depth: standard
  output_format: markdown
  category: research
  tier: 1
---

## Research Assistant Skill

Conduct multi-source research via `research_assistant` and `deep_researcher`.

**Research topic:** $ARGUMENTS

**Tool orchestration by depth:**

- **quick** (1-3 sources): `research_assistant.research(topic)`
  Good for factual lookups and quick overviews.

- **standard** (5-10 sources): `research_assistant` + `news_searcher` + `web_fetcher`
  Cross-references multiple sources, identifies consensus and disagreements.

- **deep** (10+ sources): `deep_researcher` — comprehensive multi-angle sweep
  Includes academic papers (`arxiv_searcher`), SEC filings (`sec_edgar_tool`),
  and synthesizes into a structured report.

**Research framework:**
1. Establish what's known (background, consensus facts)
2. Find recent developments (news search, last 90 days)
3. Identify expert perspectives and evidence quality
4. Note gaps, uncertainties, and conflicting information
5. Synthesize into actionable conclusions

**Output structure:**
- **Executive summary** (3-5 sentences, the core answer)
- **Key findings** (bulleted, specific facts with sources)
- **Context** (background, history, why it matters)
- **Uncertainties** (what is not known or contested)
- **Sources** (all URLs consulted, with titles)

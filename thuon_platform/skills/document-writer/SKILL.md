---
name: document-writer
description: |
  Write long-form documents: reports, proposals, RFP responses, research
  papers, business plans, white papers, and technical documentation. Produces
  structured multi-section documents with consistent voice and formatting.
  Use when the user asks to "write a report on", "create a document about",
  "draft a proposal for", "produce a white paper on", or "write up" anything
  longer than a few paragraphs.
when_to_use: |
  Invoke for documents >500 words that require: multiple sections, consistent
  professional voice, structured outline, citations, executive summary, or
  table of contents. For shorter content use research_assistant instead.
argument-hint: "document topic, type, and target audience"
arguments:
  - name: topic
    description: "Subject of the document"
    required: true
  - name: document_type
    description: "report | proposal | white_paper | business_plan | technical_doc"
    required: false
    default: "report"
  - name: target_length
    description: "Target word count (default: 2000)"
    required: false
    default: "2000"
  - name: audience
    description: "Target audience for tone calibration"
    required: false
    default: "executive"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [document, write, report, proposal, long-form, white-paper, draft]

thuon:
  capability: long_form_document_engine
  method: generate
  deps: [ai_engine, search_engine]
  params:
    include_executive_summary: true
    include_toc: true
  output_format: markdown
  category: content
  tier: 1
---

## Document Writer Skill

Generate professional long-form documents via `long_form_document_engine`.

**Document request:** $ARGUMENTS

**Generation pipeline:**
1. **Research phase**: gather current data via search tools if needed
2. **Outline phase**: create a structured outline with section headings
3. **Writing phase**: write each section with appropriate depth
4. **Polish phase**: ensure consistent voice, add transitions, format citations

**Document structure (auto-applied):**
- Title page with date and audience
- Executive summary (if >1000 words)
- Table of contents (if >3 sections)
- Body sections with H2/H3 hierarchy
- Conclusion and recommendations
- References/bibliography if research was conducted

**Quality standards:**
- Active voice preferred
- Specific numbers and evidence over vague claims
- Each claim supported by data or reasoning
- Consistent terminology throughout
- Plain-language executive summary even for technical docs


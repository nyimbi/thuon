---
name: memory
description: |
  Store, retrieve, and consolidate information across sessions. Save important
  facts, decisions, preferences, and context for future recall. Use when the
  user says "remember that", "save this for later", "recall what I told you
  about", "what do you know about", "forget this", or asks about prior sessions.
when_to_use: |
  Invoke for: explicitly saving facts to persistent memory, retrieving stored
  context before a task, consolidating session notes into long-term memory,
  or searching memory for relevant past information. Backed by BM25 search
  over stored notes.
argument-hint: "memory task: 'remember X' or 'recall Y'"
arguments:
  - name: action
    description: "save | recall | consolidate | search | list"
    required: true
  - name: content
    description: "Content to save, or query to recall"
    required: true
  - name: category
    description: "Category tag for organization (default: general)"
    required: false
    default: "general"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [memory, remember, recall, persist, notes, context, sessions]

thuon:
  capability: memory_consolidator
  method: consolidate
  deps: [ai_engine, rag_engine]
  params: {}
  output_format: markdown
  category: research
  tier: 1
---

## Memory Skill

Persist and retrieve information via the memory system.

**Action:** $ARGUMENTS

**Available operations:**

- **save**: Store a fact, decision, or preference permanently
  - Use `memory_consolidator` to structure and store the content
  - Tag with category for organized retrieval

- **recall**: Search stored memory for relevant context
  - BM25 search over all stored notes
  - Returns top matching memories with relevance scores
  - Use `vector_search.search(query)` for semantic matching

- **consolidate**: Summarize recent session context into long-term memory
  - Extracts key decisions, facts, and preferences from recent interactions
  - Removes redundant/duplicate memories

- **list**: Show all stored memories in a category

**Memory principles:**
- Store facts, not assumptions
- Include date context for time-sensitive information (`!$(date +"%Y-%m-%d")`)
- Avoid storing sensitive data (passwords, keys) in plain text
- Consolidate regularly to keep memory clean and relevant


---
name: code-reviewer
description: |
  Review code for bugs, security vulnerabilities, performance issues, and
  style problems. Provide actionable feedback with severity ratings and
  suggested fixes. Use when the user asks to "review this code", "check
  for bugs in", "security audit", "code review", "find issues in",
  or pastes code asking for feedback.
when_to_use: |
  Invoke for: pre-commit code review, security auditing, performance analysis,
  logic correctness checks, API design review, or any task where code needs
  systematic evaluation across multiple quality dimensions.
argument-hint: "code to review, file path, or description of what to check"
arguments:
  - name: code
    description: "Code to review (paste or file path)"
    required: true
  - name: language
    description: "Programming language (default: auto-detect)"
    required: false
    default: "auto"
  - name: focus
    description: "security | performance | correctness | style | all (default: all)"
    required: false
    default: "all"
  - name: severity_threshold
    description: "Minimum severity to report: critical | high | medium | low (default: low)"
    required: false
    default: "low"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [code, review, security, bugs, audit, quality, vulnerability, performance]

thuon:
  capability: code_writer
  method: review
  deps: [ai_engine]
  params: {}
  output_format: markdown
  category: dev
  tier: 1
---

## Code Reviewer Skill

Systematically review code across security, correctness, performance, and style.

**Code to review:** $ARGUMENTS

**Review dimensions:**

### 🔴 Critical / Security
- SQL injection, XSS, command injection, path traversal
- Hardcoded secrets/credentials
- Insecure deserialization, SSRF, XXE
- Auth bypasses, privilege escalation

### 🟠 High / Correctness
- Logic errors (off-by-one, wrong comparisons, missing cases)
- Null/undefined dereferences on reachable paths
- Race conditions, thread-safety issues
- Resource leaks (unclosed files, connections)

### 🟡 Medium / Performance
- N+1 queries, missing indexes (for SQL)
- Redundant computation in loops
- Memory inefficiency (large objects in closures, unnecessary copies)
- Blocking I/O in async code

### 🟢 Low / Style
- Non-idiomatic patterns for the language
- Missing error handling
- Overly complex expressions that could be simplified
- Dead code, unused imports

**Output format per finding:**
```
[SEVERITY] file:line — One-sentence summary
  Why: explanation of the risk
  Fix: concrete code change to make
```

**Final summary:** Overall verdict (LGTM / Minor issues / Needs work / Block),
count by severity, and the single most important change to make first.


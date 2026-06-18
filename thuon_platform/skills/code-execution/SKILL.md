---
name: code-execution
description: |
  Execute Python code in a sandboxed environment and return the output.
  Use when the user asks to "run this code", "calculate", "execute",
  "test this script", "compute", "process this data programmatically",
  or provides code that needs to be run to produce a result.
when_to_use: |
  Invoke when the user provides Python code to run, asks for a computation
  that requires code (data processing, statistical analysis, file parsing,
  API calls in code form), or needs to verify code output before deploying.
argument-hint: "Python code to execute"
arguments:
  - name: code
    description: "Python code to execute"
    required: true
  - name: timeout
    description: "Execution timeout in seconds (default: 30)"
    required: false
    default: "30"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [python, code, execution, sandbox, compute, script]

thuon:
  capability: python_executor
  method: execute
  deps: []
  params:
    timeout: 30
  output_format: text
  category: dev
  tier: 1
---

## Code Execution Skill

You can execute Python code in a sandboxed subprocess. Standard library and
common packages (pandas, numpy, requests, etc.) are available if installed.

**Code to execute:** $ARGUMENTS

**Execution guidelines:**
- Print results explicitly — the skill captures stdout/stderr
- For data analysis: load data, process, print key findings
- For file operations: use absolute paths or `/tmp/`
- Execution is isolated — no persistent state between calls
- Timeout is enforced; avoid infinite loops
- If code requires packages not installed, report which ones and suggest `uv add`

**After execution:**
- Report stdout, stderr, and exit code
- Explain what the output means in plain language
- If there were errors, diagnose the root cause and suggest a fix


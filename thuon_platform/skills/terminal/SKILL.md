---
name: terminal
description: |
  Execute terminal commands and Python scripts in a sandboxed environment.
  Use when the user asks to "run this command", "execute this script",
  "run in terminal", "shell command", "bash this", or provides code/commands
  to run. Returns stdout, stderr, and exit code.
when_to_use: |
  Invoke for: running Python scripts, data processing pipelines, build
  commands, system information queries, or any computation that requires
  code execution. Sandboxed — system commands are run via Python subprocess.
argument-hint: "command or script to run"
arguments:
  - name: code
    description: "Python code or shell commands to execute"
    required: true
  - name: timeout
    description: "Max execution time in seconds (default: 30)"
    required: false
    default: "30"
  - name: language
    description: "python | shell (default: python)"
    required: false
    default: "python"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [terminal, shell, execute, script, command, python, subprocess, bash]

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

## Terminal / Shell Execution Skill

Execute code in a sandboxed Python subprocess via `python_executor`.

**Command/Script:** $ARGUMENTS

**Execution model:**
- Python code runs directly: `python_executor.execute(code, timeout)`
- Shell commands run via: `python_executor.execute('import subprocess; result = subprocess.run([...], capture_output=True, text=True); print(result.stdout)')`
- Execution is sandboxed — no persistent environment between calls
- Standard Python stdlib + installed packages available
- Timeout enforced (default 30s); long-running processes are killed

**Output interpretation:**
- Report stdout, stderr, and exit code
- Non-zero exit code = error — diagnose and suggest fix
- For long output, summarize key lines rather than dumping everything
- If the user asks for a result value, extract it from stdout

**Security note:** Code runs as the current OS user. Do not run commands
that modify system configuration or install packages without user approval.


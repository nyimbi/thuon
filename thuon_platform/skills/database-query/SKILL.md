---
name: database-query
description: |
  Query a PostgreSQL database using SQL. Execute SELECT queries to retrieve
  and analyze data, explore schema, and generate reports from structured data.
  Use when the user asks to "query the database", "run SQL", "look up in the
  database", "how many records", "join these tables", or provides SQL.
when_to_use: |
  Invoke when the user needs to query structured data from the configured
  PostgreSQL database. Read-only by default (SELECT, WITH, EXPLAIN only).
  For write operations, the user must explicitly set readonly=false.
argument-hint: "SQL query or natural language description of what to query"
arguments:
  - name: sql
    description: "SQL SELECT query to execute"
    required: true
  - name: readonly
    description: "Enforce read-only mode (default: true)"
    required: false
    default: "true"
  - name: max_rows
    description: "Maximum rows to return (default: 1000)"
    required: false
    default: "1000"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [database, sql, postgresql, query, data, records, schema]

thuon:
  capability: sql_executor
  method: query
  deps: []
  params:
    readonly: true
    max_rows: 1000
  output_format: table
  category: data
  tier: 2
---

## Database Query Skill

Execute SQL queries via `sql_executor`.

**Requires:** `database.url` set in config.yaml (PostgreSQL connection string).

**Query:** $ARGUMENTS

**Query execution:**
```
sql_executor.query(
    sql="SELECT ...",
    params={},        # parameterized values (prevent injection)
    readonly=True,    # blocks INSERT/UPDATE/DELETE by default
    max_rows=1000
)
```

**Output includes:** columns, rows, row count, execution time, truncation flag.

**Best practices:**
- Always use parameterized queries: `WHERE id = %(id)s` with `params={'id': value}`
- Add `LIMIT` to large tables to avoid timeouts
- Use `EXPLAIN` first for performance-sensitive queries
- For schema exploration: `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '...'`

**Result formatting:**
- Present results as a markdown table
- Summarize key statistics (total rows, range of values, nulls found)
- Flag truncated results and suggest a more specific query


---
name: data-analysis
description: |
  Analyze data from spreadsheets, databases, CSV files, or provided datasets.
  Perform statistical analysis, financial calculations, generate charts, and
  produce summaries. Use when the user asks to "analyze this data", "calculate",
  "summarize this spreadsheet", "show me trends", "run stats on", or provides
  a file path to analyze.
when_to_use: |
  Invoke for: Excel/CSV analysis, financial modeling (NPV, IRR, PMT),
  statistical summaries, data quality checks, trend identification,
  SQL queries on structured data, or any quantitative analysis task.
argument-hint: "file path, dataset, or calculation to perform"
arguments:
  - name: source
    description: "File path (xlsx/csv), SQL query, or data description"
    required: true
  - name: analysis_type
    description: "summary | financial | statistical | chart | query (default: summary)"
    required: false
    default: "summary"
  - name: question
    description: "Specific question to answer about the data"
    required: false
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [data, analysis, excel, csv, statistics, financial, chart, spreadsheet]

thuon:
  capability: excel_reader
  method: read
  deps: []
  params:
    max_rows: 500
  output_format: markdown
  category: analytics
  tier: 1
---

## Data Analysis Skill

You have access to multiple data analysis tools:

**Tool selection:**
- Excel/CSV files → `excel_reader.read(file_path)`
- Financial calculations (NPV, IRR, PMT, compound) → `calculator.calculate(expr)`
- SQL databases → `sql_executor.query(sql)`
- Charts → `chart_generator.generate(chart_type, data, title)`
- Code-heavy analysis → `python_executor.execute(code)`

**Analysis request:** $ARGUMENTS

**Analysis workflow:**
1. Load the data using the appropriate tool
2. Inspect structure: row count, columns, data types, missing values
3. Compute requested statistics or answer the specific question
4. Identify key patterns, anomalies, or insights
5. If helpful, generate a chart to visualize findings
6. Summarize findings in plain language with specific numbers

**Output format:**
- Lead with the direct answer to the question
- Follow with supporting statistics
- Include a data quality note if issues were found
- Recommend next steps or deeper analyses


---
name: pdf-reader
description: |
  Extract and read text content from PDF files, including contracts, reports,
  research papers, RFPs, invoices, and other documents. Use when the user
  references a PDF file path, asks to "read this PDF", "extract text from",
  "summarize this document", or provides a PDF URL.
when_to_use: |
  Invoke when a user provides a PDF file path or URL and asks for: extraction,
  summarization, specific section lookup, table extraction, or comparison
  against another document. Works with both local files and remote URLs.
argument-hint: "PDF file path or URL"
arguments:
  - name: source
    description: "Local file path or URL to the PDF"
    required: true
  - name: pages
    description: "Page range to extract e.g. '1-5' or '3' (default: all)"
    required: false
    default: ""
  - name: task
    description: "What to do: summarize | extract_tables | find_section | full_text"
    required: false
    default: "summarize"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [pdf, document, extract, read, text, contract, report, rfp]

thuon:
  capability: pdf_extractor
  method: extract
  deps: []
  params:
    extract_tables: true
  output_format: markdown
  category: data
  tier: 1
---

## PDF Reader Skill

Extract and process content from PDF documents using `pdf_extractor`.

**Source:** $ARGUMENTS

**Extraction process:**
1. Call `pdf_extractor.extract(source, pages)`
   - Source can be a local path (`/path/to/file.pdf`) or URL
   - For large documents, extract specific pages to stay within limits
2. For tables: `pdf_extractor.extract(source, extract_tables=True)`
3. After extraction, perform the requested task:

**Task-specific instructions:**
- **summarize**: Write a structured summary with key sections, main findings, and conclusions
- **extract_tables**: List all tables found with their data in markdown format
- **find_section**: Search for the specified section or topic in the extracted text
- **full_text**: Return the complete extracted text, cleaned of headers/footers

**Quality checks:**
- Note if OCR quality is poor (garbled text from scanned PDFs)
- Flag password-protected PDFs (will show an error)
- For RFPs: extract title, deadline, scope, evaluation criteria automatically

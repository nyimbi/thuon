---
name: computer-use
description: |
  Control a web browser to perform tasks on websites: navigate pages, click
  buttons, fill forms, take screenshots, scrape dynamic content, and automate
  web workflows. Use when the user asks to "click", "fill in", "navigate to",
  "take a screenshot of", "automate on a website", or "log in to".
when_to_use: |
  Invoke for browser automation tasks: form submission, web scraping of
  JavaScript-heavy sites, UI testing, automated data entry, or any task
  requiring interaction with a live website rather than just fetching its HTML.
argument-hint: "URL and task description"
arguments:
  - name: url
    description: "URL to navigate to"
    required: true
  - name: task
    description: "What to do on the page (click, fill, screenshot, etc.)"
    required: true
  - name: selector
    description: "CSS selector or text to target (optional)"
    required: false
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [browser, automation, web, click, screenshot, form]
  compatibility:
    requires: playwright

thuon:
  capability: browser_agent
  method: navigate
  deps: []
  params: {}
  output_format: json
  category: dev
  tier: 2
---

## Computer Use / Browser Automation Skill

You have access to a headless Playwright browser via the `browser_agent` tool.

**Available browser actions:**
- `browser_agent.navigate(url)` — open a URL
- `browser_agent.click(selector)` — click an element
- `browser_agent.fill(selector, value)` — type into a field
- `browser_agent.screenshot()` — capture the current page
- `browser_agent.wait_for(selector, timeout_ms)` — wait for element
- `browser_agent.evaluate(js_code)` — run JavaScript on the page

**Task:** $ARGUMENTS

**Instructions:**
1. Navigate to the target URL first
2. Wait for the page to load (use wait_for with a key element)
3. Perform the requested actions step by step
4. Take a screenshot after key actions to verify success
5. Return the result with any extracted data or confirmation
6. Handle errors gracefully — if an element isn't found, report what IS on the page


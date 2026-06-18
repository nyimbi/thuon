---
name: browser-automation
description: |
  Automate web browser interactions: navigate pages, click elements, fill forms,
  extract data from JavaScript-heavy sites, take screenshots, and run automated
  web workflows. Use when the user asks to "automate", "scrape a dynamic site",
  "fill this form", "click the button", "screenshot this page", or "log in and
  then navigate to".
when_to_use: |
  Invoke when web content requires JavaScript execution to render, when the
  task involves multi-step browser interaction (login → navigate → extract),
  or when simple HTTP fetching (web_fetcher) won't work because the page
  is dynamically rendered.
argument-hint: "URL and browser actions to perform"
arguments:
  - name: url
    description: "Starting URL"
    required: true
  - name: actions
    description: "Sequence of actions: navigate, click, fill, screenshot, extract"
    required: true
  - name: output_type
    description: "screenshot | text | json | html (default: text)"
    required: false
    default: "text"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [browser, playwright, automation, scrape, click, form, screenshot, selenium]
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

## Browser Automation Skill

Control a Playwright browser via `browser_agent`.

**Note:** Requires playwright installed (`uv add playwright && playwright install chromium`).

**Task:** $ARGUMENTS

**Action sequence:**
1. `browser_agent.navigate(url)` — open the URL
2. `browser_agent.wait_for(selector, timeout_ms=5000)` — wait for page load
3. For extraction: `browser_agent.evaluate('document.body.innerText')`
4. For clicking: `browser_agent.click(selector)`
5. For forms: `browser_agent.fill(selector, value)`
6. For screenshots: `browser_agent.screenshot()` → returns base64 PNG
7. `browser_agent.close()` — always close when done

**Selector strategies (preference order):**
1. `[data-testid="..."]` — most stable
2. `button:has-text("Submit")` — text-based
3. `#id` — ID-based
4. CSS selector — last resort

**Common patterns:**
- Login flow: navigate → fill username → fill password → click submit → wait for redirect
- Pagination: click next → wait for load → extract → repeat
- Modal: click trigger → wait for modal → interact → close

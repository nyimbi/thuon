---
name: api-caller
description: |
  Make HTTP requests to external APIs and web services. Fetch data from REST
  APIs, webhooks, and web endpoints. Use when the user asks to "call this API",
  "fetch from this URL", "make a GET/POST request", "hit this endpoint",
  or provides an API URL to query.
when_to_use: |
  Invoke for: fetching data from REST APIs (GET/POST/PUT), calling webhooks,
  retrieving JSON/XML from web services, or any HTTP request where the URL
  and optionally request body are known. For web page reading use web-search.
argument-hint: "API URL and optional method/headers/body"
arguments:
  - name: url
    description: "API endpoint URL"
    required: true
  - name: method
    description: "HTTP method: GET | POST | PUT | DELETE (default: GET)"
    required: false
    default: "GET"
  - name: headers
    description: "JSON object of request headers (e.g. Authorization)"
    required: false
  - name: body
    description: "Request body for POST/PUT (JSON string)"
    required: false
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [api, http, rest, request, fetch, endpoint, webhook, json]

thuon:
  capability: web_fetcher
  method: fetch
  deps: []
  params:
    extract_text: false
  output_format: json
  category: research
  tier: 1
---

## API Caller Skill

Make HTTP requests via `web_fetcher`.

**API call:** $ARGUMENTS

**Request execution:**
```python
web_fetcher.fetch(
    url="https://api.example.com/endpoint",
    extract_text=False,   # False = return raw response, True = extract readable text
    selector=None         # CSS selector for HTML extraction (optional)
)
```

**For APIs requiring auth or POST body:** use `python_executor` to run requests directly:
```python
import requests, json
resp = requests.post(
    "https://api.example.com/data",
    headers={"Authorization": "Bearer TOKEN"},
    json={"key": "value"},
    timeout=15
)
print(json.dumps(resp.json(), indent=2))
```

**Response handling:**
- Parse and pretty-print JSON responses
- For errors (4xx/5xx): report status code, headers, and body
- For large responses: summarize structure and key fields
- Flag rate limit headers (X-RateLimit-*) and retry-after values

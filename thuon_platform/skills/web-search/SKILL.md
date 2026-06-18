---
name: web-search
description: |
  Search the web for current information, news, and real-time data. Use when
  the user asks about recent events, current prices, today's news, live data,
  or any topic that requires up-to-date information not in training data.
  Triggers: "search for", "look up", "find information about", "what's happening
  with", "latest news on", "current status of", "search the web".
when_to_use: |
  Invoke for any request requiring live or recent web data: news, prices,
  company announcements, sports scores, weather, regulatory updates, market
  movements, or factual lookups that may have changed since training.
argument-hint: "search query or topic"
arguments:
  - name: query
    description: "What to search for"
    required: true
  - name: source_type
    description: "news | web | arxiv (default: web)"
    required: false
    default: "web"
  - name: max_results
    description: "Maximum results to return (default: 5)"
    required: false
    default: "5"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [web, search, internet, news, research]

thuon:
  capability: web_fetcher
  method: fetch
  deps: []
  params:
    extract_text: true
  output_format: markdown
  category: research
  tier: 1
---

## Web Search Skill

You have access to real-time web search via the Thuon platform's web tools.

**Search strategy:**
1. For news queries → use `news_searcher.search(query, max_results)`
2. For academic papers → use `arxiv_searcher.search(query, max_results)`
3. For web pages/URLs → use `web_fetcher.fetch(url, extract_text=True)`
4. For site crawls → use `web_crawler.crawl(start_url, max_pages=5)`

**Query:** $ARGUMENTS

**Instructions:**
- Use the most appropriate tool for the query type
- For general web queries, search news first then fetch top results
- Cite all sources with title + URL
- Prefer results from the last 30 days for current-events queries
- Summarize findings in 3-5 clear paragraphs with key facts highlighted


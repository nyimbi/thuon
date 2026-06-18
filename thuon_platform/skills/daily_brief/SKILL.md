---
name: daily_brief
description: Generate a structured morning brief with FX rates, news digest, calendar, todos, weather, and email summaries
version: "1.0"
keywords:
  - morning brief
  - daily digest
  - news summary
  - what happened today
  - briefing
  - daily report
  - news
  - calendar today
  - todo list
  - what's on today
thuon:
  capability: daily_brief
  module: capabilities.daily_brief
  class: DailyBrief
  method: generate
  deps: [ai_engine, search_engine]
  category: research
  params:
    - name: date_str
      type: str
      required: false
      default: ""
    - name: include_sections
      type: list
      required: false
      default: [fx, weather, news, calendar, todos, economic_calendar]
---

## Daily Brief

Use this skill when the user asks for:
- "morning brief", "daily brief", "daily digest"
- "what's happening today", "news summary"
- "show me my todos", "what's on my calendar"
- "FX rates", "currency rates today"
- "weather in Nairobi"

The brief includes:
1. **FX Rates** — KES cross-rates vs USD, EUR, GBP, UGX, TZS, ZAR, CNY
2. **Weather** — current conditions and forecast for the configured location
3. **News Digest** — Kenya/East Africa business, Kenyan politics, Ukraine/Iran conflicts, FIFA World Cup, rugby (Kenya Simbas + international), polo
4. **Calendar** — today's events + next 7 days
5. **Todos** — open action items from data/todos/ and Obsidian vault, overdue first
6. **Economic Calendar** — upcoming CBK/Treasury/IMF events from RSS feeds
7. **Email summaries** — unread IMAP email (requires IMAP config)

### Configuration (config.yaml)

```yaml
daily_brief:
  weather_location: Nairobi
  imap_host: imap.gmail.com
  imap_username: you@example.com
  imap_password: app-password
```

Sections are selective — pass `include_sections` to restrict to a subset.

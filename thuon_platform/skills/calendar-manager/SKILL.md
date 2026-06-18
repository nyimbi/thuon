---
name: calendar-manager
description: |
  Read, create, and manage calendar events in .ics format. Check schedule,
  find free slots, add appointments, and summarize upcoming events. Use when
  the user asks to "check my calendar", "add a meeting", "schedule",
  "what's on my agenda", "book a slot", or "add to my schedule".
when_to_use: |
  Invoke for: reading upcoming events from a calendar file, creating new
  events (exports to .ics), finding free time slots, or summarizing the
  week's schedule. Works with any .ics calendar file.
argument-hint: "calendar action: 'show next 7 days' or 'add meeting Title at 2pm'"
arguments:
  - name: action
    description: "show | create | find_free | summarize"
    required: true
  - name: calendar_path
    description: "Path to .ics calendar file (uses config default if omitted)"
    required: false
  - name: days_ahead
    description: "Days ahead to look (default: 7)"
    required: false
    default: "7"
  - name: event_details
    description: "For create: 'Title | 2026-07-01T10:00 | 2026-07-01T11:00'"
    required: false
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [calendar, schedule, meeting, event, ics, appointment, agenda]

thuon:
  capability: calendar_tool
  method: get_events
  deps: []
  params:
    days_ahead: 7
  output_format: markdown
  category: data
  tier: 1
---

## Calendar Manager Skill

Manage calendar events using `calendar_tool`.

**Action:** $ARGUMENTS

**Available operations:**

- **Show events**: `calendar_tool.get_events(days_ahead=7, calendar_path)`
  Returns list of upcoming events with title, start, end, location

- **Create event**: `calendar_tool.create_event(title, start, end, description, location, calendar_path)`
  Datetime format: `YYYY-MM-DDTHH:MM:SS`
  Returns uid and confirms creation

**Output format:**
- For schedule views: table with Date | Time | Event | Location
- Highlight conflicts (overlapping events)
- Flag events with no end time set
- For week summary: group by day, show total meeting hours per day
- When creating: confirm details before creating, then show the event created

**Today's date:** !$(date +"%Y-%m-%d")

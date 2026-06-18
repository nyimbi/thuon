---
name: email-composer
description: |
  Read, compose, and send emails. Drafts professional emails for any context:
  business development, follow-ups, proposals, client communications, internal
  announcements. Can also read the inbox and summarize unread messages.
  Use when the user asks to "send an email", "draft a message to", "check
  my email", "read inbox", "reply to", or "compose an email for".
when_to_use: |
  Invoke for: drafting and sending emails (requires SMTP config), reading
  inbox messages (requires IMAP config), summarizing unread mail, or
  composing email drafts for human review before sending.
argument-hint: "email task: 'draft to X about Y' or 'read inbox'"
arguments:
  - name: task
    description: "What to do: draft | send | read_inbox | summarize"
    required: true
  - name: recipient
    description: "Email address(es) for draft/send tasks"
    required: false
  - name: subject
    description: "Email subject line"
    required: false
  - name: context
    description: "Context or key points to include in the email"
    required: false
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [email, compose, send, inbox, draft, communication, smtp, imap]

thuon:
  capability: email_sender
  method: send
  deps: []
  params: {}
  output_format: text
  category: data
  tier: 2
---

## Email Composer Skill

Access email via `email_sender` (outbound) and `email_reader` (inbound).

**Note:** Email requires configuration in `config.yaml`:
- Outbound: `tools.email.smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`
- Inbound: `tools.email.imap_host`, `imap_user`, `imap_password`

**Task:** $ARGUMENTS

**Task routing:**
- **draft**: Write the email body, present for human review before sending
- **send**: `email_sender.send(to, subject, body, attachments)`
- **read_inbox**: `email_reader.read_inbox(max_messages, folder)`
- **summarize**: Read inbox then summarize unread messages by priority

**Email drafting guidelines:**
- Match tone to the relationship (formal for new contacts, conversational for colleagues)
- Subject line: specific and action-oriented (not "Following up")
- Opening: address the recipient by name
- Body: one main point per paragraph, max 4 paragraphs
- CTA: one clear call-to-action at the end
- Always show the draft to the user before sending

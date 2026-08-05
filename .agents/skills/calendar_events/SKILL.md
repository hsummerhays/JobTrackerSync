---
name: calendar_events
description: Generate a pre-filled Google Calendar event link for interviews or follow-ups.
---
# Calendar Events Skill

Use this skill whenever the user asks to add an event (like an interview or phone screen) to their calendar.

## Instructions
Do not create the event via an API directly. Instead, generate a pre-filled Google Calendar event link.
Format:
`https://calendar.google.com/calendar/r/eventedit?text=[Event+Title]&details=[Description]&dates=[StartDate]/[EndDate]`

Ensure all values are URL-encoded. Present the link to the user as a clickable Markdown link.

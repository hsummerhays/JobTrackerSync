---
name: calendar_events
description: Generate a pre-filled Google Calendar event link for interviews or follow-ups.
---
# Calendar Events Skill

Use this skill whenever the user asks to add an event (like an interview or phone screen) to their calendar.

## Instructions
Do not create the event via an API directly. Instead, use the helper script to generate a pre-filled Google Calendar event link:

```bash
python create_calendar_event.py --title "[Event Title]" --description "[Optional Description]" --start "[StartDate]" --end "[EndDate]"
```

The script will automatically URL-encode the parameters and print a clickable Markdown link. Present this link directly to the user.

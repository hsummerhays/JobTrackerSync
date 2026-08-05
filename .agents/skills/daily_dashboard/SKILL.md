---
name: daily_dashboard
description: View the daily job tracking dashboard, active pipeline health, and top missing skills.
---
# Daily Dashboard Skill

Use this skill when the user wants an overview of their job search progress, daily tasks, or pipeline health.

## Commands
To print today's action queue:
`python parse_jobs.py --today`

To print the full analytics and application pipeline dashboard:
`python parse_jobs.py --dashboard`

Always format the output nicely for the user, highlighting key metrics.

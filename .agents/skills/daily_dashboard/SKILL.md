---
name: daily_dashboard
description: View the daily job tracking dashboard, active pipeline health, and top missing skills.
---
# Daily Dashboard Skill

Use this skill when the user wants an overview of their job search progress, daily tasks, or pipeline health.

## Commands

To print today's high-priority action queue (P1/P2 jobs + active pipeline):
```bash
python parse_jobs.py --dashboard
```

To print just today's apply-now list (compact view):
```bash
python parse_jobs.py --today
```

To print the full analytics dashboard (conversion rates, funnel metrics, weekly volume):
```bash
python parse_jobs.py --analytics
```

Always format the output nicely for the user, highlighting key metrics.

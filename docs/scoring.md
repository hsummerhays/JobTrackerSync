# Scoring Reference

This document explains exactly how `Fit Score`, `Priority`, `Recommendation`, and `Action` are calculated in JobTrackerSync.

---

## Fit Score (0 - 100)

The Fit Score is the sum of up to 7 weighted criteria. It is recalculated on every sync run so changes to your resume profile in `config.json` automatically propagate.

| # | Criterion | Points | Condition |
|---|-----------|--------|-----------|
| 1 | **Remote or Utah** | 20 | Location contains "remote", "ut", "utah", "salt lake", "slc", "lehi", "provo", or "ogden" |
| 2 | **Senior-level title** | 15 | Title contains: senior, lead, principal, sme, staff, architect, manager |
| 3 | **Backend / Full Stack** | 15 | Title or notes contains: backend, full stack, fullstack, full-stack, distributed, data |
| 4a | **.NET / C# match** | 20 | Title or notes contains: .net, c# |
| 4b | **Java-only match** | 10 | Title or notes contains: java, spring (but NOT .net or c#) |
| 5 | **No degree requirement** | 10 | Notes do NOT contain: degree requirement, bachelor, bs required |
| 6 | **Small/medium company** | 10 | Company Type is "Small / Medium" |
| 7 | **Legacy modernization** | 10 | Notes contain: legacy, modernization |
| 8 | **Onsite/Local penalty** | -30 | Title or notes contain: local candidate, onsite only, on-site only, must relocate, no remote |

**Maximum possible score: 100**

> Note: Criteria 4a and 4b are mutually exclusive. If both .NET and Java are present, the full 20 points are awarded.

---

## Confidence

Confidence is derived from whether the role is a priority keyword match AND has matched tech skills AND has a valid URL.

| Confidence | Condition |
|------------|-----------|
| High | Priority keyword match + tech match + valid URL |
| Medium | Priority keyword OR tech match |
| Low | Neither |

---

## Recommendation (Stars)

| Stars | Label | Condition |
|-------|-------|-----------|
| 5 | Apply Now | Fit Score >= 80 AND Confidence = High |
| 4 | Strong | Fit Score >= 60 |
| 3 | Maybe | Fit Score >= 40 |
| 2 | Low | Fit Score >= 20 |
| 1 | Skip | Fit Score < 20 OR Confidence = Low |

---

## Priority

Priority is derived from Action and Recommendation together:

| Priority | Condition |
|----------|-----------|
| P1 – Apply today | Action = Apply AND Recommendation = 5 stars |
| P2 – Apply this week | Action = Apply OR Contact Recruiter |
| P3 – Investigate | Action = Review |
| P4 – Ignore | All other cases |

---

## Action

Action is calculated based on Company Type and Recommendation:

| Action | Condition |
|--------|-----------|
| Contact Recruiter | Company Type = Recruiting Firm AND Recommendation >= 4 stars |
| Apply | Recommendation >= 4 stars (and not a Recruiting Firm) |
| Review | Recommendation = 3 stars |
| Ignore | Recommendation <= 2 stars |
| Already Applied | Tracker Status is Applied, Phone Screen, Technical Interview, Recruiter Submitted, or Waiting |

> **Recruiting Firm detection** is intentionally strict: it checks only the company *name* (not the job description) for keywords like: recruiting, staffing, placement, navigators, personnel, robert half, binit, headhunters, search partners.
> This prevents normal companies like CGI, Amazon, or Citi from being incorrectly labeled as recruiters.

---

## Company Type

Determined by keyword matching the company name (and description for non-recruiter types):

| Type | Keywords checked |
|------|-----------------|
| Recruiting Firm | recruiting, staffing, placement, navigators, personnel, robert half, binit, headhunters, search partners *(company name only)* |
| Consulting | consulting, solutions, services, cgi, pwc |
| Defense | defense, leidos, harris, lockheed, raytheon, boeing, northrop, military |
| Healthcare | health, medical, hosp, care, pharm, optum, clinical, dental |
| Financial | finance, wealth, bank, capital, valuations, investment, insurance, insurtech, credit, fidelity |
| Enterprise | FAANG list (Google, Apple, Amazon, Meta, Microsoft, etc.) |
| Small / Medium | Default (none of the above match) |

---

## Reason vs. Notes

These two fields serve distinct purposes:

- **Reason** - Short, user-facing explanation for the recommendation. Written to be scannable at a glance. Example: `Remote + .NET + small company`
- **Notes** - Longer parser-generated analyst comments. Example: `Existing company detected. Tech matches: .NET, C#. Missing: Kafka, Terraform. Legacy modernization detected.`

Keep Reason concise (one line). Notes can be multi-sentence.

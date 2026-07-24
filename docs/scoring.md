# Scoring Reference

This document explains exactly how `Fit Score`, `Priority`, `Recommendation`, and `Action` are calculated in JobTrackerSync.

---

## Fit Score (0 - 100)

The Fit Score is the sum of up to 7 weighted criteria. It is recalculated on every sync run so changes to your resume profile in `config.json` automatically propagate.

| # | Criterion | Points | Condition |
|---|-----------|--------|-----------|
| 1 | **Remote or Utah** | 20 | Location contains "remote", "ut", "utah", "salt lake", "slc", "lehi", "provo", or "ogden" |
| 2a | **Experienced title** | 15 | Title contains: senior, lead, principal, staff, architect, engineering manager, sme, mid, ii, iii, 2, 3, level ii, level iii |
| 2b | **Role match** | 10 | Title contains: software engineer, backend engineer, full stack, developer, sde, swe |
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

Confidence represents the estimated accuracy of the parser's extracted metadata and is represented as a percentage value.

| Confidence | Condition |
|------------|-----------|
| **100%** | Direct employer posting (Company identified + URL available) |
| **90%** | Company identified + URL missing |
| **70%** | Company inferred from context (no explicit company metadata block) |
| **40%** | Daily digest / summary source (such as `Jobs.utah.gov` and `Ladders`) |
| **20%** | OCR fallback with sparse content (< 50 chars context) |

---

## Recommendation (Stars)

Recommendation categories are determined by combining the **Fit Score** and the numeric **Confidence** level.

| Stars | Label | Condition |
|-------|-------|-----------|
| 5 | Apply Now | Fit Score >= 80 AND Confidence >= 90% |
| 4 | Strong | Fit Score >= 60 AND Confidence > 20% |
| 3 | Maybe | Fit Score >= 40 AND Confidence > 20% |
| 2 | Low | Fit Score >= 20 AND Confidence > 20% |
| 1 | Skip | Fit Score < 20 OR Confidence <= 20% |

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

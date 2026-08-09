---
name: manage_config
description: Use this skill to safely read and update the Job Tracker configuration (config.json), including resume skills, aliases, and tech keywords.
---

# Manage Config Skill

Use this skill whenever the user asks to "add a new skill to my profile", "update tracking criteria", or "start tracking a new technology".

## Context
The tracker uses `config.json` to define how jobs are parsed and scored. It contains:
- `skill_aliases`: A mapping of canonical skills (e.g., `"vue.js"`) to an array of variations found in job postings (e.g., `["vue", "nuxt"]`). 
- `job_type_criteria`: Contains profiles like "Software Engineer" and "Operations". Each profile tracks:
  - `resume_skills`: An array of canonical skills the user possesses. If a skill is found in a job posting but missing from here, it gets flagged as a "Missing Skill".
  - `tech_keywords`: Keywords that add fit-score credit to a job posting when matched.
  - `priority_keywords`: Keywords that automatically elevate a job's priority.
  - `skip_keywords`: Keywords that cause a job to be ignored/rejected.

## Instructions
1. First, read `config.json` to understand the current structure.
2. If adding a new skill, consider where it belongs:
   - Does it need alias normalization? (Add to `skill_aliases` block).
   - Is it a skill the user possesses? (Add to `resume_skills` list in the appropriate profile).
   - Should it grant fit-score credit? (Add to `tech_keywords` list in the appropriate profile).
3. Write a small Python script to safely load, modify, and rewrite `config.json` to ensure the JSON formatting is perfectly preserved, or use surgical text replacement. Do NOT overwrite the entire file blindly.

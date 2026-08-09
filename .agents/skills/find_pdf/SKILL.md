---
name: find_pdf
description: Use this skill to locate, query, or link a job alert PDF file by filename or substring.
---

# Find PDF Skill

Use this skill when the user asks to find, query, or link a PDF file.

## Instructions
Do not create a temporary Python script or query the database directly. Instead, use the provided Python helper script:

```bash
python find_pdf.py "<pdf_filename_or_substring>"
```

Use the helper's output to identify matching files and their `file:///` URIs. Return clickable Markdown links, preserving the filename as the link text.

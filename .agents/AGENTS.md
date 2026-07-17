# Workspace Rules for JobTrackerSync

- When the user asks to find, query, or "Link" a PDF file (e.g. `Link "some.pdf"`), do not write a scratch python script to query the database.
- Instead, use the helper script [find_pdf.py](file:///c:/HughApps/JobTrackerSync/find_pdf.py):
  ```bash
  python find_pdf.py "<pdf_filename_or_substring>"
  ```
- Use the script's output to retrieve matching rows and file URIs, then provide the clickable `file:///` links to the user.

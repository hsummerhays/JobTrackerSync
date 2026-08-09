import sqlite3
import argparse
import sys
import re
from dedup_utils import path_to_file_uri, split_multivalue_field, TERMINAL_STATUSES

# Reconfigure stdout to use utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Query the jobs database by company name.")
    parser.add_argument("query", type=str, nargs="?", default="", help="Company name (or part of it) to search for")
    parser.add_argument("--active", action="store_true", help="Only show active (non-terminal) jobs like those not Expired or Closed")
    args = parser.parse_args()

    conn = sqlite3.connect('jobs.db')
    try:
        c = conn.cursor()

        # Use NOCASE for case-insensitive matching
        query_sql = "SELECT job_id, company, position, tracker_status, notes, source_pdf, date_added FROM jobs WHERE company LIKE ? COLLATE NOCASE"
        params = [f"%{args.query}%"]
        
        if args.active:
            placeholders = ', '.join(['?'] * len(TERMINAL_STATUSES))
            query_sql += f" AND tracker_status NOT IN ({placeholders})"
            params.extend(TERMINAL_STATUSES)
            
        query_sql += " ORDER BY date_added DESC"
        
        c.execute(query_sql, tuple(params))

        results = c.fetchall()
    finally:
        conn.close()

    if not results:
        print(f"No jobs found matching '{args.query}'.")
        sys.exit(0)

    print(f"Found {len(results)} job(s) matching '{args.query}'\n")
    for i, row in enumerate(results, start=1):
        job_id, company, position, status, notes, source_pdf, date_added = row
        
        # Normalize position by removing stray leading words like 'engineer'
        position = re.sub(r'(?i)^\s*engineer\s+', '', position)
        
        print(f"**{i}. {company} — {position}**\n")
        print(f"- **ID:** `{job_id}`")
        print(f"- **Date:** {date_added}")
        print(f"- **Status:** {status}")
        
        if notes:
            import textwrap
            clean_notes = notes.replace('\r', ' ').replace('\n', ' ')
            wrapped_notes = textwrap.fill(clean_notes, width=120, subsequent_indent='  ')
            print(f"- **Notes:** {wrapped_notes}")
            
        if source_pdf:
            values = split_multivalue_field(source_pdf)
            first_pdf = values[0] if values else source_pdf.strip()
            filename = first_pdf.split('/')[-1].split('\\')[-1]
            uri = path_to_file_uri(first_pdf)

            if uri:
                print(f"- **Source PDF:**\n  📄 [{filename}]({uri})\n")

if __name__ == "__main__":
    main()

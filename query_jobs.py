import sqlite3
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Query the jobs database by company name.")
    parser.add_argument("query", type=str, help="Company name (or part of it) to search for")
    args = parser.parse_args()

    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    
    # Use NOCASE for case-insensitive matching
    c.execute(
        "SELECT job_id, company, position, tracker_status, notes FROM jobs WHERE company LIKE ? COLLATE NOCASE", 
        (f"%{args.query}%",)
    )
    
    results = c.fetchall()
    
    if not results:
        print(f"No jobs found matching '{args.query}'.")
        sys.exit(0)
        
    print(f"Found {len(results)} job(s) matching '{args.query}':\n")
    for row in results:
        job_id, company, position, status, notes = row
        print(f"[{job_id}] {company} - {position}")
        print(f"  Status: {status}")
        if notes:
            print(f"  Notes:  {notes}")
        print("-" * 40)

if __name__ == "__main__":
    main()

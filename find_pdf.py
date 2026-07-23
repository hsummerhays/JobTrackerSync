import sqlite3
import sys
import os
import pathlib
import csv
import re

# Reconfigure stdout to use utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def _word_boundary_pattern(search_term):
    """Build a case-insensitive regex that only matches search_term when it
    isn't embedded inside a longer alphanumeric run, so short terms don't
    match substrings buried inside URLs/IDs. Unlike \\b, non-alphanumeric
    separators like '_' or '-' still count as boundaries (e.g. matches
    "Franki" in "Franki_hiring.pdf")."""
    return re.compile(
        r'(?<![A-Za-z0-9])' + re.escape(search_term) + r'(?![A-Za-z0-9])',
        re.IGNORECASE,
    )

def _row_matches(row_dict, pattern):
    return any(isinstance(v, str) and pattern.search(v) for v in row_dict.values())

def find_matches(db_path, search_term):
    """Search all columns of all tables in the SQLite database for the search_term."""
    if not os.path.exists(db_path):
        return {}
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]

    pattern = _word_boundary_pattern(search_term)
    results = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info(\"{table}\")")
        cols = [c[1] for c in cursor.fetchall()]
        
        where_clauses = []
        for col in cols:
            where_clauses.append(f"\"{col}\" LIKE ?")
            
        if where_clauses:
            query = f"SELECT * FROM \"{table}\" WHERE {' OR '.join(where_clauses)}"
            params = [f"%{search_term}%"] * len(cols)
            try:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                if rows:
                    for r in rows:
                        row_dict = dict(zip(cols, r))
                        if not _row_matches(row_dict, pattern):
                            continue
                        # Output a nice file:/// link if we find a file path
                        for k, v in list(row_dict.items()):
                            if isinstance(v, str) and (v.startswith("D:\\") or v.startswith("C:\\") or "/" in v or "\\" in v) and (v.endswith(".pdf") or v.endswith(".csv") or v.endswith(".db")):
                                try:
                                    row_dict[k + "_uri"] = pathlib.Path(v).as_uri()
                                except Exception:
                                    pass
                        results.setdefault(table, []).append(row_dict)
            except Exception as e:
                # Silently ignore query errors or print if needed during debugging
                pass
    conn.close()
    return results

def find_csv_matches(csv_path, search_term):
    """Search all columns in the CSV tracker for the search_term."""
    if not os.path.exists(csv_path):
        return []
        
    matches = []
    pattern = _word_boundary_pattern(search_term)
    try:
        with open(csv_path, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if _row_matches(row, pattern):
                    row_dict = dict(row)
                    # Generate file:/// links if we find file paths in values
                    for k, v in list(row_dict.items()):
                        if isinstance(v, str) and (v.startswith("D:\\") or v.startswith("C:\\") or "/" in v or "\\" in v) and (v.endswith(".pdf") or v.endswith(".csv") or v.endswith(".db")):
                            try:
                                row_dict[k + "_uri"] = pathlib.Path(v).as_uri()
                            except Exception:
                                pass
                    matches.append(row_dict)
    except Exception as e:
        pass
    return matches

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_pdf.py <pdf_filename_or_substring>")
        sys.exit(1)
        
    search_term = sys.argv[1]
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs.db')
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'master_tracker.csv')
    
    db_results = find_matches(db_path, search_term)
    csv_results = find_csv_matches(csv_path, search_term)
    
    if not db_results and not csv_results:
        print(f"No matches found for: '{search_term}'")
        return
        
    if db_results:
        for table, rows in db_results.items():
            print(f"\n--- Matches in Table: {table} ---")
            for row in rows:
                print(row)
                
    if csv_results:
        print(f"\n--- Matches in CSV: master_tracker.csv ---")
        for row in csv_results:
            print(row)

if __name__ == '__main__':
    main()

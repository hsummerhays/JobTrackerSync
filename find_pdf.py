import sqlite3
import sys
import os
import pathlib
import csv

# Reconfigure stdout to use utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def find_matches(db_path, search_term):
    """Search all columns of all tables in the SQLite database for the search_term."""
    if not os.path.exists(db_path):
        return {}
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    
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
                    results[table] = []
                    for r in rows:
                        row_dict = dict(zip(cols, r))
                        # Output a nice file:/// link if we find a file path
                        for k, v in list(row_dict.items()):
                            if isinstance(v, str) and (v.startswith("D:\\") or v.startswith("C:\\") or "/" in v or "\\" in v) and (v.endswith(".pdf") or v.endswith(".csv") or v.endswith(".db")):
                                try:
                                    row_dict[k + "_uri"] = pathlib.Path(v).as_uri()
                                except Exception:
                                    pass
                        results[table].append(row_dict)
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
    search_term_lower = search_term.lower()
    try:
        with open(csv_path, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Search all fields in the row case-insensitively
                found = False
                for v in row.values():
                    if v and search_term_lower in v.lower():
                        found = True
                        break
                if found:
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

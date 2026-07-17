import sqlite3
import sys
import os
import pathlib

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

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_pdf.py <pdf_filename_or_substring>")
        sys.exit(1)
        
    search_term = sys.argv[1]
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs.db')
    
    results = find_matches(db_path, search_term)
    
    if not results:
        print(f"No matches found for: '{search_term}'")
        return
        
    for table, rows in results.items():
        print(f"\n--- Matches in Table: {table} ---")
        for row in rows:
            print(row)

if __name__ == '__main__':
    main()

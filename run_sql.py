import sqlite3
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Run a raw SQL query against jobs.db")
    parser.add_argument("query", help="The SQL query to execute")
    args = parser.parse_args()
    
    conn = sqlite3.connect('jobs.db')
    try:
        cursor = conn.cursor()
        cursor.execute(args.query)
        
        if args.query.strip().upper().startswith("SELECT"):
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            print(" | ".join(columns))
            print("-" * (sum(len(c) for c in columns) + (3 * (len(columns) - 1))))
            for row in rows:
                print(" | ".join(str(val) for val in row))
            print(f"\n{len(rows)} row(s) returned.")
        else:
            conn.commit()
            print(f"Query executed successfully. {cursor.rowcount} row(s) affected.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()

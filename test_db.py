
import sqlite3
import os

try:
    db_path = os.path.join(os.path.dirname(__file__), "law_database.db")
    print(f"Testing DB at: {db_path}")
    
    if not os.path.exists(db_path):
        print("❌ File does not exist!")
        exit(1)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Try to list tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"✅ Connection successful. Found {len(tables)} tables.")
    print(f"Tables: {[t[0] for t in tables]}")
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")

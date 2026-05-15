import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('law_database.db')
cur = c.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
rows = [r[0] for r in cur.fetchall()]
print(f"Tables: {len(rows)}")
for n in rows:
    cur.execute(f'SELECT COUNT(*) FROM "{n}"')
    print(f"  {cur.fetchone()[0]:>7}  {n}")

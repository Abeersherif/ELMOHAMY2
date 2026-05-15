import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('law_database.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Case 96/27 from 2020
print("=== ahkam_master: case 96/27 (2020) ===")
for r in cur.execute("SELECT ID, Hkm_No, Hkm_Year, hkm_date, titel, substr(details,1,300) FROM ahkam_master WHERE Hkm_No=96 AND Hkm_Year=27"):
    print(f"  ID={r[0]} {r[4]} date={r[3]}")
    print(f"    {(r[5] or '').replace(chr(10),' ')[:300]}")
    print()

# Case 124/25 from 2007 (we know it's ID 7276)
print("=== Case 124/25 (2007) ===")
for r in cur.execute("SELECT ID, hkm_date, titel FROM ahkam_master WHERE Hkm_No=124 AND Hkm_Year=25"):
    print(f"  ID={r[0]} {r[2]} date={r[1]}")

# Now what does the user's wrong path return: fetch_rulings_for(59, 1945, 58) right now
print("\n=== Live: fetch_rulings_for(59, 1945, 58) ===")
import logging; logging.disable(logging.WARNING)
from agents.retrieval_agent import RetrievalAgent
ra = RetrievalAgent(db_path='law_database.db')
rs = ra.fetch_rulings_for(59, 1945, 58, limit=8)
print(f"  returned {len(rs)} rulings")
for r in rs[:8]:
    tag = "[LINKED]" if r['linked'] else "[KW]"
    print(f"  {tag} ID={r['id']} {r['titel'][:80]}  date={r['date']}")

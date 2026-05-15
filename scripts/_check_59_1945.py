import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('law_database.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# What law is T_No=59, T_Year=1945 in tash_master?
print("=== tash_master rows where T_No=59 AND T_Year=1945 ===")
for r in cur.execute("SELECT Tash_id, tash_name, law_name FROM tash_master WHERE T_No=59 AND T_Year=1945"):
    print(f"  Tash_id={r['Tash_id']}")
    print(f"  law_name = {r['law_name']!r}")
    print(f"  tash_name = {(r['tash_name'] or '')[:250]}")

# Article 58 of that
print("\n=== tash_mowad article 58 in those Tash_ids ===")
for r in cur.execute("SELECT _id, Tash_id, number, titel, substr(details,1,200) AS snip FROM tash_mowad WHERE number=58 AND Tash_id IN (SELECT Tash_id FROM tash_master WHERE T_No=59 AND T_Year=1945)"):
    print(f"  _id={r['_id']} Tash_id={r['Tash_id']} titel={r['titel']}")
    print(f"    {r['snip']!r}")

# What rulings link to that mda_id?
print("\n=== Linked rulings ===")
mda_rows = cur.execute("SELECT _id FROM tash_mowad WHERE number=58 AND Tash_id IN (SELECT Tash_id FROM tash_master WHERE T_No=59 AND T_Year=1945)").fetchall()
for m in mda_rows:
    mda_id = m['_id']
    for r in cur.execute("SELECT am.ID, am.titel, am.hkm_date, substr(am.details,1,200) AS snip FROM ahkam_master am JOIN Tash_ahkam ta ON ta.hkm_id=am.ID WHERE ta.mda_id=?", (mda_id,)):
        print(f"  ruling ID={r['ID']} {r['titel']}")
        print(f"    {r['snip']!r}")

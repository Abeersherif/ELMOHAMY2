"""Probe the law DB for any cancellation/repeal signals."""
import sqlite3, sys, re
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('law_database.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1) Look at columns across all law tables — is there a status column?
print("=== Distinct column names across all law tables ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'قانون%'")
tables = [r['name'] for r in cur.fetchall()]
col_counts = {}
for t in tables[:80]:
    cur.execute(f'PRAGMA table_info("{t}")')
    for r in cur.fetchall():
        col_counts[r[1]] = col_counts.get(r[1], 0) + 1
for c, n in sorted(col_counts.items(), key=lambda x: -x[1])[:30]:
    print(f"  {n:4} tables: {c}")

# 2) Does any column name hint at cancellation/status?
print("\n=== Columns with hint of status/cancel ===")
hint_words = ['cancel', 'الغ', 'ملغ', 'status', 'state', 'active', 'حال', 'منسوخ', 'مستبدل', 'سار', 'نفاذ']
for c in col_counts:
    if any(h in c.lower() for h in hint_words):
        print(f"  → {c}")

# 3) Search article details for cancellation keywords
print("\n=== Sample articles containing cancellation keywords in details ===")
keywords = ["ملغى", "ملغاه", "ملغاة", "ملغية", "ألغي", "أُلغي", "أُلغيت", "منسوخ", "تم إلغاء", "مستبدل"]
for t in tables[:20]:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        if 'details' not in cols: continue
        cur.execute(f'SELECT rowid, titel, details FROM "{t}" WHERE ' +
                    ' OR '.join([f'details LIKE ?']*len(keywords)) + ' LIMIT 2',
                    tuple(f'%{k}%' for k in keywords))
        rows = cur.fetchall()
        if rows:
            print(f"\n  [{t}]")
            for r in rows:
                snip = (r['details'] or '')[:200].replace('\n', ' ')
                print(f"    rowid={r['rowid']} titel={(r['titel'] or '')[:60]}")
                print(f"       …{snip}…")
                break
    except Exception as e:
        pass

# 4) Show samples of titles that look like "إلغاء قانون..." (laws that ARE the cancellation)
print("\n=== Sample titles that announce a cancellation ===")
for t in tables[:30]:
    try:
        cur.execute(f'SELECT rowid, titel FROM "{t}" WHERE titel LIKE ? OR titel LIKE ? LIMIT 1',
                    ('%إلغاء%', '%الغاء%'))
        r = cur.fetchone()
        if r:
            print(f"  [{t}] rowid={r['rowid']}: {(r['titel'] or '')[:120]}")
    except Exception: pass

conn.close()

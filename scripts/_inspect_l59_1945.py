"""Find article 58 of Law 59/1945 in the DB and check digit forms."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('law_database.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Try multiple digit variants
for ascii_digits, ai_digits in [('59', '٥٩'), ('1945', '١٩٤٥'), ('58', '٥٨')]:
    print(f"\n--- searching for {ascii_digits!r} (ASCII) and {ai_digits!r} (Arabic-Indic) ---")

# 1) Find any table whose law_name mentions 59 and 1945
print("\n=== Tables/rows whose law_name contains '59' and '1945' ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'قانون%'")
tables = [r['name'] for r in cur.fetchall()]
hits = 0
for t in tables:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        if 'law_name' not in cols:
            continue
        cur.execute(
            f'SELECT rowid, law_name, titel, number FROM "{t}" '
            f'WHERE (law_name LIKE ? OR law_name LIKE ?) '
            f'  AND (law_name LIKE ? OR law_name LIKE ?) LIMIT 3',
            ('%59%', '%٥٩%', '%1945%', '%١٩٤٥%')
        )
        rows = cur.fetchall()
        for r in rows:
            hits += 1
            print(f"  [{t}] rowid={r['rowid']}  number={r['number']!r}  titel={(r['titel'] or '')[:50]}")
            print(f"      law_name={(r['law_name'] or '')[:120]}")
            if hits >= 12:
                break
    except Exception:
        pass
    if hits >= 12:
        break

# 2) Look at the `number` column values format — are they ASCII or Arabic-Indic?
print("\n=== Sample `number` values across tables ===")
for t in tables[:5]:
    try:
        cur.execute(f'SELECT DISTINCT number FROM "{t}" WHERE number IS NOT NULL LIMIT 5')
        nums = [r['number'] for r in cur.fetchall()]
        print(f"  [{t}] number samples: {nums}")
    except Exception:
        pass

# 3) Find article 58 specifically in any table where law_name has 59/1945
print("\n=== Searching specifically for article 58 within law 59/1945 ===")
for t in tables:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        if 'law_name' not in cols or 'number' not in cols:
            continue
        cur.execute(
            f'SELECT rowid, law_name, titel, number, substr(details,1,250) AS snippet FROM "{t}" '
            f'WHERE (law_name LIKE ? OR law_name LIKE ?) '
            f'  AND (law_name LIKE ? OR law_name LIKE ?) '
            f"  AND (number IN ('58','٥٨') OR titel LIKE '%58%' OR titel LIKE '%٥٨%') LIMIT 3",
            ('%59%', '%٥٩%', '%1945%', '%١٩٤٥%')
        )
        for r in cur.fetchall():
            print(f"  [{t}] rowid={r['rowid']} number={r['number']!r} titel={r['titel']}")
            print(f"      law_name={(r['law_name'] or '')[:120]}")
            print(f"      snippet: {(r['snippet'] or '')[:200]}")
            print()
    except Exception:
        pass

conn.close()

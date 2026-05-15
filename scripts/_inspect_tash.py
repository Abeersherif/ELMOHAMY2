"""Probe the judicial-rulings tables for how to cross-reference articles."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('law_database.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

for t in ['Tash_ahkam', 'tash_master', 'ahkam_master', 'tash_mowad', 'tash_keywords']:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [(r[1], r[2]) for r in cur.fetchall()]
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        n = cur.fetchone()[0]
        print(f"\n=== {t}  ({n:,} rows) ===")
        for name, typ in cols:
            print(f"  {name}  ({typ})")
        # sample
        cur.execute(f'SELECT * FROM "{t}" LIMIT 1')
        r = cur.fetchone()
        if r:
            print("\n  sample row:")
            for k in r.keys():
                v = r[k]
                s = (v if isinstance(v, str) else str(v))[:160]
                print(f"    {k!r}: {s!r}")
    except Exception as e:
        print(f"\n=== {t}: ERROR {e} ===")

# Now check: can we find rulings mentioning مادة 58 ?
print("\n\n=== Rulings mentioning مادة 58 + 1945 (sample) ===")
for t in ['Tash_ahkam', 'tash_master', 'ahkam_master', 'tash_mowad']:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        text_col = None
        for c in ('details', 'text', 'mwd_text', 'tash_text', 'content', 'tash_name'):
            if c in cols:
                text_col = c; break
        if not text_col:
            print(f"  [{t}] no text-like column")
            continue
        cur.execute(f'SELECT rowid, {text_col} FROM "{t}" WHERE {text_col} LIKE ? AND {text_col} LIKE ? LIMIT 3',
                    ('%مادة 58%', '%1945%'))
        rows = cur.fetchall()
        if rows:
            print(f"  [{t}] text_col={text_col}: {len(rows)} hits")
            for r in rows[:2]:
                s = (r[text_col] or '')[:300].replace('\n', ' ')
                print(f"    rowid={r['rowid']}: {s}...")
        else:
            print(f"  [{t}] text_col={text_col}: 0 hits for مادة 58 + 1945")
    except Exception as e:
        print(f"  [{t}] err: {e}")

# Constitutional court rulings keyword
print("\n=== Anything mentioning المحكمة الدستورية + 1945 ===")
for t in ['Tash_ahkam', 'tash_master', 'ahkam_master']:
    try:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        for tc in ('details', 'text', 'tash_text', 'tash_name'):
            if tc in cols:
                cur.execute(f'SELECT rowid, {tc} FROM "{t}" WHERE {tc} LIKE ? AND {tc} LIKE ? LIMIT 2',
                            ('%الدستورية%', '%1945%'))
                rows = cur.fetchall()
                if rows:
                    print(f"  [{t}/{tc}] {len(rows)} hits")
                    for r in rows:
                        s = (r[tc] or '')[:250].replace('\n', ' ')
                        print(f"    rowid={r['rowid']}: {s}...")
                break
    except Exception: pass

conn.close()

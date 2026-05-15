import sqlite3
import logging
from typing import List, Dict, Any, Tuple, Optional

from utils import (
    detect_cancellation,
    extract_legal_refs,
    normalize_arabic_simple as _normalize_arabic_simple,
)

logger = logging.getLogger("mohamy.retrieval")

class RetrievalAgent:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.law_tables = self._discover_law_tables()
        logger.info(f"📘 Final law tables detected: {self.law_tables}")

        self.semantic_laws, self.semantic_corpus = self._load_all_law_texts()
        logger.info(f"📘 Semantic entries loaded: {len(self.semantic_corpus)}")
        logger.info("📚 Loading complete.")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _discover_law_tables(self) -> List[str]:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = cur.fetchall()

        raw = [r[0] for r in rows]
        logger.info(f"📘 Raw tables found in DB: {raw}")

        valid = []

        for t in raw:
            if t.startswith("sqlite_"):
                continue
            if t.startswith("tash_"):
                continue
            if t in ["combined_laws", "all_laws"]:
                logger.info(f"⏭️ Skipping master table: {t}")
                continue
            if t == "قاننون":
                logger.warning("⚠️ Ignoring table exactly named 'قاننون'.")
                continue
            if t == "قانون":
                logger.warning("⚠️ Ignoring general table named exactly 'قانون'.")
                continue
            if "قانون" in t or "قوانين" in t:
                valid.append(t)
                logger.info(f"✓ Including law table: {t}")

        if not valid:
            logger.error("❌ NO specific law tables found in database!")
            logger.error(f"📋 Available tables were: {', '.join(raw)}")

        return valid

    def _load_all_law_texts(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        laws = []
        corpus = []

        conn = self._connect()
        cur = conn.cursor()

        for table in self.law_tables:
            try:
                cur.execute(f'SELECT rowid AS _rid, * FROM "{table}" LIMIT 50000')
                rows = cur.fetchall()

                if not rows:
                    continue

                for row in rows:
                    columns = row.keys()

                    law_name = row["law_name"] if "law_name" in columns else table
                    titel = row["titel"] if "titel" in columns else ""
                    details = row["details"] if "details" in columns else ""
                    main_cat = row["main_category"] if "main_category" in columns else ""
                    number = row["number"] if "number" in columns else None

                    text = f"{law_name} {titel} {details}".strip()

                    cancel_info = detect_cancellation(details, titel)

                    laws.append({
                        "id": row["_rid"],
                        "law_name": law_name,
                        "table": table,
                        "titel": titel,
                        "details": details,
                        "main_category": main_cat,
                        "number": number,
                        "is_cancelled": cancel_info["is_cancelled"],
                        "cancellation_signal": cancel_info["signal"],
                        "replacement": cancel_info["replacement"],
                        "full_text": text
                    })

                    corpus.append(text)

            except Exception as e:
                logger.error(f"❌ Error loading from table {table}: {e}")

        return laws, corpus

    def fetch_rulings_by_article_topic(
        self,
        article_details: str,
        article_num: Optional[int] = None,
        limit: int = 4,
    ) -> List[Dict[str, Any]]:
        """Surface rulings that share distinctive vocabulary with an article body.

        Useful for finding constitutional/cassation rulings whose own text
        doesn't cite the article number explicitly but discusses the same legal
        construct (e.g. the 2007 const ruling on supply-law owner liability).
        """
        if not article_details:
            return []

        import re as _re
        text = article_details.strip()

        # Manually walk consecutive 4+ char Arabic words to form OVERLAPPING bigrams
        # and trigrams. This guarantees we pick up e.g. "صاحب المحل" even when it
        # also appears inside a larger phrase like "يكون صاحب المحل".
        words = _re.findall(r"[ء-ي]{4,}", text)
        stopword_starts = {"اذا", "اذ", "وان", "كان", "لما", "وقد", "بان",
                            "هذا", "ذلك", "هذه", "يكون", "يعاقب", "ويعاقب",
                            "حيث", "اذا", "والتي", "الذي", "التي"}

        bigrams: List[str] = []
        trigrams: List[str] = []
        seen: set = set()
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w1 in stopword_starts:
                continue
            b = f"{w1} {w2}"
            if 9 <= len(b) <= 24 and b not in seen:
                seen.add(b)
                bigrams.append(b)
            if i + 2 < len(words):
                w3 = words[i + 2]
                t = f"{w1} {w2} {w3}"
                if 12 <= len(t) <= 32 and t not in seen:
                    seen.add(t)
                    trigrams.append(t)

        # Bigrams first — they're more permissive matches, more likely to hit
        # paraphrased rulings (e.g. constitutional rulings that don't use the
        # exact 3-word phrase from the article).
        phrases = bigrams[:6] + trigrams[:2]

        if not phrases:
            return []

        # Cap phrases hard — each LIKE on 524k rows is slow.
        # We only need constitutional rulings here (cassation come via the linked path).
        phrases = phrases[:3]

        constitutional: List[Dict[str, Any]] = []
        seen_ids: set = set()

        def _row_to_dict(r):
            return {
                "id": r["ID"], "titel": r["titel"],
                "date": str(r["hkm_date"] or ""),
                "snippet": (r["snippet"] or "").strip(),
                "linked": False,
            }

        conn = self._connect()
        try:
            cur = conn.cursor()
            # Ensure index on MASTER_ID exists so the partition scan is instant.
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_ahkam_master_id "
                "ON ahkam_master(MASTER_ID)"
            )
            for phrase in phrases:
                like = f"%{phrase}%"
                # ONLY scan the Constitutional Court partition (MASTER_ID=4, ~3054 rows).
                # Skip the full-table scans entirely — they were causing 12s+ timeouts.
                cur.execute(
                    "SELECT ID, titel, hkm_date, substr(details, 1, 800) AS snippet "
                    "FROM ahkam_master "
                    "WHERE MASTER_ID = 4 AND details LIKE ? "
                    "ORDER BY hkm_date DESC LIMIT 3",
                    (like,),
                )
                for r in cur.fetchall():
                    if r["ID"] in seen_ids:
                        continue
                    seen_ids.add(r["ID"])
                    constitutional.append(_row_to_dict(r))
                if len(constitutional) >= limit:
                    break

            return constitutional[:limit]
        except Exception as e:
            logger.error(f"❌ fetch_rulings_by_article_topic error: {e}")
            return []
        finally:
            conn.close()

    def verify_law_exists(self, law_no: int, year: int) -> bool:
        """Check if a law identified by (T_No, T_Year) exists in tash_master."""
        conn = self._connect()
        try:
            r = conn.execute(
                "SELECT 1 FROM tash_master WHERE T_No = ? AND T_Year = ? LIMIT 1",
                (law_no, year),
            ).fetchone()
            return bool(r)
        except Exception:
            return False
        finally:
            conn.close()

    def find_similar_laws(
        self,
        law_no: int,
        year: int,
        article_num: Optional[int] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Suggest existing laws — used when the cited (T_No, T_Year) doesn't exist.

        Priority:
          1. Same year + has the cited article number (most likely the user's intent)
          2. Same year (any article)
          3. Digit-transpositions of the law number (e.g. 59 ↔ 95) in the same year
        """
        suggestions: List[Dict[str, Any]] = []
        seen: set = set()

        def _add(r, reason):
            key = (r["T_No"], r["T_Year"])
            if key in seen:
                return
            seen.add(key)
            suggestions.append({
                "T_No": r["T_No"],
                "T_Year": r["T_Year"],
                "law_name": r["law_name"] or "",
                "tash_name": (r["tash_name"] or "").strip()[:240],
                "reason": reason,
            })

        conn = self._connect()
        try:
            cur = conn.cursor()
            # 1) Same year + cited article number → most likely correction
            if article_num is not None:
                cur.execute(
                    """
                    SELECT DISTINCT tm.T_No, tm.T_Year, tm.law_name, tm.tash_name
                    FROM tash_master tm
                    JOIN tash_mowad mw ON mw.Tash_id = tm.Tash_id
                    WHERE tm.T_Year = ? AND mw.number = ?
                    ORDER BY tm.T_No
                    LIMIT ?
                    """,
                    (year, article_num, limit * 2),
                )
                for r in cur.fetchall():
                    _add(r, f"نفس السنة ({year}) ويتضمن المادة {article_num}")

            # 2) Digit-transposed law_no with same year
            digits = str(law_no)
            if len(digits) >= 2:
                permutations = {digits[::-1]}  # reverse
                # swap adjacent digits
                for i in range(len(digits) - 1):
                    p = list(digits)
                    p[i], p[i + 1] = p[i + 1], p[i]
                    permutations.add("".join(p))
                permutations.discard(digits)
                for p in permutations:
                    try:
                        cur.execute(
                            "SELECT T_No, T_Year, law_name, tash_name FROM tash_master "
                            "WHERE T_No = ? AND T_Year = ? LIMIT 1",
                            (int(p), year),
                        )
                        r = cur.fetchone()
                        if r:
                            _add(r, f"رقم قانون مشابه ({p} بدل {law_no}) في نفس السنة")
                    except (ValueError, TypeError):
                        pass

            return suggestions[:limit]
        except Exception as e:
            logger.error(f"❌ find_similar_laws error: {e}")
            return []
        finally:
            conn.close()

    def resolve_law_no_year(self, law_name_hint: str) -> Optional[Tuple[int, int]]:
        """Find (T_No, T_Year) in tash_master by matching its law_name to a hint."""
        if not law_name_hint:
            return None
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT T_No, T_Year FROM tash_master "
                "WHERE T_No IS NOT NULL AND T_Year IS NOT NULL "
                "  AND law_name LIKE ? LIMIT 1",
                (f"%{law_name_hint}%",),
            )
            r = cur.fetchone()
            if r and r["T_No"] and r["T_Year"]:
                return (int(r["T_No"]), int(r["T_Year"]))
            return None
        except Exception:
            return None
        finally:
            conn.close()

    _rulings_cache: Dict[Tuple[int, int, int, int], List[Dict[str, Any]]] = {}
    _rulings_cache_max = 512

    def fetch_rulings_for(
        self, law_no: int, year: int, article_num: int, limit: int = 8
    ) -> List[Dict[str, Any]]:
        """Find judicial rulings that interpret a specific article.

        Cached in-memory by (law_no, year, article_num, limit) — repeat queries
        on the same article (within process lifetime) return in microseconds.

        Returns up to `limit` rulings, mixed from:
          • Tash_ahkam-linked rulings (precise, mostly cassation/lower courts)
          • Keyword search on ahkam_master.details for the same article reference
            (catches constitutional-court rulings not in the link table).
        """
        cache_key = (int(law_no), int(year), int(article_num), int(limit))
        cached = RetrievalAgent._rulings_cache.get(cache_key)
        if cached is not None:
            logger.info(
                f"⚡ rulings cache hit for ({law_no}/{year}, art {article_num})"
            )
            return list(cached)  # defensive copy

        rulings: List[Dict[str, Any]] = []
        keyword_quota = max(2, limit // 3)         # reserve ~1/3 for keyword hits
        linked_quota = limit - keyword_quota

        conn = self._connect()
        try:
            cur = conn.cursor()

            # PRIMARY: linked rulings
            cur.execute(
                """
                SELECT DISTINCT am.ID, am.titel, am.hkm_date,
                       substr(am.details, 1, 800) AS snippet
                FROM ahkam_master am
                JOIN Tash_ahkam ta ON ta.hkm_id = am.ID
                WHERE ta.mda_id IN (
                    SELECT _id FROM tash_mowad
                    WHERE number = ?
                      AND Tash_id IN (
                        SELECT Tash_id FROM tash_master
                        WHERE T_No = ? AND T_Year = ?
                      )
                )
                ORDER BY am.hkm_date DESC
                LIMIT ?
                """,
                (article_num, law_no, year, linked_quota),
            )
            for r in cur.fetchall():
                rulings.append({
                    "id": r["ID"],
                    "titel": r["titel"],
                    "date": str(r["hkm_date"] or ""),
                    "snippet": (r["snippet"] or "").strip(),
                    "linked": True,
                })

            existing_ids = {r["id"] for r in rulings}

            # SECONDARY: keyword search — catches constitutional rulings not linked
            placeholders = ",".join(["?"] * len(existing_ids)) if existing_ids else "NULL"
            for art_pattern in (f"%المادة {article_num}%", f"%مادة {article_num}%"):
                cur.execute(
                    f"""
                    SELECT ID, titel, hkm_date, substr(details, 1, 800) AS snippet
                    FROM ahkam_master
                    WHERE details LIKE ? AND details LIKE ? AND details LIKE ?
                      AND ID NOT IN ({placeholders})
                    ORDER BY hkm_date DESC
                    LIMIT ?
                    """,
                    (
                        art_pattern,
                        f"%{law_no} لسنة {year}%",
                        f"%{year}%",
                        *existing_ids,
                        keyword_quota,
                    ),
                )
                for r in cur.fetchall():
                    if r["ID"] in existing_ids:
                        continue
                    existing_ids.add(r["ID"])
                    rulings.append({
                        "id": r["ID"],
                        "titel": r["titel"],
                        "date": str(r["hkm_date"] or ""),
                        "snippet": (r["snippet"] or "").strip(),
                        "linked": False,
                    })
                    if len([r for r in rulings if not r["linked"]]) >= keyword_quota:
                        break
                if len([r for r in rulings if not r["linked"]]) >= keyword_quota:
                    break

            # FINAL FALLBACK: if we still found nothing (e.g. user typed wrong law_no),
            # broaden to article-number + year keyword search alone.
            if not rulings:
                cur.execute(
                    """
                    SELECT ID, titel, hkm_date, substr(details, 1, 800) AS snippet
                    FROM ahkam_master
                    WHERE (details LIKE ? OR details LIKE ?)
                      AND details LIKE ?
                    ORDER BY hkm_date DESC
                    LIMIT ?
                    """,
                    (
                        f"%مادة {article_num}%",
                        f"%المادة {article_num}%",
                        f"%{year}%",
                        limit,
                    ),
                )
                for r in cur.fetchall():
                    rulings.append({
                        "id": r["ID"],
                        "titel": r["titel"],
                        "date": str(r["hkm_date"] or ""),
                        "snippet": (r["snippet"] or "").strip(),
                        "linked": False,
                    })

            # Sort: linked first, newest first within each group
            rulings.sort(key=lambda r: (
                not r["linked"],
                -(int((r["date"] or "0000")[:4]) if (r["date"] or "")[:4].isdigit() else 0)
            ))
            final = rulings[:limit]
            # Evict oldest entry if cache is full (simple FIFO)
            if len(RetrievalAgent._rulings_cache) >= RetrievalAgent._rulings_cache_max:
                first_key = next(iter(RetrievalAgent._rulings_cache))
                RetrievalAgent._rulings_cache.pop(first_key, None)
            RetrievalAgent._rulings_cache[cache_key] = list(final)
            return final
        except Exception as e:
            logger.error(f"❌ fetch_rulings_for error: {e}")
            return []
        finally:
            conn.close()

    def _keyword_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        results = []
        q = query.lower()

        for item in self.semantic_laws:
            text = item["full_text"].lower()

            score = 0
            for word in q.split():
                if word in text:
                    score += 1

            if score > 0:
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        results = [item for score, item in results[:top_k]]

        return results

    def retrieve(self, user_query: str, extracted_concepts: Dict[str, Any], target_tables: List[str] = None, top_k: int = 20) -> List[Dict[str, Any]]:
        # Step 1: extract explicit legal refs from the user's text
        refs = extract_legal_refs(user_query)
        article_numbers = refs.get("article_numbers") or []
        law_refs = refs.get("law_refs") or []
        years = refs.get("years") or []
        if article_numbers or law_refs or years:
            logger.info(
                f"🔖 Legal refs in query: articles={article_numbers} "
                f"laws={law_refs} years={years}"
            )

        if target_tables:
            filtered_laws = [law for law in self.semantic_laws if law['table'] in target_tables]
            logger.info(f"🔍 Filtering by tables: {target_tables}")
            logger.info(f"📚 Filtered to {len(filtered_laws)} articles from target tables")
        else:
            filtered_laws = self.semantic_laws
            logger.info(f"📚 No table filter - searching all {len(filtered_laws)} articles")

        # Step 2: precise lookup — if the user named an article number, scan ALL laws.
        # Rank precise hits by token overlap with the query and diversify across tables.
        precise_hits: List[Dict[str, Any]] = []
        if article_numbers:
            wanted = {str(n) for n in article_numbers}
            q_norm_pre = _normalize_arabic_simple(user_query)
            q_tokens_pre = [
                w for w in q_norm_pre.split()
                if len(w) > 1 and w not in {"ما", "هو", "هي", "في", "من", "على", "عن",
                                            "ال", "و", "ثم", "او", "بل", "لا", "هل"}
            ]
            candidates = []
            for law in self.semantic_laws:
                num = str(law.get("number") or "").strip()
                if not num or num not in wanted:
                    continue

                table_norm = _normalize_arabic_simple(law.get("table") or "")
                law_norm = _normalize_arabic_simple(law.get("law_name") or "")
                full_norm = _normalize_arabic_simple(law.get("full_text") or "")

                score = 0
                for tok in q_tokens_pre:
                    if tok in wanted:
                        continue  # already matched via number
                    if tok in table_norm:
                        score += 8
                    if tok in law_norm:
                        score += 5
                    if tok in full_norm:
                        score += 1
                    # Fuzzy stem overlap: catches تمويل↔تموين, تمويلي↔تمويل, etc.
                    stem = tok
                    if stem.startswith("ال") and len(stem) > 4:
                        stem = stem[2:]
                    if len(stem) > 4 and stem.endswith(("ون", "ين", "ات")):
                        stem = stem[:-2]
                    if len(stem) >= 4:
                        prefix = stem[:4]
                        if prefix in table_norm:
                            score += 4
                        if prefix in law_norm:
                            score += 2
                if years and any(y in law_norm or y in full_norm for y in years):
                    score += 12

                candidates.append((score, law))

            # Sort by score desc, then diversify: at most 2 per table, top 10 total
            candidates.sort(key=lambda x: x[0], reverse=True)
            per_table = {}
            for sc, law in candidates:
                t = law.get("table")
                if per_table.get(t, 0) >= 2:
                    continue
                per_table[t] = per_table.get(t, 0) + 1
                precise_hits.append(law)
                if len(precise_hits) >= 10:
                    break

            logger.info(
                f"🎯 Precise article-number hits: {len(precise_hits)} of "
                f"{len(candidates)} total candidates (numbers={list(wanted)}, years={years})"
            )

        if not filtered_laws and not precise_hits:
            logger.warning(f"⚠️ No articles found in target tables: {target_tables}")
            return []

        results = []
        q_norm = _normalize_arabic_simple(user_query)

        stopwords = {
            "ما", "هو", "هي", "في", "من", "على", "عن", "ان", "أن", "كان", "هل",
            "كيف", "اين", "متى", "لماذا", "ال", "و", "ثم", "او", "بل", "لا",
            "لم", "لن", "كل", "مع", "بين", "حول", "شرح", "اريد", "ابحث"
        }

        q_tokens = [w for w in q_norm.split() if w not in stopwords and len(w) > 1]

        if not q_tokens:
            q_tokens = q_norm.split()

        logger.info(f"🔍 Search Tokens: {q_tokens}")

        for item in filtered_laws:
            text_norm = _normalize_arabic_simple(item["full_text"])
            title_norm = _normalize_arabic_simple(item["titel"])

            score = 0

            for token in q_tokens:
                if token in title_norm:
                    score += 10

                count = text_norm.count(token)
                if count > 0:
                    score += count + 1

            if len(results) < 10:
                logger.debug(f"📊 Score={score} | Title: {item['titel'][:50]} | Law: {item['law_name'][:50]}")

            if score > 0:
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        scored = [item for score, item in results[:top_k]]

        # Prepend precise hits, deduped by (table, id). Keep order, cap at top_k.
        seen = set()
        final_results: List[Dict[str, Any]] = []
        for item in precise_hits + scored:
            key = (item.get("table"), item.get("id"))
            if key in seen:
                continue
            seen.add(key)
            final_results.append(item)
            if len(final_results) >= top_k:
                break

        if final_results:
            top = final_results[0]
            tag = "(precise)" if precise_hits and (top.get("table"), top.get("id")) in {
                (p.get("table"), p.get("id")) for p in precise_hits
            } else ""
            logger.info(f"🏆 Top Result: {top['titel']} {tag}")

        return final_results

import sqlite3
import logging
from typing import List, Dict, Any, Tuple

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
                cur.execute(f'SELECT * FROM "{table}" LIMIT 50000')
                rows = cur.fetchall()

                if not rows:
                    continue

                for row in rows:
                    columns = row.keys()

                    law_name = row["law_name"] if "law_name" in columns else table
                    titel = row["titel"] if "titel" in columns else ""
                    details = row["details"] if "details" in columns else ""
                    main_cat = row["main_category"] if "main_category" in columns else ""

                    text = f"{law_name} {titel} {details}".strip()

                    laws.append({
                        "law_name": law_name,
                        "table": table,
                        "titel": titel,
                        "details": details,
                        "main_category": main_cat,
                        "full_text": text
                    })

                    corpus.append(text)

            except Exception as e:
                logger.error(f"❌ Error loading from table {table}: {e}")

        return laws, corpus

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
        if target_tables:
            filtered_laws = [law for law in self.semantic_laws if law['table'] in target_tables]
            logger.info(f"🔍 Filtering by tables: {target_tables}")
            logger.info(f"📚 Filtered to {len(filtered_laws)} articles from target tables")
        else:
            filtered_laws = self.semantic_laws
            logger.info(f"📚 No table filter - searching all {len(filtered_laws)} articles")

        if not filtered_laws:
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
        final_results = [item for score, item in results[:top_k]]

        if final_results:
            top = final_results[0]
            logger.info(f"🏆 Top Result: {top['titel']} (Score hidden)")

        return final_results

def _normalize_arabic_simple(text: str) -> str:
    import re
    if not text:
        return ""
    text = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)
    text = re.sub(r'[؟!.,،؛:""«»\'"\(\)\[\]\{\}]', ' ', text)
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'[ةه]', 'ه', text)
    text = re.sub(r'[يى]', 'ي', text)
    return text.strip().lower()

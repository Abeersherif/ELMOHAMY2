
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta

logger = logging.getLogger("mohamy.knowledge")

class KnowledgeAgent:
    """
    Learns & indexes all laws, categories, subjects from the DB safely.
    Fully protected against missing columns or null values.
    """

    def __init__(self, db_path: str, cache_refresh_minutes: int = 60):
        self.db_path = db_path
        self.cache_refresh_minutes = cache_refresh_minutes
        self.last_refresh: Optional[datetime] = None

        self.law_tables: List[str] = []
        self.law_metadata: Dict[str, Dict[str, Any]] = {}
        self.all_categories: Dict[str, List[str]] = {}
        self.all_subjects: Set[str] = set()
        self.law_stats: Dict[str, int] = {}

        self.refresh_knowledge()
        logger.info("✅ Knowledge Agent initialized with dataset learning")

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def refresh_knowledge(self):
        logger.info("🧠 Knowledge Agent: Refreshing dataset knowledge...")

        try:
            with self.get_connection() as conn:
                self.law_tables = self._discover_law_tables(conn)

                for table_name in self.law_tables:
                    self._index_law_table(table_name, conn)

                self._build_category_index()

                self.last_refresh = datetime.now()

                logger.info(
                    f"✅ Knowledge refresh complete. "
                    f"Laws: {len(self.law_tables)}, "
                    f"Categories: {len(self.all_categories)}, "
                    f"Subjects: {len(self.all_subjects)}"
                )

        except Exception as e:
            logger.error(f"❌ Knowledge refresh failed: {e}")

    def _discover_law_tables(self, conn: sqlite3.Connection) -> List[str]:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'قانون%';"
        )
        rows = cur.fetchall()

        ignored_tables = {"قانون", "all_laws", "main_laws"}

        return [
            name for (name,) in rows
            if name not in ignored_tables
        ]

    def _index_law_table(self, table_name: str, conn: sqlite3.Connection):
        try:
            cur = conn.cursor()

            cur.execute(f'PRAGMA table_info("{table_name}");')
            columns = {row[1] for row in cur.fetchall()}

            cur.execute(f'SELECT * FROM "{table_name}" LIMIT 100;')
            rows = cur.fetchall()

            if not rows:
                logger.warning(f"⚠️ Table {table_name} is empty")
                return

            categories = set()

            for row in rows:
                row_dict = {k: row[k] for k in row.keys()}

                main_cat = row_dict.get("main_category")

                if main_cat not in (None, "", "null", "None"):
                    categories.add(str(main_cat))
                    self.all_subjects.add(str(main_cat))

                titel = row_dict.get("titel")
                if titel:
                    for word in titel.split():
                        if len(word) > 3:
                            self.all_subjects.add(word)

            cur.execute(f'SELECT COUNT(*) FROM "{table_name}";')
            total_count = cur.fetchone()[0]

            self.law_metadata[table_name] = {
                "name": table_name,
                "categories": list(categories),
                "article_count": total_count,
                "columns": list(columns),
            }

            self.law_stats[table_name] = total_count

            logger.info(
                f"📘 Indexed {table_name}: "
                f"Articles: {total_count}, "
                f"Categories: {len(categories)}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to index table {table_name}: {e}")

    def _build_category_index(self):
        self.all_categories = {}

        for law_name, metadata in self.law_metadata.items():
            for category in metadata.get("categories", []):

                if category in (None, "", "None", "null"):
                    continue

                if category not in self.all_categories:
                    self.all_categories[category] = []

                self.all_categories[category].append(law_name)

    def get_all_laws(self) -> List[Dict[str, Any]]:
        self._check_refresh()
        return [
            {
                "name": law_name,
                "article_count": metadata.get("article_count", 0),
                "categories": metadata.get("categories", []),
            }
            for law_name, metadata in self.law_metadata.items()
        ]

    def get_all_categories(self) -> Dict[str, Any]:
        self._check_refresh()

        categories = []
        for category_name, law_list in self.all_categories.items():
            categories.append({
                "name": category_name,
                "laws": law_list,
                "count": len(law_list)
            })

        categories.sort(key=lambda x: x["count"], reverse=True)

        return {
            "categories": categories,
            "total_categories": len(categories),
            "total_laws": len(self.law_tables)
        }

    def find_laws_by_category(self, category: str) -> List[str]:
        self._check_refresh()

        if category in self.all_categories:
            return self.all_categories[category]

        return [
            law
            for cat, laws in self.all_categories.items()
            if category in cat
            for law in laws
        ]

    def get_law_info(self, law_name: str) -> Optional[Dict[str, Any]]:
        self._check_refresh()

        if law_name in self.law_metadata:
            return self.law_metadata[law_name]

        for name, metadata in self.law_metadata.items():
            if law_name in name:
                return metadata

        return None

    def _check_refresh(self):
        if not self.last_refresh:
            self.refresh_knowledge()
            return

        if (datetime.now() - self.last_refresh) > timedelta(minutes=self.cache_refresh_minutes):
            logger.info("🔄 Knowledge cache expired → refreshing")
            self.refresh_knowledge()

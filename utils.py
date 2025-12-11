"""
Utility functions for the Mohamy Legal Assistant.
"""
import sqlite3
import re
from typing import List


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Create and return a database connection with Row factory.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        SQLite connection object
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_all_law_tables(db_path: str) -> List[str]:
    """
    List all law tables in the database.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        List of table names that represent laws
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    # Get all tables that start with 'قانون' (law in Arabic)
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name LIKE 'قانون%';"
    )
    rows = cur.fetchall()
    conn.close()
    
    # Filter out system tables
    ignored_tables = {"قانون", "all_laws", "main_laws", "combined_laws"}
    
    return [
        row[0] for row in rows
        if row[0] not in ignored_tables
    ]


def normalize_arabic_simple(text: str) -> str:
    """
    Normalize Arabic text for better matching.
    - Remove diacritics (tashkeel)
    - Normalize alef variants
    - Remove extra whitespace
    - Convert to lowercase where applicable
    
    Args:
        text: Arabic text to normalize
        
    Returns:
        Normalized text
    """
    if not text:
        return ""
    
    # Remove Arabic diacritics (tashkeel)
    text = re.sub(r'[\u064B-\u065F]', '', text)
    
    # Normalize Alef variants
    text = re.sub(r'[أإآ]', 'ا', text)
    
    # Normalize Ya
    text = re.sub(r'ى', 'ي', text)
    
    # Normalize Taa Marbuta
    text = re.sub(r'ة', 'ه', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text.lower()

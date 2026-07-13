"""
store.py — نظام الذاكرة الدائمة لـ WeaverCode (SQLite)
يحفظ: المحادثات، الحقائق، الأنماط، مخرجات الأدوات
"""

import sqlite3
import json
import time
import os
from pathlib import Path
from typing import List, Optional, Dict, Any


class MemoryStore:
    """
    ذاكرة SQLite دائمة للوكيل
    تحفظ السياق عبر الجلسات وتسمح بالبحث النصي
    """

    def __init__(self, db_path: Optional[str] = None):
        raw = db_path or os.environ.get(
            "WEAVER_DB_PATH",
            str(Path.home() / ".weaver" / "memory.db")
        )
        # توسيع ~ دائماً حتى يتطابق المسار بين الطرفية والـ daemon ولوحة الويب
        # (وإلا كتب أحدهم في مجلد اسمه "~" حرفياً فتختفي المحادثات المحفوظة)
        self.db_path = os.path.expanduser(raw)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    prompt TEXT,
                    response TEXT,
                    tools_used TEXT,
                    created_at REAL,
                    importance REAL DEFAULT 1.0
                );

                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE,
                    value TEXT,
                    tags TEXT,
                    created_at REAL,
                    updated_at REAL,
                    access_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_seen REAL,
                    context TEXT
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
                    USING fts5(prompt, response, content='conversations', content_rowid='id');

                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
                    USING fts5(key, value, content='facts', content_rowid='id');
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    async def save(
        self,
        prompt: str,
        response: str,
        tools_used: Optional[List[str]] = None,
        session_id: str = "",
        importance: float = 1.0,
    ):
        """حفظ محادثة في الذاكرة"""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO conversations
                   (session_id, prompt, response, tools_used, created_at, importance)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    prompt,
                    response,
                    json.dumps(tools_used or []),
                    time.time(),
                    importance,
                ),
            )

    async def get_relevant(self, query: str, limit: int = 3) -> str:
        """استرجاع الذكريات ذات الصلة بالاستعلام الحالي"""
        try:
            with self._conn() as conn:
                # بحث نصي في المحادثات
                rows = conn.execute(
                    """SELECT prompt, response FROM conversations
                       ORDER BY importance DESC, created_at DESC
                       LIMIT ?""",
                    (limit * 3,),
                ).fetchall()

                # تصفية بسيطة بالكلمات المفتاحية
                keywords = set(query.lower().split())
                scored = []
                for prompt, response in rows:
                    text = (prompt + " " + response).lower()
                    score = sum(1 for kw in keywords if kw in text)
                    if score > 0:
                        scored.append((score, prompt, response))

                scored.sort(reverse=True)
                results = scored[:limit]

                if not results:
                    return ""

                parts = []
                for _, p, r in results:
                    parts.append(f"س: {p[:100]}\nج: {r[:200]}")
                return "\n---\n".join(parts)
        except Exception:
            return ""

    def save_fact(self, key: str, value: str, tags: Optional[List[str]] = None):
        """حفظ حقيقة مفيدة"""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO facts (key, value, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       tags=excluded.tags,
                       updated_at=excluded.updated_at,
                       access_count=access_count+1""",
                (key, value, json.dumps(tags or []), now, now),
            )

    def get_fact(self, key: str) -> Optional[str]:
        """استرجاع حقيقة بمفتاحها"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM facts WHERE key=?", (key,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE facts SET access_count=access_count+1 WHERE key=?", (key,)
                )
                return row[0]
        return None

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """البحث في الحقائق المحفوظة"""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT key, value, tags FROM facts
                   WHERE key LIKE ? OR value LIKE ?
                   ORDER BY access_count DESC, updated_at DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [{"key": r[0], "value": r[1], "tags": json.loads(r[2] or "[]")} for r in rows]

    def get_stats(self) -> Dict[str, int]:
        """إحصاءات الذاكرة"""
        with self._conn() as conn:
            convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        return {"conversations": convs, "facts": facts}

    def clear_old(self, days: int = 30):
        """حذف الذكريات القديمة (أقل أهمية)"""
        cutoff = time.time() - (days * 86400)
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE created_at < ? AND importance < 0.5",
                (cutoff,),
            )

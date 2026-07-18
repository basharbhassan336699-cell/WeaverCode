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

            # Triggers لمزامنة FTS5 مع الجداول الأساسية عند الإدراج
            try:
                conn.executescript("""
                    CREATE TRIGGER IF NOT EXISTS conversations_ai
                        AFTER INSERT ON conversations BEGIN
                        INSERT INTO conversations_fts(rowid, prompt, response)
                        VALUES (new.id, new.prompt, new.response);
                    END;

                    CREATE TRIGGER IF NOT EXISTS facts_ai
                        AFTER INSERT ON facts BEGIN
                        INSERT INTO facts_fts(rowid, key, value)
                        VALUES (new.id, new.key, new.value);
                    END;
                """)
                # فهرسة الصفوف الموجودة مسبقاً (قبل إضافة الـ triggers) مرةً واحدة
                conn.execute("INSERT INTO conversations_fts(conversations_fts) VALUES('rebuild')")
                conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
            except sqlite3.OperationalError:
                # FTS5 غير متاح في هذا البناء من SQLite → نعتمد بحث LIKE الاحتياطي
                pass

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
        """استرجاع الذكريات ذات الصلة بالاستعلام باستخدام FTS5 الحقيقي.

        يجرّب FTS5 MATCH أولاً؛ وإن لم يُرجِع نتائج (أو تعذّر) يسقط إلى بحث
        LIKE عادي حتى تبقى الذاكرة القديمة قابلة للاسترجاع.
        """
        if not query.strip():
            return ""
        rows = []
        try:
            with self._conn() as conn:
                # (1) محاولة FTS5 الحقيقي
                try:
                    fts_query = " OR ".join(
                        f'"{w}"' for w in query.split() if len(w) > 1
                    )
                    if fts_query:
                        rows = conn.execute(
                            """SELECT c.prompt, c.response
                               FROM conversations_fts f
                               JOIN conversations c ON c.id = f.rowid
                               WHERE conversations_fts MATCH ?
                               ORDER BY c.importance DESC, c.created_at DESC
                               LIMIT ?""",
                            (fts_query, limit),
                        ).fetchall()
                except Exception:
                    rows = []

                # (2) احتياطي: بحث LIKE عادي إن لم تُرجِع FTS نتائج
                if not rows:
                    rows = conn.execute(
                        """SELECT prompt, response FROM conversations
                           WHERE prompt LIKE ? OR response LIKE ?
                           ORDER BY importance DESC, created_at DESC
                           LIMIT ?""",
                        (f"%{query}%", f"%{query}%", limit),
                    ).fetchall()

                if not rows:
                    return ""
                parts = [f"س: {p[:150]}\nج: {r[:300]}" for p, r in rows]
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

    # ── إدارة الجلسات (Sessions) — حفظ واستئناف المحادثات ─────────────────────

    def _ensure_sessions_table(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT,
                last_prompt TEXT,
                messages_json TEXT,
                created_at REAL,
                updated_at REAL
            )""")

    def save_session(self, session_id: str, name: str, last_prompt: str,
                     messages_json: str) -> None:
        """حفظ جلسة كاملة للاستئناف لاحقاً."""
        with self._conn() as conn:
            self._ensure_sessions_table(conn)
            conn.execute("""
                INSERT INTO sessions (id, name, last_prompt, messages_json,
                                      created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    last_prompt=excluded.last_prompt,
                    messages_json=excluded.messages_json,
                    updated_at=excluded.updated_at
            """, (session_id, name, last_prompt, messages_json,
                  time.time(), time.time()))

    def list_sessions(self, limit: int = 20) -> list:
        """عرض الجلسات المحفوظة مرتبة بالأحدث."""
        with self._conn() as conn:
            self._ensure_sessions_table(conn)
            try:
                rows = conn.execute("""
                    SELECT id, name, last_prompt, updated_at
                    FROM sessions ORDER BY updated_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [{"id": r[0], "name": r[1],
                         "last_prompt": r[2], "updated_at": r[3]}
                        for r in rows]
            except Exception:
                return []

    def load_session(self, session_ref: str) -> Optional[dict]:
        """تحميل جلسة بالـ ID أو الاسم."""
        with self._conn() as conn:
            self._ensure_sessions_table(conn)
            try:
                row = conn.execute(
                    "SELECT id, name, messages_json FROM sessions "
                    "WHERE id=? OR name=?",
                    (session_ref, session_ref)
                ).fetchone()
                if row:
                    return {"id": row[0], "name": row[1],
                            "messages": json.loads(row[2] or "[]")}
            except Exception:
                pass
        return None

    def delete_session(self, session_id: str) -> bool:
        """حذف جلسة بالـ ID."""
        with self._conn() as conn:
            self._ensure_sessions_table(conn)
            try:
                conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                return True
            except Exception:
                return False

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """إعادة تسمية جلسة."""
        with self._conn() as conn:
            self._ensure_sessions_table(conn)
            try:
                conn.execute(
                    "UPDATE sessions SET name=? WHERE id=?",
                    (new_name, session_id))
                return True
            except Exception:
                return False

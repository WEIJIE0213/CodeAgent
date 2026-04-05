"""
long_term.py —— SQLite 长期记忆持久化

表结构：
  sessions  : 会话元数据 (thread_id PK, created_at, updated_at)
  messages  : 每轮消息记录 (id, thread_id, role, content, created_at)
  summaries : 压缩摘要历史 (id, thread_id, summary, created_at)
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional

from codeagent.config import settings


def _db_path() -> str:
    raw = settings.DB_URL.replace("sqlite:///", "")
    # 处理相对路径（./xxx）
    if raw.startswith("./"):
        raw = raw[2:]
    return raw


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化所有表（幂等，多次调用安全）"""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            thread_id  TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_thread
            ON messages(thread_id);

        CREATE TABLE IF NOT EXISTS summaries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  TEXT NOT NULL,
            summary    TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_summaries_thread
            ON summaries(thread_id);
    """)
    conn.commit()
    conn.close()


def upsert_session(thread_id: str) -> None:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO sessions (thread_id, created_at, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at
    """, (thread_id, now, now))
    conn.commit()
    conn.close()


def save_messages(thread_id: str, user_content: str, assistant_content: str) -> None:
    """保存一轮对话（用户 + 助手）"""
    conn = _connect()
    now = datetime.utcnow().isoformat()
    conn.executemany(
        "INSERT INTO messages (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        [
            (thread_id, "user", user_content, now),
            (thread_id, "assistant", assistant_content, now),
        ]
    )
    conn.commit()
    conn.close()


def get_latest_summary(thread_id: str) -> Optional[str]:
    """获取该会话最新的摘要"""
    conn = _connect()
    row = conn.execute(
        "SELECT summary FROM summaries WHERE thread_id = ? ORDER BY id DESC LIMIT 1",
        (thread_id,)
    ).fetchone()
    conn.close()
    return row["summary"] if row else None


def save_summary(thread_id: str, summary: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO summaries (thread_id, summary, created_at) VALUES (?, ?, ?)",
        (thread_id, summary, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_recent_messages(thread_id: str, limit: int = 20) -> list[dict]:
    """加载最近 N 条消息（用于恢复 short_term）"""
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
        (thread_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

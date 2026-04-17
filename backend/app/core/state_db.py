"""
Hermes State DB 访问模块
只读访问 Hermes SQLite 数据库
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class StateDBError(Exception):
    """State DB 访问错误"""
    pass


class StateDB:
    """Hermes SQLite 数据库只读访问"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.hermes_state_db_full_path

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取只读数据库连接"""
        conn = None
        try:
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                timeout=5.0
            )
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to state db: {e}")
            raise StateDBError(f"Database connection failed: {e}")
        finally:
            if conn:
                conn.close()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话详情"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
        source: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取会话列表"""
        with self._get_connection() as conn:
            query = "SELECT * FROM sessions WHERE 1=1"
            params = []

            if source:
                query += " AND source = ?"
                params.append(source)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_session_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取会话消息"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_session_count(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """获取会话总数"""
        with self._get_connection() as conn:
            query = "SELECT COUNT(*) FROM sessions WHERE 1=1"
            params = []

            if source:
                query += " AND source = ?"
                params.append(source)

            if status:
                query += " AND status = ?"
                params.append(status)

            cursor = conn.execute(query, params)
            return cursor.fetchone()[0]

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计"""
        with self._get_connection() as conn:
            stats = {}

            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            stats["total_sessions"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            stats["total_messages"] = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT source, COUNT(*) as count FROM sessions GROUP BY source"
            )
            stats["by_source"] = {row[0]: row[1] for row in cursor.fetchall()}

            cursor = conn.execute(
                "SELECT status, COUNT(*) as count FROM sessions GROUP BY status"
            )
            stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

            today = datetime.now().strftime("%Y-%m-%d")
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE DATE(created_at) = ?",
                (today,)
            )
            stats["today_sessions"] = cursor.fetchone()[0]

            return stats


# 全局实例
_state_db: Optional[StateDB] = None


def get_state_db() -> StateDB:
    """获取 StateDB 实例"""
    global _state_db
    if _state_db is None:
        _state_db = StateDB()
    return _state_db

"""Durable SQLite Session Memory and Trajectory Store."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SessionMemoryManager:
    """Manages persistent session checkpoints and agent trajectory logs in SQLite."""

    def __init__(self, db_path: str | Path = "reports/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    query TEXT NOT NULL,
                    final_answer TEXT,
                    verified INTEGER,
                    strategy TEXT,
                    cost_usd REAL,
                    latency_ms REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trajectories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_memory (
                    entity_key TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_session(
        self,
        session_id: str,
        query: str,
        final_answer: str | None,
        verified: bool,
        strategy: str,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, created_at, query, final_answer, verified, strategy, cost_usd, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    query,
                    final_answer,
                    1 if verified else 0,
                    strategy,
                    cost_usd,
                    latency_ms,
                ),
            )
            conn.commit()

    def log_step(
        self,
        session_id: str,
        step_index: int,
        agent_name: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO trajectories (session_id, step_index, agent_name, action, payload, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    step_index,
                    agent_name,
                    action,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                ),
            )
            conn.commit()

    def get_trajectory(self, session_id: str) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT step_index, agent_name, action, payload, timestamp
                FROM trajectories
                WHERE session_id = ?
                ORDER BY step_index ASC
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "step_index": r[0],
                    "agent_name": r[1],
                    "action": r[2],
                    "payload": json.loads(r[3]),
                    "timestamp": r[4],
                }
                for r in rows
            ]

    def get_recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT session_id, created_at, query, final_answer, verified, strategy, cost_usd, latency_ms
                FROM sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "session_id": r[0],
                    "created_at": r[1],
                    "query": r[2],
                    "final_answer": r[3],
                    "verified": bool(r[4]),
                    "strategy": r[5],
                    "cost_usd": float(r[6] or 0.0),
                    "latency_ms": float(r[7] or 0.0),
                }
                for r in rows
            ]

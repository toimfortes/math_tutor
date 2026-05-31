"""Append-only attempt log.

An immutable, queryable record of every graded submission, separate from the
mutable session aggregate. Useful for analytics and debugging. SQLite-backed
via stdlib sqlite3; rows are only ever inserted, never updated.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Callable


class SqliteAttemptLog:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS attempt_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, session_id TEXT NOT NULL, "
            "student_id TEXT NOT NULL, skill_id TEXT NOT NULL, problem_id TEXT NOT NULL, "
            "check_result TEXT, xp_awarded INTEGER NOT NULL)"
        )
        self._conn.commit()

    def record(
        self,
        *,
        session_id: str,
        student_id: str,
        skill_id: str,
        problem_id: str,
        check_result: str | None,
        xp_awarded: int,
    ) -> None:
        self._conn.execute(
            "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self._clock(), session_id, student_id, skill_id, problem_id, check_result, xp_awarded),
        )
        self._conn.commit()

    def entries(self, session_id: str) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded "
            "FROM attempt_log WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

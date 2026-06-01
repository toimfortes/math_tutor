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

    def mastery_by_skill(self, student_id: str) -> list[tuple[str, float, int]]:
        """Per-skill mastery signals for a student, CROSS-SESSION: (skill_id, latest
        correct ts, distinct correct problem count).

        Keyed by `student_id` (not session_id), so mastery demonstrated anywhere — the
        assessment loop or the practice pool — counts, matching the offline `review_queue`.
        `COUNT(DISTINCT problem_id)` is the mastery measure (replaying one problem cannot
        qualify a skill); `MAX(ts)` is the time-defined recency `review_due` expects.
        `ts`/`problem_id` are NOT NULL, so these agree with `review_due`'s set-based count.
        Bounded output: one row per skill, ordered for determinism. Read-only.
        """
        cursor = self._conn.execute(
            "SELECT skill_id, MAX(ts), COUNT(DISTINCT problem_id) FROM attempt_log "
            "WHERE student_id = ? AND check_result = 'correct' GROUP BY skill_id ORDER BY skill_id",
            (student_id,),
        )
        return [(skill_id, ts, count) for skill_id, ts, count in cursor.fetchall()]

    def recent_decidable_by_problem(self, session_id: str, *, limit: int) -> list[dict]:
        """Latest decidable attempt per problem — the most recent `limit` DISTINCT
        problems, in chronological (ascending id) order.

        Deduplication happens in SQL via `MAX(id) ... GROUP BY problem_id` BEFORE the
        limit, so the cap counts distinct problems: re-attempting one problem cannot
        flush other problems out of the window (and the latest decidable result wins,
        landing in that problem's latest chronological slot). Read-only.
        """
        cursor = self._conn.execute(
            "SELECT skill_id, problem_id, check_result FROM attempt_log WHERE id IN ("
            "  SELECT MAX(id) FROM attempt_log "
            "  WHERE session_id = ? AND check_result IN ('correct', 'incorrect') "
            "  GROUP BY problem_id"
            ") ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        columns = [description[0] for description in cursor.description]
        rows = list(reversed(cursor.fetchall()))
        return [dict(zip(columns, row)) for row in rows]

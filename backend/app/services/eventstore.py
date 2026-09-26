"""SQLite persistence for incidents, response actions and system events.

Keeps the incident timeline auditable across restarts while staying a single
file that ships with the repo (gridshield.db is recreated on first run).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    step_index INTEGER,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    extra TEXT
);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT UNIQUE NOT NULL,
    attack_type TEXT NOT NULL,
    device_id TEXT NOT NULL,
    detected_step INTEGER,
    resolved_step INTEGER,
    confidence REAL,
    status TEXT NOT NULL,
    actions TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


class EventStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ #
    def record_event(self, ev: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, step_index, kind, severity, message, extra) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ev.get("ts", time.time()),
                    ev.get("step_index"),
                    ev.get("kind", "SYSTEM"),
                    ev.get("severity", "info"),
                    ev.get("message", ""),
                    json.dumps(ev.get("extra", {})),
                ),
            )
            self._conn.commit()

    def record_incident(self, inc_dict: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO incidents "
                "(incident_id, attack_type, device_id, detected_step, resolved_step, "
                " confidence, status, actions, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    inc_dict.get("incident_id"),
                    inc_dict.get("attack_type"),
                    inc_dict.get("device_id"),
                    inc_dict.get("detected_step"),
                    inc_dict.get("resolved_step"),
                    inc_dict.get("confidence"),
                    inc_dict.get("status"),
                    json.dumps(inc_dict.get("actions", [])),
                    time.time(),
                ),
            )
            self._conn.commit()

    def recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, step_index, kind, severity, message, extra FROM events "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for ts, step, kind, sev, msg, extra in rows:
            e = {"ts": ts, "step_index": step, "kind": kind, "severity": sev, "message": msg}
            try:
                e["extra"] = json.loads(extra or "{}")
            except json.JSONDecodeError:
                e["extra"] = {}
            out.append(e)
        return out

    def incident_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT incident_id, attack_type, device_id, detected_step, resolved_step, "
                "confidence, status, actions, created_at FROM incidents "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for (iid, atk, dev, dst, rst, conf, status, actions, created) in rows:
            try:
                acts = json.loads(actions or "[]")
            except json.JSONDecodeError:
                acts = []
            out.append({
                "incident_id": iid, "attack_type": atk, "device_id": dev,
                "detected_step": dst, "resolved_step": rst, "confidence": conf,
                "status": status, "actions": acts, "created_at": created,
            })
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# Singleton store shared by the API layer.
event_store = EventStore()

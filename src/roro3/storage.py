"""Persistance SQLite : état global et prise atomique d'une tentative."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path
from uuid import uuid4

from roro3.models import (
    AttemptStatus,
    Merchant,
    Offer,
    ReservationResult,
    RunPolicy,
    ScheduleWindow,
    timestamp,
    utc,
    validate_manual_windows,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime (
    id INTEGER PRIMARY KEY CHECK(id=1),
    observe INTEGER NOT NULL, notify INTEGER NOT NULL,
    reserve INTEGER NOT NULL, dry_run INTEGER NOT NULL, stopped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS merchants (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, windows TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    watched INTEGER NOT NULL DEFAULT 1 CHECK(watched IN (0,1))
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    offer_id TEXT NOT NULL, merchant_id TEXT NOT NULL,
    pickup_start TEXT NOT NULL, observed_at TEXT NOT NULL,
    available INTEGER NOT NULL CHECK(available>=0), event TEXT NOT NULL,
    UNIQUE(offer_id,pickup_start,observed_at)
);
CREATE INDEX IF NOT EXISTS observation_history
    ON observations(offer_id,pickup_start,observed_at);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, account TEXT NOT NULL,
    offer_id TEXT NOT NULL, pickup_start TEXT NOT NULL, kind TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    reference TEXT,
    UNIQUE(account,offer_id,pickup_start,kind)
);
"""


def _encode_windows(windows: tuple[ScheduleWindow, ...]) -> str:
    return json.dumps(
        [
            {
                "weekday": window.weekday,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "source": window.source,
                "sample_count": window.sample_count,
            }
            for window in windows
        ],
        ensure_ascii=False,
    )


def _merchant(row: sqlite3.Row) -> Merchant:
    return Merchant(
        row["id"],
        row["name"],
        tuple(
            ScheduleWindow(
                weekday=w["weekday"],
                start=time.fromisoformat(w["start"]),
                end=time.fromisoformat(w["end"]),
                source=w["source"],
                sample_count=w["sample_count"],
            )
            for w in json.loads(row["windows"])
        ),
        active=bool(row["active"]),
        watched=bool(row["watched"]),
    )


def _require_merchant(db: sqlite3.Connection, identifier: str) -> Merchant:
    row = db.execute("SELECT * FROM merchants WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise ValueError("Ce commerçant n'existe plus. Actualisez la liste.")
    return _merchant(row)


class Repository:
    def __init__(self, path: Path, initial_policy: RunPolicy | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        initial = initial_policy or RunPolicy()
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Version de base non prise en charge")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError("Version de base non prise en charge")
            # Schéma statique sans triggers ; éviter le commit implicite d'executescript.
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    db.execute(statement)
            if version == 1:
                db.execute(
                    "ALTER TABLE merchants ADD COLUMN active INTEGER NOT NULL "
                    "DEFAULT 1 CHECK(active IN (0,1))"
                )
                db.execute(
                    "ALTER TABLE merchants ADD COLUMN watched INTEGER NOT NULL "
                    "DEFAULT 1 CHECK(watched IN (0,1))"
                )
            db.execute(
                "INSERT OR IGNORE INTO runtime VALUES(1,?,?,?,?,0)",
                (initial.observe, initial.notify, initial.reserve, initial.dry_run),
            )
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get_policy(self) -> RunPolicy:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runtime WHERE id=1").fetchone()
        return RunPolicy(*(bool(row[key]) for key in ("observe", "notify", "reserve", "dry_run")))

    def set_policy(self, policy: RunPolicy) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE runtime SET observe=?,notify=?,reserve=?,dry_run=? WHERE id=1",
                (policy.observe, policy.notify, policy.reserve, policy.dry_run),
            )

    def is_stopped(self) -> bool:
        with self.connection() as db:
            return bool(db.execute("SELECT stopped FROM runtime WHERE id=1").fetchone()[0])

    def set_stopped(self, stopped: bool) -> None:
        with self.connection() as db:
            db.execute("UPDATE runtime SET stopped=? WHERE id=1", (bool(stopped),))

    def upsert_merchant(self, merchant: Merchant) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO merchants(id,name,windows,active,watched) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,windows=excluded.windows,"
                "active=excluded.active,watched=excluded.watched",
                (
                    merchant.id,
                    merchant.name,
                    _encode_windows(merchant.windows),
                    merchant.active,
                    merchant.watched,
                ),
            )

    def list_merchants(self) -> list[Merchant]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM merchants ORDER BY name").fetchall()
        return [_merchant(row) for row in rows]

    def get_merchant(self, identifier: str) -> Merchant | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM merchants WHERE id=?", (identifier,)).fetchone()
        return _merchant(row) if row is not None else None

    def update_merchant_details(
        self, identifier: str, name: str, manual_windows: tuple[ScheduleWindow, ...]
    ) -> Merchant:
        validate_manual_windows(manual_windows)
        Merchant(identifier, name, manual_windows)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = _require_merchant(db, identifier)
            estimated = tuple(w for w in current.windows if w.source == "estimated")
            updated = replace(current, name=name.strip(), windows=manual_windows + estimated)
            db.execute(
                "UPDATE merchants SET name=?,windows=? WHERE id=?",
                (updated.name, _encode_windows(updated.windows), identifier),
            )
        return updated

    def _set_merchant_flag(self, identifier: str, field: str, value: bool) -> Merchant:
        if field not in {"active", "watched"} or type(value) is not bool:
            raise ValueError("État de commerçant invalide")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = _require_merchant(db, identifier)
            db.execute(f"UPDATE merchants SET {field}=? WHERE id=?", (value, identifier))
            return replace(current, **{field: value})

    def set_merchant_active(self, identifier: str, active: bool) -> Merchant:
        return self._set_merchant_flag(identifier, "active", active)

    def set_merchant_watched(self, identifier: str, watched: bool) -> Merchant:
        return self._set_merchant_flag(identifier, "watched", watched)

    def replace_estimates(self, identifier: str, windows: tuple[ScheduleWindow, ...]) -> Merchant:
        if any(w.source != "estimated" for w in windows):
            raise ValueError("Seuls des créneaux estimés peuvent remplacer les estimations")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = _require_merchant(db, identifier)
            manual = tuple(w for w in current.windows if w.source == "manual")
            updated = replace(current, windows=manual + windows)
            db.execute(
                "UPDATE merchants SET windows=? WHERE id=?",
                (_encode_windows(updated.windows), identifier),
            )
            return updated

    def record_observation(self, offer: Offer, now: datetime) -> str:
        observed_at, pickup = timestamp(now), timestamp(offer.pickup_start)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT available FROM observations WHERE offer_id=? AND pickup_start=? "
                "ORDER BY observed_at DESC,id DESC LIMIT 1",
                (offer.id, pickup),
            ).fetchone()
            if not offer.available:
                event = "unavailable"
            elif previous is None:
                event = "first_seen_available"
            elif previous[0] == 0:
                event = "became_available"
            else:
                event = "still_available"
            cursor = db.execute(
                "INSERT INTO observations(offer_id,merchant_id,pickup_start,observed_at,"
                "available,event) VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (offer.id, offer.merchant_id, pickup, observed_at, offer.available, event),
            )
            return event if cursor.rowcount else "duplicate"

    def list_observations(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM observations ORDER BY id DESC")]

    def claim_attempt(self, offer: Offer, account: str, now: datetime) -> ReservationResult:
        """Le claim est le point d'admission de l'action ; il survit à un arrêt brutal."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute("SELECT * FROM runtime WHERE id=1").fetchone()
            if state["stopped"]:
                return ReservationResult("stopped")
            if not state["reserve"]:
                return ReservationResult("disabled")
            merchant = db.execute(
                "SELECT active,watched FROM merchants WHERE id=?", (offer.merchant_id,)
            ).fetchone()
            if merchant is None:
                return ReservationResult("unknown_merchant")
            if not merchant["active"]:
                return ReservationResult("merchant_disabled")
            if not merchant["watched"]:
                return ReservationResult("not_watched")
            if offer.available == 0 or utc(now) >= utc(offer.pickup_end):
                return ReservationResult("unavailable")
            preview = bool(state["dry_run"])
            kind = "preview" if preview else "simulation"
            status = AttemptStatus.PREVIEW if preview else AttemptStatus.PENDING
            identifier, created = str(uuid4()), timestamp(now)
            cursor = db.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    identifier,
                    account,
                    offer.id,
                    timestamp(offer.pickup_start),
                    kind,
                    status.value,
                    created,
                    created,
                    None,
                ),
            )
            if not cursor.rowcount:
                return ReservationResult("duplicate")
            return ReservationResult("preview" if preview else "claimed", identifier)

    def finish_attempt(
        self, identifier: str, status: AttemptStatus, now: datetime, reference: str | None = None
    ) -> None:
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE attempts SET status=?,updated_at=?,reference=? WHERE id=? AND status=?",
                (status.value, timestamp(now), reference, identifier, AttemptStatus.PENDING.value),
            )
            if cursor.rowcount != 1:
                raise ValueError("Transition de tentative invalide")

    def list_attempts(self) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row) for row in db.execute("SELECT * FROM attempts ORDER BY created_at DESC")
            ]

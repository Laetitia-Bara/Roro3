"""Modèles métier, sans dépendance d'interface ou d'accès réseau."""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import StrEnum


def utc(value: datetime) -> datetime:
    """Refuser les dates ambiguës sans fuseau et normaliser les instants."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Une date avec fuseau horaire est obligatoire")
    return value.astimezone(UTC)


def timestamp(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class RunPolicy:
    observe: bool = True
    notify: bool = False
    reserve: bool = False
    dry_run: bool = True


@dataclass(frozen=True)
class ScheduleWindow:
    weekday: int
    start: time
    end: time
    source: str = "manual"
    sample_count: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6 or self.start >= self.end:
            raise ValueError("Créneau diurne avec jour entre 0 et 6 requis")
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Les heures de créneau sont locales, sans décalage fixe")
        if self.source not in {"manual", "estimated"} or self.sample_count < 0:
            raise ValueError("Origine de créneau invalide")


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    windows: tuple[ScheduleWindow, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("Identifiant et nom de commerçant obligatoires")


@dataclass(frozen=True)
class Offer:
    id: str
    merchant_id: str
    pickup_start: datetime
    pickup_end: datetime
    available: int
    price_minor: int = 0
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if utc(self.pickup_end) <= utc(self.pickup_start):
            raise ValueError("La fin du retrait doit suivre son début")
        if self.available < 0 or self.price_minor < 0:
            raise ValueError("Quantité et prix doivent être positifs ou nuls")
        if not self.id or not self.merchant_id:
            raise ValueError("Identifiants du panier et du commerçant obligatoires")


class AttemptStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    PREVIEW = "preview"


@dataclass(frozen=True)
class ReservationResult:
    outcome: str
    attempt_id: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class CycleResult:
    observations: int = 0
    notifications: int = 0
    reservations: tuple[ReservationResult, ...] = ()
    stopped: bool = False

"""Modèles métier, sans dépendance d'interface ou d'accès réseau."""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import StrEnum
from itertools import pairwise


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
        if type(self.weekday) is not int or not 0 <= self.weekday <= 6:
            raise ValueError("Le jour doit être un entier entre 0 et 6")
        if not isinstance(self.start, time) or not isinstance(self.end, time):
            raise ValueError("Les heures de début et de fin sont obligatoires")
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Les heures de créneau sont locales, sans décalage fixe")
        if self.start >= self.end:
            raise ValueError("La fin doit suivre le début, sans traverser minuit")
        if (
            self.source not in {"manual", "estimated"}
            or type(self.sample_count) is not int
            or self.sample_count < 0
        ):
            raise ValueError("Origine de créneau invalide")


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    windows: tuple[ScheduleWindow, ...] = ()
    active: bool = True
    watched: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Identifiant de commerçant obligatoire")
        if not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 100:
            raise ValueError("Le nom du commerçant doit contenir entre 1 et 100 caractères")
        if type(self.active) is not bool or type(self.watched) is not bool:
            raise ValueError("Les états actif et suivi doivent être des booléens")
        if not all(isinstance(window, ScheduleWindow) for window in self.windows):
            raise ValueError("Les créneaux du commerçant sont invalides")


def validate_manual_windows(windows: tuple[ScheduleWindow, ...]) -> None:
    """Valider avant écriture ; les estimations ne sont jamais saisies à la main."""
    if any(
        not isinstance(window, ScheduleWindow) or window.source != "manual" for window in windows
    ):
        raise ValueError("Seuls des créneaux manuels peuvent être saisis")
    ordered = sorted(windows, key=lambda window: (window.weekday, window.start, window.end))
    for previous, current in pairwise(ordered):
        if previous.weekday == current.weekday and current.start < previous.end:
            raise ValueError("Deux créneaux manuels du même jour ne doivent pas se chevaucher")


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


def validate_interval_seconds(value: int) -> None:
    if type(value) is not int or not 15 <= value <= 3600:
        raise ValueError("La fréquence doit être un entier entre 15 et 3600 secondes")


@dataclass(frozen=True)
class SchedulerStatus:
    running: bool
    owned: bool
    state: str
    interval_seconds: int
    next_check: datetime | None = None
    last_check: datetime | None = None
    last_error: str | None = None

"""Consultation de l'historique, sans modifier le suivi ou les estimations.

Le dépôt fournit les relevés par un SELECT unique : chaque requête travaille sur
ce même instantané. Le filtrage, le tri et la pagination sont faits en mémoire ;
ce choix convient à la démonstration locale, pas à un historique de grande taille.
Les jours observés ne mesurent pas une couverture continue de surveillance.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from roro3.models import utc
from roro3.storage import Repository

OBSERVATION_EVENTS = (
    "unavailable",
    "first_seen_available",
    "became_available",
    "still_available",
)


@dataclass(frozen=True)
class HistoryFilters:
    merchant_id: str | None = None
    event: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.merchant_id is not None and (
            not isinstance(self.merchant_id, str) or not self.merchant_id.strip()
        ):
            raise ValueError("Identifiant de commerçant invalide")
        if self.event is not None and self.event not in OBSERVATION_EVENTS:
            raise ValueError("Type de relevé invalide")
        for value in (self.start_date, self.end_date):
            if value is not None and type(value) is not date:
                raise ValueError("Une date de calendrier est obligatoire")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("La date de début doit précéder ou égaler la date de fin")


@dataclass(frozen=True)
class HistorySummary:
    observation_count: int
    observed_days: int
    transition_count: int
    first_seen_count: int
    first_observed_at: str | None
    last_observed_at: str | None


@dataclass(frozen=True)
class ObservedPattern:
    weekday: int
    start: time
    end: time
    distinct_days: int
    eligible: bool


@dataclass(frozen=True)
class HistoryPage:
    rows: tuple[Mapping[str, str | int], ...]
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: HistorySummary
    patterns: tuple[ObservedPattern, ...]


_ALL_HISTORY = HistoryFilters()


class HistoryService:
    def __init__(self, repo: Repository, timezone: str = "Europe/Paris") -> None:
        self.repo = repo
        if not isinstance(timezone, str) or not timezone:
            raise ValueError("Fuseau horaire invalide")
        try:
            self.zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Fuseau horaire invalide") from error

    def query(
        self,
        filters: HistoryFilters = _ALL_HISTORY,
        page: int = 1,
        page_size: int = 20,
    ) -> HistoryPage:
        """Filtrer sur des dates locales inclusives et compter avant pagination.

        Les premières présences ne datent pas une apparition : seuls les événements
        ``became_available`` participent aux quarts d'heure descriptifs. Leur seuil
        de trois jours et la limite de minuit suivent le calcul d'estimation existant.
        Ces motifs sont propres à la sélection et ne changent aucun horaire enregistré.
        """
        if not isinstance(filters, HistoryFilters):
            raise ValueError("Filtres d'historique invalides")
        if type(page) is not int or page < 1:
            raise ValueError("Le numéro de page doit être un entier positif")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("La taille de page doit être un entier entre 1 et 100")

        records = []
        # Ne pas relire le dépôt entre les comptes, les motifs et les lignes affichées.
        for row in self.repo.list_observations():
            if filters.merchant_id is not None and row["merchant_id"] != filters.merchant_id:
                continue
            if filters.event is not None and row["event"] != filters.event:
                continue
            instant = utc(datetime.fromisoformat(row["observed_at"]))
            local = instant.astimezone(self.zone)
            if filters.start_date and local.date() < filters.start_date:
                continue
            if filters.end_date and local.date() > filters.end_date:
                continue
            records.append((instant, local, row))
        records.sort(key=lambda item: (item[0], item[2]["id"]), reverse=True)

        total = len(records)
        summary = HistorySummary(
            observation_count=total,
            observed_days=len({local.date() for _, local, _ in records}),
            transition_count=sum(row["event"] == "became_available" for _, _, row in records),
            first_seen_count=sum(row["event"] == "first_seen_available" for _, _, row in records),
            first_observed_at=records[-1][2]["observed_at"] if records else None,
            last_observed_at=records[0][2]["observed_at"] if records else None,
        )
        buckets: dict[tuple[int, int], set[date]] = defaultdict(set)
        if filters.merchant_id is not None:
            for _, local, row in records:
                if row["event"] != "became_available":
                    continue
                minute = (local.hour * 60 + local.minute) // 15 * 15
                if minute + 15 >= 24 * 60:
                    continue
                buckets[(local.weekday(), minute)].add(local.date())
        patterns = tuple(
            ObservedPattern(
                weekday=weekday,
                start=time(minute // 60, minute % 60),
                end=time((minute + 15) // 60, (minute + 15) % 60),
                distinct_days=len(days),
                eligible=len(days) >= 3,
            )
            for (weekday, minute), days in sorted(buckets.items())
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        offset = (current_page - 1) * page_size
        return HistoryPage(
            rows=tuple(
                MappingProxyType(dict(row)) for _, _, row in records[offset : offset + page_size]
            ),
            total=total,
            page=current_page,
            page_size=page_size,
            total_pages=total_pages,
            summary=summary,
            patterns=patterns,
        )

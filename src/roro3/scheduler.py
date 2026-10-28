"""Planification simulée, admission persistante et démarrage explicitement demandé."""

import logging
from datetime import datetime, timedelta
from threading import Lock
from uuid import uuid4

from roro3.models import CycleResult, SchedulerStatus, utc
from roro3.observations import MonitorService
from roro3.planning import next_window
from roro3.storage import Repository

logger = logging.getLogger(__name__)
LEASE_SECONDS = 15
_ERROR = "Le contrôle simulé a échoué. Un nouvel essai est prévu au prochain passage."


class SchedulerService:
    def __init__(
        self,
        repository: Repository,
        monitor: MonitorService,
        timezone: str = "Europe/Paris",
    ) -> None:
        self.repository = repository
        self.monitor = monitor
        self.timezone = timezone
        self._owner = ""
        self._started = False
        self._tick_lock = Lock()

    def start(self, now: datetime) -> None:
        current = utc(now)
        if self._started and self.repository.scheduler_is_owner(self._owner, current):
            return
        owner = str(uuid4())
        self.repository.start_scheduler_session(
            owner, current, current + timedelta(seconds=LEASE_SECONDS)
        )
        self._owner, self._started = owner, True

    def stop(self) -> None:
        self.repository.stop_scheduler_session()
        self._started = False

    def close(self) -> None:
        if self._owner:
            self.repository.stop_scheduler_session(self._owner)
        self._started = False

    def set_interval_seconds(self, interval_seconds: int) -> None:
        self.repository.set_scheduler_interval(interval_seconds)

    def tick(self, now: datetime) -> CycleResult | None:
        current = utc(now)
        if not self._started or not self._tick_lock.acquire(blocking=False):
            return None
        owner = self._owner
        try:
            due = self.repository.admit_scheduled_checks(
                owner, current, current + timedelta(seconds=LEASE_SECONDS), self.timezone
            )
            if due is None:
                self._started = False
                return None
            if not due:
                return None
            try:
                result = self.monitor.run_once(
                    current,
                    merchant_ids=due,
                    observation_only=True,
                    guard=lambda: self.repository.scheduler_is_owner(owner, current),
                )
            except Exception:
                # Ne jamais stocker/afficher le contenu brut d'une exception externe.
                self.repository.finish_scheduled_checks(owner, due, current, _ERROR)
                logger.warning("Échec d'un contrôle planifié simulé ; reprise à la cadence prévue")
                return None
            self.repository.finish_scheduled_checks(owner, due, current, None)
            return result
        finally:
            self._tick_lock.release()

    def status(self, now: datetime) -> SchedulerStatus:
        current = utc(now)
        snapshot = self.repository.scheduler_snapshot()
        live = bool(
            snapshot["enabled"]
            and snapshot["lease_until"]
            and datetime.fromisoformat(snapshot["lease_until"]) > current
        )
        owned = live and self._started and snapshot["owner_token"] == self._owner
        if snapshot["stopped"]:
            state, live = "global_stop", False
        elif not snapshot["observe"]:
            state, live = "observation_disabled", False
        elif live:
            state = "running" if owned else "other_instance"
        elif snapshot["enabled"]:
            state = "lease_expired"
        else:
            state = "stopped"
        upcoming = []
        if live:
            attempts = self.repository.scheduled_attempts()
            interval = timedelta(seconds=snapshot["interval_seconds"])
            for merchant in self.repository.list_merchants():
                if not merchant.active or not merchant.watched:
                    continue
                earliest = max(current, attempts.get(merchant.id, current - interval) + interval)
                candidate = next_window(merchant.windows, earliest, self.timezone)
                if candidate is not None:
                    upcoming.append(candidate)
        return SchedulerStatus(
            running=live,
            owned=bool(owned and live),
            state=state,
            interval_seconds=snapshot["interval_seconds"],
            next_check=min(upcoming, key=utc) if upcoming else None,
            last_check=(
                datetime.fromisoformat(snapshot["last_check"]) if snapshot["last_check"] else None
            ),
            last_error=snapshot["last_error"],
        )

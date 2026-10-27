"""Orchestration d'un contrôle manuel ; le rythme est géré séparément."""

from datetime import datetime

from roro3.models import CycleResult
from roro3.ports import Connector, Notifier
from roro3.reservations import ReservationService
from roro3.storage import Repository


class MonitorService:
    def __init__(self, repository: Repository, connector: Connector, notifier: Notifier) -> None:
        self.repository, self.connector, self.notifier = repository, connector, notifier
        self.reservations = ReservationService(repository, connector)

    def run_once(self, now: datetime) -> CycleResult:
        if self.repository.is_stopped():
            return CycleResult(stopped=True)
        policy = self.repository.get_policy()
        if not (policy.observe or policy.notify or policy.reserve):
            return CycleResult()
        observations, notifications = 0, 0
        results = []
        for offer in self.connector.get_offers():
            if self.repository.is_stopped():
                return CycleResult(observations, notifications, tuple(results), stopped=True)
            policy = self.repository.get_policy()
            # Chaque contrôle utile aux autres fonctions enrichit aussi l'historique.
            event = self.repository.record_observation(offer, now)
            observations += event != "duplicate"
            if policy.notify and event in {"first_seen_available", "became_available"}:
                self.notifier.send(f"[SIMULATION] Panier disponible : {offer.id}")
                notifications += 1
            if policy.reserve:
                result = self.reservations.try_reserve(offer, now)
                results.append(result)
                if result.outcome in {"confirmed", "unknown", "failed", "preview"}:
                    self.notifier.send(f"[SIMULATION] {offer.id} : {result.outcome}")
                    notifications += 1
        return CycleResult(observations, notifications, tuple(results))

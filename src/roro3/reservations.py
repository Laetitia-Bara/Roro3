"""Frontière d'action unique, persistante et exclusivement simulée."""

import logging
from datetime import datetime

from roro3.models import AttemptStatus, Offer, ReservationResult, utc
from roro3.ports import Connector, ReservationRejected
from roro3.storage import Repository

logger = logging.getLogger(__name__)


class ReservationService:
    def __init__(self, repository: Repository, connector: Connector) -> None:
        if getattr(connector, "is_simulated", False) is not True:
            raise ValueError("Un connecteur exclusivement simulé est obligatoire")
        self.repository = repository
        self.connector = connector

    def try_reserve(self, offer: Offer, now: datetime) -> ReservationResult:
        utc(now)
        # Ne jamais se fier à un état conservé par une ancienne vue de l'interface.
        result = self.repository.claim_attempt(offer, self.connector.account_id, now)
        if result.outcome != "claimed":
            return result
        assert result.attempt_id is not None
        try:
            reference = self.connector.reserve(offer)
        except ReservationRejected:
            status, outcome, reference = AttemptStatus.FAILED, "failed", None
        except Exception:
            # Pas d'exception brute : elle peut contenir des données privées.
            status, outcome, reference = AttemptStatus.UNKNOWN, "unknown", None
        else:
            status, outcome = AttemptStatus.CONFIRMED, "confirmed"
        self.repository.finish_attempt(result.attempt_id, status, now, reference)
        logger.info("Tentative %s : %s (simulateur)", result.attempt_id, outcome)
        return ReservationResult(outcome, result.attempt_id, reference)

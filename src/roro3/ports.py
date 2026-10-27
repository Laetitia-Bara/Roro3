"""Contrats d'accès : aucune implémentation HTTP ou Telegram réelle."""

from typing import Protocol

from roro3.models import Offer


class ReservationRejected(Exception):
    """Refus certain du simulateur, distinct d'une réponse ambiguë."""


class Connector(Protocol):
    is_simulated: bool
    account_id: str

    def get_offers(self) -> tuple[Offer, ...]: ...

    def reserve(self, offer: Offer) -> str: ...


class Notifier(Protocol):
    def send(self, message: str) -> None: ...

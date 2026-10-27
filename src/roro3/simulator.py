"""Services factices : pas d'import réseau, de compte ou de token."""

from collections.abc import Callable, Sequence

from roro3.models import Offer
from roro3.ports import ReservationRejected


class SimulatedConnector:
    is_simulated = True
    account_id = "demo-family"

    def __init__(
        self,
        offers: Sequence[Offer] = (),
        offer_source: Callable[[], Sequence[Offer]] | None = None,
    ) -> None:
        self.offers = tuple(offers)
        self._offer_source = offer_source
        self.reserve_calls: list[Offer] = []

    def get_offers(self) -> tuple[Offer, ...]:
        return tuple(self._offer_source()) if self._offer_source is not None else self.offers

    def reserve(self, offer: Offer) -> str:
        if offer.available == 0:
            raise ReservationRejected("Aucun panier fictif disponible")
        self.reserve_calls.append(offer)
        return f"SIM-{len(self.reserve_calls):04d}-{offer.id}"


class MemoryNotifier:
    """Remplace Telegram dans ce jalon ; les messages restent en mémoire."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)

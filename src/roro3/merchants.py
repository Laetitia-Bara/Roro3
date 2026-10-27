"""Gestion des commerçants et séparation des horaires saisis et estimés."""

from uuid import uuid4

from roro3.analysis import estimate_windows
from roro3.models import Merchant, ScheduleWindow, validate_manual_windows
from roro3.storage import Repository


class MerchantService:
    def __init__(self, repository: Repository, timezone: str = "Europe/Paris") -> None:
        self.repository = repository
        self.timezone = timezone

    def get(self, identifier: str) -> Merchant:
        merchant = self.repository.get_merchant(identifier)
        if merchant is None:
            raise ValueError("Ce commerçant n'existe plus. Actualisez la liste.")
        return merchant

    def create(self, name: str, manual_windows: tuple[ScheduleWindow, ...] = ()) -> Merchant:
        validate_manual_windows(manual_windows)
        # Valider avant d'appeler strip pour conserver des erreurs métier lisibles.
        validated = Merchant(str(uuid4()), name, manual_windows)
        merchant = Merchant(validated.id, name.strip(), tuple(manual_windows))
        self.repository.upsert_merchant(merchant)
        return merchant

    def update(
        self, identifier: str, name: str, manual_windows: tuple[ScheduleWindow, ...]
    ) -> Merchant:
        return self.repository.update_merchant_details(identifier, name, tuple(manual_windows))

    def set_active(self, identifier: str, active: bool) -> Merchant:
        return self.repository.set_merchant_active(identifier, active)

    def set_watched(self, identifier: str, watched: bool) -> Merchant:
        return self.repository.set_merchant_watched(identifier, watched)

    def refresh_estimates(self, identifier: str) -> Merchant:
        self.get(identifier)
        windows = estimate_windows(
            self.repository.list_observations(), identifier, timezone=self.timezone
        )
        return self.repository.replace_estimates(identifier, windows)

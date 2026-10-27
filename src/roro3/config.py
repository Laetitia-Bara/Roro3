"""Configuration centralisée ; aucun connecteur réel n'est accepté."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from roro3.models import RunPolicy


def _flag(values: Mapping[str, str], name: str, default: bool) -> bool:
    value = values.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"Valeur booléenne invalide pour {name}")


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("data/roro3-demo.sqlite3")
    connector: str = "simulated"
    timezone: str = "Europe/Paris"
    policy: RunPolicy = field(default_factory=RunPolicy)

    def __post_init__(self) -> None:
        if self.connector != "simulated":
            raise ValueError("Seul le connecteur simulated est disponible")
        ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls, values: Mapping[str, str]) -> "Settings":
        return cls(
            database_path=Path(values.get("RORO_DATABASE_PATH", "data/roro3-demo.sqlite3")),
            connector=values.get("RORO_CONNECTOR", "simulated"),
            timezone=values.get("RORO_TIMEZONE", "Europe/Paris"),
            policy=RunPolicy(
                observe=_flag(values, "RORO_OBSERVE", True),
                notify=_flag(values, "RORO_NOTIFY", False),
                reserve=_flag(values, "RORO_RESERVE", False),
                dry_run=_flag(values, "RORO_DRY_RUN", True),
            ),
        )

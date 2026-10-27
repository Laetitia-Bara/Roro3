"""Configuration is isolated from machine credentials and fails closed."""

from pathlib import Path

import pytest

from roro3.config import Settings
from roro3.models import RunPolicy


def test_empty_environment_has_safe_local_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.connector == "simulated"
    assert settings.database_path == Path("data/roro3-demo.sqlite3")
    assert settings.policy == RunPolicy()
    assert settings.policy.reserve is False
    assert settings.policy.dry_run is True


@pytest.mark.parametrize("connector", ["real", "tgtg", "https://example.invalid"])
def test_external_connector_configuration_is_rejected(connector: str) -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"RORO_CONNECTOR": connector})


@pytest.mark.parametrize("flag", ["RORO_OBSERVE", "RORO_NOTIFY", "RORO_RESERVE", "RORO_DRY_RUN"])
@pytest.mark.parametrize("value", ["maybe", "2", ""])
def test_invalid_boolean_configuration_is_rejected(flag: str, value: str) -> None:
    with pytest.raises(ValueError):
        Settings.from_env({flag: value})


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_explicit_true_values_are_parsed(value: str) -> None:
    settings = Settings.from_env({"RORO_NOTIFY": value})

    assert settings.policy.notify is True
    assert settings.policy.reserve is False


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off"])
def test_explicit_false_values_are_parsed(value: str) -> None:
    settings = Settings.from_env({"RORO_DRY_RUN": value})

    assert settings.policy.dry_run is False
    assert settings.policy.reserve is False


def test_database_location_can_be_selected_without_machine_environment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "family-demo.sqlite3"

    settings = Settings.from_env({"RORO_DATABASE_PATH": str(database_path)})

    assert settings.database_path == database_path
    assert settings.connector == "simulated"


def test_modes_are_independent_and_explicit() -> None:
    settings = Settings.from_env(
        {
            "RORO_OBSERVE": "false",
            "RORO_NOTIFY": "true",
            "RORO_RESERVE": "true",
            "RORO_DRY_RUN": "false",
        }
    )

    assert settings.policy == RunPolicy(observe=False, notify=True, reserve=True, dry_run=False)

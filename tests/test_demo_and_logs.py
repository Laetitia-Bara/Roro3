import json
import logging
import sys

from roro3.__main__ import main
from roro3.logging_config import RedactingFormatter


def test_cli_demo_is_reproducible_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    database = str(tmp_path / "demo.sqlite3")
    monkeypatch.setattr(sys, "argv", ["roro3", "demo", "--database", database])
    main()
    first = json.loads(capsys.readouterr().out)
    main()
    second = json.loads(capsys.readouterr().out)
    assert first["connector"] == second["connector"] == "simulated"
    assert first["observations"] == second["observations"] == 9
    assert first["attempts"] == second["attempts"] == 0
    assert first["cycle"]["observations"] == 3
    assert second["cycle"]["observations"] == 0


def test_log_formatter_masks_fictitious_sensitive_values():
    record = logging.LogRecord(
        "roro3.test", logging.WARNING, "", 0, "token=fiction@example.invalid other=ok", (), None
    )
    text = RedactingFormatter("%(message)s").format(record)
    assert "fiction@example.invalid" not in text
    assert "[MASQUÉ]" in text
    assert "other=ok" in text

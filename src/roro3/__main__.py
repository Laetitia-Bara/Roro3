"""Point d'entrée : démonstration, état, arrêt et interface locale optionnelle."""

import argparse
import importlib.util
import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from roro3.config import Settings
from roro3.demo import DEMO_NOW, build_demo
from roro3.logging_config import configure_logging
from roro3.storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Roro 3.0 — simulation locale uniquement")
    parser.add_argument("command", choices=("demo", "status", "stop", "resume", "ui"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--family", action="store_true", help="Carnet familial accessible sur le réseau privé"
    )
    parser.add_argument("--host", help="IPv4 privée du PC, uniquement avec ui --family")
    args = parser.parse_args()
    if (args.family and args.command != "ui") or (args.host and not args.family):
        parser.error("--family et --host sont réservés à la commande ui --family")
    load_dotenv(Path.cwd() / ".env", override=False)
    try:
        settings = Settings.from_env(os.environ)
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    if args.database:
        from dataclasses import replace

        settings = replace(settings, database_path=args.database)
    elif args.family:
        from dataclasses import replace

        settings = replace(settings, database_path=Path("data/roro3-family.sqlite3"))
    configure_logging()
    if args.command == "ui":
        if importlib.util.find_spec("nicegui") is None:
            parser.error("Installer l'option interface : pip install -e '.[ui]'")
        try:
            if args.family:
                from roro3.family_access import family_host
                from roro3.family_ui import run_family

                try:
                    host = family_host(args.host)
                    if not 1 <= args.port <= 65535:
                        raise ValueError("Le port doit être compris entre 1 et 65 535.")
                    run_family(settings, host, args.port, show=not args.no_browser)
                except ValueError as error:
                    parser.error(str(error))
                return
            from roro3.ui import run

            run(settings, port=args.port, show=not args.no_browser)
        except ModuleNotFoundError as error:
            if error.name != "nicegui":
                raise
            parser.error("Installer l'option interface : pip install -e '.[ui]'")
        return
    repo = Repository(settings.database_path, settings.policy)
    if args.command in {"stop", "resume"}:
        repo.set_stopped(args.command == "stop")
    result = None
    if args.command == "demo":
        demo = build_demo(settings.database_path, initial_policy=settings.policy)
        result = asdict(demo.monitor.run_once(DEMO_NOW))
    print(
        json.dumps(
            {
                "connector": "none" if repo.dataset_kind == "family" else "simulated",
                "dataset": repo.dataset_kind,
                "stopped": repo.is_stopped(),
                "policy": asdict(repo.get_policy()),
                "cycle": result,
                "observations": len(repo.list_observations()),
                "attempts": len(repo.list_attempts()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

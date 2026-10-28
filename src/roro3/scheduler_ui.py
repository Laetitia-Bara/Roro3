"""Commandes de planification et minuteur applicatif, séparés des pages."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from .scheduler import SchedulerService


def register_scheduler(service: SchedulerService, clock: Callable[[], datetime]) -> None:
    """Un seul minuteur global : les onglets ne créent pas de moteurs supplémentaires."""
    from nicegui import app

    timer = app.timer(1.0, lambda: service.tick(clock()), immediate=False)

    def close() -> None:
        timer.cancel(with_current_invocation=True)
        service.close()

    app.on_shutdown(close)


def render_scheduler_panel(
    service: SchedulerService, clock: Callable[[], datetime], timezone: str
) -> Callable[[], None]:
    """Créer les commandes une seule fois ; le retour actualise seulement leurs états."""
    from nicegui import ui

    zone = ZoneInfo(timezone)
    initial = service.status(clock())

    with ui.card().classes("panel"):
        ui.label("Surveillance planifiée").classes("section-title")
        ui.label("Observation seule · simulation").classes("soft-pill")
        state = ui.label("").classes("scheduler-state")
        next_check = ui.label("").classes("muted")
        last_check = ui.label("").classes("muted")
        error = ui.label("").classes("editor-error")
        error.set_visibility(False)

        def start() -> None:
            try:
                service.start(clock())
            except ValueError as problem:
                ui.notify(str(problem), type="warning")
            else:
                ui.notify("Surveillance planifiée démarrée.", type="positive")
            refresh()

        def stop() -> None:
            service.stop()
            ui.notify("Surveillance planifiée arrêtée.")
            refresh()

        with ui.row().classes("scheduler-actions"):
            start_button = ui.button("Démarrer la surveillance", on_click=start)
            stop_button = ui.button("Arrêter la surveillance", on_click=stop).props("outline")

        interval = (
            ui.number(
                "Fréquence des contrôles (secondes)",
                value=initial.interval_seconds,
                min=15,
                max=3600,
                step=15,
                format="%.0f",
            )
            .props("outlined")
            .classes("full-width")
        )

        def save_interval() -> None:
            value = interval.value
            if value is None or not float(value).is_integer():
                ui.notify("Indiquez un nombre entier entre 15 et 3 600 secondes.", type="warning")
                return
            try:
                service.set_interval_seconds(int(value))
            except ValueError as problem:
                ui.notify(str(problem), type="warning")
            else:
                ui.notify("Fréquence enregistrée.", type="positive")
            refresh()

        ui.button("Enregistrer la fréquence", on_click=save_interval).props("flat")
        saved_interval = ui.label("").classes("muted")
        ui.separator()
        ui.label(
            "Les contrôles planifiés enregistrent les disponibilités pendant les créneaux. "
            "Aucune notification ni commande n’est créée."
        ).classes("muted")
        ui.label("Le serveur lancé dans VS Code doit rester en fonctionnement.").classes("muted")

    def refresh() -> None:
        status = service.status(clock())
        labels = {
            "stopped": "Arrêtée · démarrage manuel",
            "running": "Active" if status.next_check else "Active · en attente d’un créneau",
            "other_instance": "Active dans une autre instance",
            "global_stop": "Arrêt global actif",
            "observation_disabled": "Observation désactivée",
            "lease_expired": "Interrompue · démarrage nécessaire",
        }
        state.set_text(labels.get(status.state, "Arrêtée"))
        next_check.set_text(
            "Prochain contrôle : " + status.next_check.astimezone(zone).strftime("%d/%m à %H:%M:%S")
            if status.next_check
            else "Prochain contrôle : aucun passage prévu"
        )
        last_check.set_text(
            "Dernier contrôle : " + status.last_check.astimezone(zone).strftime("%d/%m à %H:%M:%S")
            if status.last_check
            else "Dernier contrôle : aucun"
        )
        saved_interval.set_text(f"Rythme enregistré : {status.interval_seconds} secondes")
        error.set_text(status.last_error or "")
        error.set_visibility(bool(status.last_error))
        start_button.set_enabled(
            not status.running and status.state not in {"global_stop", "observation_disabled"}
        )
        stop_button.set_enabled(status.running or status.owned)

    refresh()
    return refresh

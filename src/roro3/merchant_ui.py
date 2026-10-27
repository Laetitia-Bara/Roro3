"""Éditeur local de commerçants ; toutes les mutations passent par le service métier."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import time
from typing import TYPE_CHECKING

from .models import ScheduleWindow

if TYPE_CHECKING:
    from .merchants import MerchantService
    from .models import Merchant

WEEKDAYS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}


def parse_manual_windows(
    rows: Sequence[tuple[int | None, str, str]],
) -> tuple[ScheduleWindow, ...]:
    """Transformer les champs, sans écrire de données ni accepter une origine estimée."""
    windows = []
    for weekday, start, end in rows:
        if weekday not in WEEKDAYS:
            raise ValueError("Choisissez un jour pour chaque créneau.")
        if not all(re.fullmatch(r"\d{2}:\d{2}", value or "") for value in (start, end)):
            raise ValueError("Renseignez un début et une fin au format HH:MM.")
        try:
            windows.append(
                ScheduleWindow(weekday, time.fromisoformat(start), time.fromisoformat(end))
            )
        except ValueError as error:
            raise ValueError("Chaque créneau doit commencer avant sa fin, le même jour.") from error
    return tuple(windows)


def open_merchant_editor(
    service: MerchantService,
    on_saved: Callable[[], None],
    merchant: Merchant | None = None,
) -> None:
    """Afficher un formulaire temporaire ; Annuler ne modifie jamais la base."""
    from nicegui import ui

    rows = []
    with ui.dialog().props("persistent") as dialog, ui.card().classes("merchant-editor"):
        ui.label("Modifier le commerçant" if merchant else "Ajouter un commerçant").classes(
            "section-title"
        )
        ui.label(
            "Vos réglages restent sur cet ordinateur. Aucun service réel n'est connecté."
        ).classes("muted")
        name = (
            ui.input("Nom du commerçant", value=merchant.name if merchant else "")
            .props("outlined maxlength=100 autofocus")
            .classes("full-width")
        )
        ui.label("Créneaux manuels").style("font-size: 16px; font-weight: 700")
        ui.label(
            "Ajoutez plusieurs jours ou plages horaires. Un créneau peut être adjacent à un autre, "
            "sans le chevaucher."
        ).classes("muted")
        fields = ui.column().classes("full-width").style("gap: 12px")

        def add_window(window: ScheduleWindow | None = None) -> None:
            with fields, ui.element("div").classes("window-editor-row") as container:
                day = ui.select(
                    WEEKDAYS, value=window.weekday if window else 0, label="Jour"
                ).props("outlined")
                start = ui.input(
                    "Début", value=window.start.strftime("%H:%M") if window else "18:00"
                )
                start.props("outlined type=time step=60")
                end = ui.input("Fin", value=window.end.strftime("%H:%M") if window else "18:15")
                end.props("outlined type=time step=60")
                row = (container, day, start, end)

                def remove_window() -> None:
                    rows.remove(row)
                    container.delete()

                ui.button("Retirer", on_click=remove_window).props("flat color=negative")
                rows.append(row)

        manual = tuple(w for w in merchant.windows if w.source == "manual") if merchant else ()
        for window in manual:
            add_window(window)
        ui.button("Ajouter un créneau", on_click=lambda: add_window()).props("outline")
        if not manual:
            ui.label(
                "Vous pouvez aussi enregistrer un commerçant sans horaire pour le moment."
            ).classes("muted")
        if merchant:
            estimated = tuple(w for w in merchant.windows if w.source == "estimated")
            if estimated:
                with ui.column().classes("estimated-note"):
                    ui.label("Créneaux estimés conservés").style("font-weight: 700")
                    for window in estimated:
                        ui.label(
                            f"{WEEKDAYS[window.weekday]} {window.start:%H:%M}–{window.end:%H:%M} "
                            f"· {window.sample_count} journées observées"
                        ).classes("muted")
                    ui.label("Ces estimations ne sont pas modifiées par ce formulaire.").classes(
                        "muted"
                    )
        error_label = ui.label("").classes("editor-error")
        error_label.set_visibility(False)

        def close() -> None:
            dialog.close()
            dialog.delete()

        def save() -> None:
            try:
                windows = parse_manual_windows(
                    [(day.value, start.value, end.value) for _, day, start, end in rows]
                )
                if merchant:
                    service.update(merchant.id, name.value, windows)
                else:
                    service.create(name.value, windows)
            except ValueError as error:
                error_label.set_text(str(error))
                error_label.set_visibility(True)
                return
            # La notification doit utiliser le contexte du dialogue encore vivant.
            ui.notify("Commerçant enregistré.", type="positive")
            close()
            on_saved()

        with ui.row().classes("editor-actions"):
            ui.button("Annuler", on_click=close).props("flat")
            ui.button("Enregistrer", on_click=save)
    dialog.open()

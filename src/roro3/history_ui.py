"""Consultation de l'historique, sans écriture ni connexion externe."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from .history import HistoryFilters, HistoryService
from .storage import Repository

EVENT_LABELS = {
    "unavailable": "Aucun panier disponible",
    "first_seen_available": "Disponible dès le premier relevé",
    "became_available": "Passage de zéro à disponible",
    "still_available": "Toujours disponible",
}


def parse_filters(merchant: str, event: str, start: str, end: str) -> HistoryFilters:
    try:
        return HistoryFilters(
            merchant or None,
            event or None,
            date.fromisoformat(start) if start else None,
            date.fromisoformat(end) if end else None,
        )
    except ValueError as error:
        raise ValueError("Vérifiez les dates (début avant fin) et les filtres choisis.") from error


def register_history_page(repo: Repository, timezone: str) -> None:
    from nicegui import ui

    from .merchant_ui import WEEKDAYS
    from .ui import _CSS

    service = HistoryService(repo, timezone)
    zone = ZoneInfo(timezone)

    def formatted(value: str) -> str:
        return (
            datetime.fromisoformat(value)
            .astimezone(zone)
            .strftime("%d/%m/%Y à %H:%M:%S (%Z, UTC%z)")
        )

    @ui.page("/history")
    def history_page() -> None:
        ui.colors(primary="#3f6e5a", negative="#a94b48")
        ui.add_css(_CSS)
        state = {"filters": HistoryFilters(), "page": 1}
        names = {m.id: m.name for m in repo.list_merchants()}
        for record in repo.list_observations():
            names.setdefault(record["merchant_id"], "Ancien commerçant · " + record["merchant_id"])
        family = repo.dataset_kind == "family"
        with ui.row().classes("topbar"):
            ui.label("Roro · Historique et estimations").classes("brand")
            ui.link("Retour au tableau de bord", "/")
        ui.label(
            "Relevés saisis manuellement · aucun compte connecté"
            if family
            else "Données fictives · simulation locale"
        ).classes("soft-pill")
        with ui.card().classes("panel"):
            ui.label("Retrouver vos relevés").classes("section-title")
            with ui.row().classes("full-width").style("align-items: start"):
                merchant = (
                    ui.select({"": "Tous les commerçants", **names}, value="", label="Commerçant")
                    .style("min-width: 220px; flex: 1")
                    .props("outlined")
                )
                event = (
                    ui.select(
                        {"": "Tous les événements", **EVENT_LABELS}, value="", label="Événement"
                    )
                    .style("min-width: 220px; flex: 1")
                    .props("outlined")
                )
                start = ui.input("Du", value="").props("outlined type=date")
                end = ui.input("Au (inclus)", value="").props("outlined type=date")
            ui.label(f"Dates inclusives dans le fuseau {timezone}.").classes("muted")
            error = ui.label("").classes("editor-error")
            error.set_visibility(False)

            def apply() -> None:
                try:
                    filters = parse_filters(merchant.value, event.value, start.value, end.value)
                except ValueError as failure:
                    error.set_text(f"{failure} Résultats précédents conservés.")
                    error.set_visibility(True)
                    return
                state.update(filters=filters, page=1)
                error.set_visibility(False)
                results.refresh()

            def reset() -> None:
                merchant.set_value("")
                event.set_value("")
                start.set_value("")
                end.set_value("")
                apply()

            with ui.row():
                ui.button("Appliquer / actualiser", on_click=apply)
                ui.button("Réinitialiser", on_click=reset).props("outline")

        @ui.refreshable
        def results() -> None:
            selected = service.query(state["filters"], page=state["page"])
            state["page"] = selected.page
            filters = state["filters"]
            scope = names.get(filters.merchant_id, "Tous les commerçants")
            scope += " · " + EVENT_LABELS.get(filters.event, "Tous les événements")
            scope += (
                f" · {filters.start_date or 'début de l’historique'} → "
                f"{filters.end_date or 'fin de l’historique'}"
            )
            with ui.card().classes("panel"):
                ui.label("Analyse de la sélection").classes("section-title")
                ui.label(scope).classes("muted")
                with ui.row().classes("metrics"):
                    for count, label in (
                        (selected.total, "relevés"),
                        (selected.summary.observed_days, "journées avec un relevé"),
                        (selected.summary.transition_count, "passages de zéro à disponible"),
                        (selected.summary.first_seen_count, "premières présences"),
                    ):
                        with ui.column():
                            ui.label(str(count)).classes("metric-number")
                            ui.label(label).classes("muted")
                if selected.total:
                    ui.label("Premier relevé : " + formatted(selected.summary.first_observed_at))
                    ui.label("Dernier relevé : " + formatted(selected.summary.last_observed_at))
                ui.label(
                    "Les comptes portent sur tous les résultats filtrés, pas seulement cette page. "
                    "Une journée avec un relevé ne signifie pas une journée surveillée en continu."
                ).classes("muted")
            with ui.card().classes("panel"):
                ui.label("Comprendre les horaires estimés").classes("section-title")
                ui.label(
                    "Seuls les passages observés de zéro à disponible sont regroupés par jour "
                    "de semaine et quart d'heure. Trois journées distinctes dans le même groupe "
                    "atteignent le seuil descriptif. Une première présence "
                    "ne date pas une apparition."
                ).classes("muted")
                if not filters.merchant_id:
                    ui.label("Choisissez un commerçant pour voir ses groupes horaires.")
                for pattern in selected.patterns:
                    ui.label(
                        f"{WEEKDAYS[pattern.weekday]} · {pattern.start:%H:%M}–{pattern.end:%H:%M} "
                        f"· {pattern.distinct_days} journée(s) distincte(s)"
                    ).style("font-weight: 650")
                    ui.label(
                        "Seuil de 3 journées atteint" if pattern.eligible else "Encore peu de recul"
                    ).classes("muted")
                if filters.merchant_id and not selected.patterns:
                    ui.label("Aucun groupe exploitable avec ces filtres.")
                ui.label(
                    "Cette analyse suit vos filtres et ne modifie aucun horaire enregistré. "
                    "Elle ne calcule pas une probabilité ni une heure exacte de publication. "
                    "Une remise en vente reste possible. Les interruptions et le dernier quart "
                    "d'heure finissant à minuit ne sont pas modélisés."
                ).classes("muted")
            with ui.card().classes("panel"):
                ui.label("Relevés conservés").classes("section-title")
                ui.label(
                    f"Page {selected.page} sur {selected.total_pages} · "
                    f"{selected.total} relevé(s) · 20 par page"
                ).classes("muted")
                for row in selected.rows:
                    with ui.column().classes("history-line").style("gap: 3px"):
                        ui.label(names.get(row["merchant_id"], "Ancien commerçant")).style(
                            "font-weight: 700"
                        )
                        ui.label(formatted(row["observed_at"])).classes("muted")
                        ui.label(f"{row['available']} panier(s) · {EVENT_LABELS[row['event']]}")
                if not selected.rows:
                    ui.label("Aucun relevé ne correspond à cette sélection.")

                def turn(delta: int) -> None:
                    state["page"] = selected.page + delta
                    results.refresh()

                with ui.row():
                    ui.button("Précédent", on_click=lambda: turn(-1)).set_enabled(selected.page > 1)
                    ui.button("Suivant", on_click=lambda: turn(1)).set_enabled(
                        selected.page < selected.total_pages
                    )

        results()
        ui.label("Lecture seule · actualisation à votre demande · " + timezone).classes("footer")

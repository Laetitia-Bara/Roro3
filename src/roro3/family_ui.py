"""Interface familiale mobile, saisies manuelles dans une base distincte."""

from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .family_access import FamilyAccessMiddleware, load_access_code
from .history_ui import register_history_page
from .merchant_ui import WEEKDAYS, open_merchant_editor
from .merchants import MerchantService
from .storage import Repository


def parse_quantity(value: float | None) -> int:
    if type(value) not in (int, float) or not 0 <= value <= 1000 or int(value) != value:
        raise ValueError("Saisissez un nombre entier de paniers entre 0 et 1 000.")
    return int(value)


def run_family(settings: Settings, host: str, port: int, show: bool = True) -> None:
    from nicegui import app, ui

    from .ui import _CSS

    repo = Repository(settings.database_path, dataset_kind="family")
    merchants = MerchantService(repo, settings.timezone)
    access_file = Path(settings.database_path).parent / "family-access.json"
    code = load_access_code(access_file)
    app.add_middleware(FamilyAccessMiddleware, access_code=code, authority=f"{host}:{port}")
    register_history_page(repo, settings.timezone)
    print(f"Roro familial : http://{host}:{port}")
    print(f"Code familial dans le fichier privé : {access_file.resolve()}")

    @ui.page("/")
    def family_page() -> None:
        ui.colors(primary="#3f6e5a", negative="#a94b48")
        ui.add_css(_CSS)
        ui.add_head_html(
            '<meta name="apple-mobile-web-app-capable" content="yes">'
            '<meta name="apple-mobile-web-app-title" content="Roro Famille">'
            '<meta name="theme-color" content="#3f6e5a">'
        )
        with ui.row().classes("topbar"):
            ui.label("Roro · Famille").classes("brand")
            ui.link("Historique et estimations", "/history")
        with ui.column().classes("hero"):
            ui.label("Votre carnet partagé").classes("eyebrow")
            ui.label("Votre carnet des disponibilités.").classes("hero-title")
            ui.label("Notez les disponibilités vérifiées dans l'application officielle.").classes(
                "muted"
            )
            ui.label("Saisie manuelle · aucun compte Too Good To Go connecté").classes("soft-pill")
            ui.label(
                "Le compte et les réservations restent dans l'application officielle."
            ).classes("muted")

        @ui.refreshable
        def dashboard() -> None:
            current = repo.list_merchants()
            stopped = repo.is_stopped()

            def stop() -> None:
                repo.set_stopped(not repo.is_stopped())
                dashboard.refresh()

            with ui.row().classes("merchant-heading"):
                ui.label("Votre espace familial").classes("section-title")
                ui.button(
                    "Ajouter un commerçant",
                    on_click=lambda: open_merchant_editor(merchants, dashboard.refresh),
                )
                ui.button(
                    "Reprendre les saisies" if stopped else "Arrêt global",
                    on_click=stop,
                    color="negative",
                ).props("outline")
            if stopped:
                ui.label("Saisies arrêtées. L'historique reste consultable.").classes(
                    "editor-error"
                )
            if not current:
                ui.label("Ajoutez vos deux ou trois premiers commerces pour commencer.").classes(
                    "muted"
                )
            with ui.card().classes("panel"):
                ui.label("Noter une disponibilité").classes("section-title")
                ui.label(
                    "Saisissez ce que vous voyez maintenant. Notez aussi 0 quand aucun panier "
                    "n'est disponible. Chaque saisie prend l'heure actuelle du serveur."
                ).classes("muted")
                active = {m.id: m.name for m in current if m.active}
                selected = (
                    ui.select(active, label="Commerçant observé")
                    .classes("full-width")
                    .props("outlined")
                )
                quantity = (
                    ui.number(
                        "Paniers disponibles (0 si aucun)",
                        value=0,
                        min=0,
                        max=1000,
                        precision=0,
                        step=1,
                    )
                    .classes("full-width")
                    .props("outlined")
                )
                error = ui.label("").classes("editor-error")

                def record() -> None:
                    try:
                        repo.record_manual_observation(
                            selected.value,
                            parse_quantity(quantity.value),
                            datetime.now(UTC),
                            settings.timezone,
                        )
                    except ValueError as failure:
                        error.set_text(str(failure))
                        return
                    error.set_text("")
                    ui.notify("Relevé manuel conservé.", type="positive")
                    total.set_text(
                        f"{len(repo.list_observations())} relevé(s) manuel(s) conservé(s)"
                    )

                ui.button("Enregistrer le relevé", on_click=record).set_enabled(
                    bool(active) and not stopped
                )
                total = ui.label(f"{len(repo.list_observations())} relevé(s) manuel(s) conservé(s)")
                ui.link("Consulter les relevés et leur analyse", "/history")

            ui.label("Commerçants et horaires").classes("section-title")
            with ui.element("div").classes("merchant-grid full-width"):
                for merchant in current:
                    with ui.card().classes("panel"):
                        ui.label(merchant.name).classes("merchant-name")
                        ui.label("Actif" if merchant.active else "Désactivé").classes(
                            "merchant-state"
                        )
                        for window in merchant.windows:
                            ui.label(
                                f"{WEEKDAYS[window.weekday]} · "
                                f"{window.start:%H:%M}–{window.end:%H:%M}"
                            )
                            ui.label(
                                "Manuel"
                                if window.source == "manual"
                                else f"Estimé · {window.sample_count} journées"
                            ).classes("muted")
                        with ui.row():
                            ui.button(
                                "Modifier",
                                on_click=lambda m=merchant: open_merchant_editor(
                                    merchants, dashboard.refresh, m
                                ),
                            ).props("outline")

                            def toggle(m=merchant) -> None:
                                merchants.set_active(m.id, not m.active)
                                dashboard.refresh()

                            ui.button(
                                "Désactiver" if merchant.active else "Réactiver", on_click=toggle
                            ).props("flat")

                            def estimate(key=merchant.id) -> None:
                                merchants.refresh_estimates(key)
                                ui.notify("Calcul actualisé à partir des saisies manuelles.")
                                dashboard.refresh()

                            ui.button("Recalculer les estimations", on_click=estimate).props("flat")

        dashboard()
        ui.label("Wi-Fi privé · serveur actif sur l'ordinateur · " + settings.timezone).classes(
            "footer"
        )

    ui.run(
        host=host,
        port=port,
        title="Roro Famille",
        show=show,
        reload=False,
        on_air=False,
        tailwind=False,
        language="fr",
        show_welcome_message=False,
        proxy_headers=False,
    )

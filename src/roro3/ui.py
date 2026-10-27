"""Optional local NiceGUI view; the application core has no GUI dependency."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from .config import Settings

_CSS = """
body { background: #f7f5ef; color: #243b31; font-family: 'Segoe UI', Arial, sans-serif; }
.nicegui-content { max-width: 1240px; margin: auto; padding: 30px 24px 48px; gap: 24px; }
.topbar { width: 100%; align-items: center; justify-content: space-between; }
.brand { font-size: 25px; font-weight: 800; letter-spacing: -.8px; }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; }
.muted { color: #66786e; font-size: 13px; line-height: 1.65; }
.hero { width: 100%; border-radius: 26px; padding: 30px; background: #dce8dd; gap: 16px; }
.hero-title { font-size: clamp(29px, 4vw, 43px); font-weight: 750;
    line-height: 1.13; letter-spacing: -1.4px; }
.hero-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 8px; }
.dashboard { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(290px, 1fr);
    gap: 24px; width: 100%; align-items: start; }
.stack { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.section-title { font-size: 20px; font-weight: 750; letter-spacing: -.5px; }
.merchant-grid { display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; }
.panel { padding: 22px; border: 1px solid #e3e7de; border-radius: 22px;
    box-shadow: none; width: 100%; gap: 12px; }
.merchant-name { font-size: 18px; font-weight: 750; }
.next-window { font-size: 22px; font-weight: 750; letter-spacing: -.5px; }
.soft-pill { background: #edf3eb; color: #3f6e5a; padding: 5px 10px;
    border-radius: 20px; font-size: 11px; font-weight: 700; }
.metrics { display: flex; flex-wrap: wrap; gap: 26px; margin-top: 8px; }
.metric-number { font-size: 27px; font-weight: 750; line-height: 1.2; }
.history-line { width: 100%; padding: 9px 0; border-bottom: 1px solid #edf0e9; }
.state-line { font-size: 13px; font-weight: 650; color: #3f6e5a; }
.footer { font-size: 12px; color: #66786e; }
.q-btn { border-radius: 12px; text-transform: none; font-weight: 650; }
.q-toggle__label { font-size: 14px; }
@media (max-width: 800px) {
    .dashboard { grid-template-columns: 1fr; }
    .nicegui-content { padding: 20px 16px; }
    .hero { padding: 24px; }
}
"""


def run(settings: Settings, port: int = 8080, show: bool = True) -> None:
    """Open a manual, simulated dashboard bound exclusively to loopback."""
    try:
        from nicegui import ui
    except ImportError as exc:
        raise RuntimeError("Installez l'option interface : pip install -e '.[ui]'.") from exc

    from .demo import build_demo
    from .planning import next_window

    application = build_demo(
        settings.database_path,
        now=datetime.now(UTC),
        initial_policy=settings.policy,
    )
    local_zone = ZoneInfo(settings.timezone)
    weekdays = ("Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim.")

    def local_timestamp(value: str) -> str:
        return datetime.fromisoformat(value).astimezone(local_zone).strftime("%d/%m à %H:%M:%S")

    @ui.page("/")
    def index() -> None:
        ui.colors(primary="#3f6e5a", secondary="#748e79", negative="#a94b48")
        ui.add_css(_CSS)

        def update_policy(field: str, value: bool) -> None:
            current = application.repo.get_policy()
            if getattr(current, field) != value:
                application.repo.set_policy(replace(current, **{field: value}))
                dashboard.refresh()

        def set_stopped(value: bool) -> None:
            application.repo.set_stopped(value)
            dashboard.refresh()

        def run_cycle() -> None:
            result = application.monitor.run_once(datetime.now(UTC))
            if result.stopped:
                ui.notify(
                    "Le suivi est arrêté. Reprenez-le pour lancer un cycle fictif.", type="warning"
                )
            else:
                ui.notify(
                    f"Cycle fictif : {result.observations} relevés, "
                    f"{result.notifications} notifications et "
                    f"{len(result.reservations)} décisions de réservation.",
                    type="positive",
                )
            dashboard.refresh()

        @ui.refreshable
        def dashboard() -> None:
            now = datetime.now(UTC)
            policy = application.repo.get_policy()
            stopped = application.repo.is_stopped()
            merchants = application.repo.list_merchants()
            observations = application.repo.list_observations()
            attempts = application.repo.list_attempts()
            names = {merchant.id: merchant.name for merchant in merchants}
            offer_names = {
                record["offer_id"]: names.get(record["merchant_id"], "Panier fictif")
                for record in observations
            }

            with ui.row().classes("topbar"):
                ui.label("Roro 3.0").classes("brand")
                ui.label("Simulation locale").classes("soft-pill")
            with ui.column().classes("hero"):
                ui.label("L'atelier des bons moments").classes("eyebrow")
                ui.label("Vos commerçants, au bon moment.").classes("hero-title")
                ui.label(
                    "Explorez les créneaux et testez le suivi avec des paniers fictifs."
                ).classes("muted")
                with ui.element("div").classes("hero-actions"):
                    cycle = ui.button("Lancer un cycle fictif", on_click=run_cycle)
                    cycle.set_enabled(not stopped)
                    if stopped:
                        ui.button("Reprendre le suivi", on_click=lambda: set_stopped(False)).props(
                            "outline"
                        )
                    else:
                        ui.button(
                            "Arrêt global", on_click=lambda: set_stopped(True), color="negative"
                        ).props("outline")
                ui.label("Suivi arrêté" if stopped else "Prêt · cycles manuels uniquement").classes(
                    "state-line"
                )
                with ui.element("div").classes("metrics"):
                    for value, label in (
                        (len(merchants), "commerçants fictifs"),
                        (len(observations), "relevés conservés"),
                        (len(attempts), "tentatives conservées"),
                    ):
                        with ui.column().style("gap: 2px"):
                            ui.label(str(value)).classes("metric-number")
                            ui.label(label).classes("muted")

            with ui.element("div").classes("dashboard"):
                with ui.element("div").classes("stack"):
                    ui.label("Vos prochains créneaux").classes("section-title")
                    with ui.element("div").classes("merchant-grid"):
                        for merchant in merchants:
                            with ui.card().classes("panel"):
                                ui.label(merchant.name).classes("merchant-name")
                                upcoming = next_window(merchant.windows, now, settings.timezone)
                                ui.label(
                                    upcoming.astimezone(local_zone).strftime("%d/%m · %H:%M")
                                    if upcoming
                                    else "Aucun créneau"
                                ).classes("next-window")
                                ui.label(
                                    "Prochaine fenêtre · heure de Paris"
                                    if settings.timezone == "Europe/Paris"
                                    else f"Prochaine fenêtre · {settings.timezone}"
                                ).classes("muted")
                                ui.separator()
                                for window in merchant.windows[:3]:
                                    origin = (
                                        "Manuel"
                                        if window.source == "manual"
                                        else f"Estimé · {window.sample_count} observations"
                                    )
                                    ui.label(
                                        f"{weekdays[window.weekday]} "
                                        f"{window.start:%H:%M}–{window.end:%H:%M}"
                                    ).style("font-weight: 650")
                                    ui.label(origin).classes("muted")
                        if not merchants:
                            ui.label("Aucun commerçant de démonstration.").classes("muted")
                    with ui.card().classes("panel"):
                        ui.label("Derniers relevés").classes("section-title")
                        for record in observations[:5]:
                            with ui.column().classes("history-line").style("gap: 2px"):
                                ui.label(names.get(record["merchant_id"], "Commerçant fictif"))
                                ui.label(
                                    f"{record['available']} panier(s) · "
                                    f"{local_timestamp(record['observed_at'])}"
                                ).classes("muted")
                        if not observations:
                            ui.label(
                                "Lancez un premier cycle fictif pour observer les disponibilités."
                            ).classes("muted")

                with ui.element("div").classes("stack"):
                    with ui.card().classes("panel"):
                        ui.label("Ce qui est activé").classes("section-title")
                        for field, label in (
                            ("observe", "Observer les disponibilités"),
                            ("notify", "Notifications fictives"),
                            ("reserve", "Réservation fictive"),
                            ("dry_run", "Aucune commande, même fictive"),
                        ):
                            ui.switch(
                                label,
                                value=getattr(policy, field),
                                on_change=lambda event, key=field: update_policy(
                                    key, bool(event.value)
                                ),
                            )
                        ui.label(
                            "Les modes sont indépendants. Aucun service réel n'est connecté."
                        ).classes("muted")
                    with ui.card().classes("panel"):
                        ui.label("Dernières tentatives").classes("section-title")
                        statuses = {
                            "preview": "Simulation sans commande",
                            "pending": "En cours",
                            "confirmed": "Commande fictive confirmée",
                            "failed": "Échec fictif",
                            "unknown": "Résultat à vérifier",
                        }
                        for record in attempts[:5]:
                            ui.label(offer_names.get(record["offer_id"], "Panier fictif"))
                            ui.label(
                                statuses.get(record["status"], "Tentative enregistrée")
                            ).classes("muted")
                            ui.label(local_timestamp(record["created_at"])).classes("muted")
                        if not attempts:
                            ui.label(
                                "Aucune tentative. Activez la réservation fictive "
                                "pour explorer ce parcours."
                            ).classes("muted")
                    with ui.card().classes("panel"):
                        ui.label("Journal de démonstration").classes("section-title")
                        for message in application.notifier.messages[-3:]:
                            text = message.removeprefix("[SIMULATION] ")
                            for offer_id, merchant_name in offer_names.items():
                                text = text.replace(offer_id, merchant_name)
                            for code, label in statuses.items():
                                if text.endswith(f": {code}"):
                                    text = text.removesuffix(code) + label.lower()
                            ui.label(text).classes("muted")
                        if not application.notifier.messages:
                            ui.label("Les notifications fictives apparaîtront ici.").classes(
                                "muted"
                            )
            ui.label(
                f"Données fictives · aucune réservation réelle · affichage {settings.timezone}"
            ).classes("footer")

        dashboard()

    ui.run(
        host="127.0.0.1",
        port=port,
        title="Roro 3.0",
        show=show,
        reload=False,
        on_air=False,
        tailwind=False,
        language="fr",
        show_welcome_message=False,
    )

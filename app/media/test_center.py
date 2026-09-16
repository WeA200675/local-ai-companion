from __future__ import annotations

from dataclasses import dataclass

from app.media.service import MediaService
from app.media.workflow_routing import workflow_suitability_score


@dataclass(frozen=True, slots=True)
class MediaProfileTest:
    profile_id: str
    label: str
    runnable: bool
    kinds: tuple[str, ...]
    output_evidence: tuple[str, ...]
    reference_supported: bool
    render_controls: tuple[str, ...]
    warnings: tuple[str, ...]
    error: str
    suitability_score: int = 0
    successes: int = 0
    failures: int = 0
    quarantined: bool = False


@dataclass(frozen=True, slots=True)
class MediaTestReport:
    backend_enabled: bool
    service_enabled: bool
    available_kinds: tuple[str, ...]
    profiles: tuple[MediaProfileTest, ...]

    @property
    def ready_profiles(self) -> int:
        return sum(1 for profile in self.profiles if profile.runnable)

    @property
    def failed_profiles(self) -> int:
        return sum(1 for profile in self.profiles if not profile.runnable)

    def render_text(self) -> str:
        lines = [
            "Lokales Medien-Testzentrum",
            "",
            f"Medienservice: {'bereit' if self.service_enabled else 'nicht bereit'}",
            f"Legacy-Backend: {'konfiguriert' if self.backend_enabled else 'nicht konfiguriert'}",
            f"Verfügbare Arten: {', '.join(self.available_kinds) or 'keine'}",
            f"Workflow-Profile: {self.ready_profiles} bereit, {self.failed_profiles} nicht bereit",
        ]
        if not self.profiles:
            lines.extend(("", "Keine Workflow-Profile im aktiven Katalog."))
            return "\n".join(lines)

        for profile in self.profiles:
            lines.extend(
                (
                    "",
                    f"[{'OK' if profile.runnable else 'FEHLER'}] {profile.label} ({profile.profile_id})",
                    f"  Arten: {', '.join(profile.kinds) or 'keine'}",
                    f"  Output-Evidenz: {', '.join(profile.output_evidence) or 'keine'}",
                    f"  Referenz: {'ja' if profile.reference_supported else 'nein'}",
                    f"  Rendersteuerung: {', '.join(profile.render_controls) or 'Workflow-Defaults'}",
                    f"  Eignungsscore: {profile.suitability_score}/100 · lokale Ergebnisse {profile.successes} OK / {profile.failures} Fehler",
                )
            )
            if profile.quarantined:
                lines.append("  Quarantäne: aktiv — erfolgreicher Eignungstest gibt das Profil wieder frei")
            if profile.error:
                lines.append(f"  Fehler: {profile.error}")
            lines.extend(f"  Warnung: {warning}" for warning in profile.warnings)
        return "\n".join(lines)


def build_media_test_report(service: MediaService) -> MediaTestReport:
    health_repository = getattr(service, "workflow_health", None)
    profiles = []
    for capability in service.workflow_capabilities.values():
        kind = capability.runnable_kinds[0] if capability.runnable_kinds else "image"
        health = (
            health_repository.get(capability.profile_id)
            if health_repository is not None
            else None
        )
        profiles.append(
            MediaProfileTest(
                profile_id=capability.profile_id,
                label=capability.label,
                runnable=capability.runnable,
                kinds=capability.runnable_kinds,
                output_evidence=capability.output_evidence,
                reference_supported=capability.reference_supported,
                render_controls=capability.render_controls,
                warnings=capability.warnings,
                error=capability.error,
                suitability_score=workflow_suitability_score(
                    capability,
                    kind=kind,
                    reference_needed=False,
                ),
                successes=health.successes if health is not None else 0,
                failures=health.failures if health is not None else 0,
                quarantined=health.quarantined if health is not None else False,
            )
        )
    return MediaTestReport(
        backend_enabled=service.backend.enabled,
        service_enabled=service.enabled,
        available_kinds=service.available_media_kinds,
        profiles=tuple(sorted(profiles, key=lambda item: item.profile_id)),
    )

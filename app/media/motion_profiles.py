from __future__ import annotations

from app.media.capabilities import inspect_workflow_profile
from app.media.profiles import WorkflowProfile


def with_detected_motion_profile(profile: WorkflowProfile) -> WorkflowProfile:
    """Enrich one runtime profile from conservative workflow evidence.

    The returned copy is ephemeral. User catalogs are never rewritten and a
    declared motion kind is never added unless the workflow contains both a
    frame-producing pipeline and a matching animated output.
    """

    capability = inspect_workflow_profile(profile)
    evidence = set(capability.output_evidence)
    detected = [kind for kind in ("gif", "video") if kind in evidence]
    if not detected:
        return profile

    kinds = list(profile.kinds)
    for kind in detected:
        if kind not in kinds:
            kinds.append(kind)

    routing_tags = list(profile.routing_tags)
    if "motion" not in routing_tags:
        routing_tags.append("motion")

    return profile.model_copy(
        update={
            "kinds": kinds,
            "routing_tags": routing_tags,
        }
    )

"""Map a free-text intake to the best-fit archetype + build target.

Deterministic, rule-based scoring by default (keyword hits + primitive signals)
so it is offline-safe and testable. An optional LLM client can refine the choice
when connected, but the rule-based result is always the floor.

Target selection (python|appkit):
- Honor an explicit hint in the intake (e.g. "typescript", "react", "appkit",
  or "python", "streamlit").
- Otherwise use the archetype's ``default_target``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from composer.archetypes.catalog import (
    Archetype,
    ARCHETYPES,
    TARGET_APPKIT,
    TARGET_PYTHON,
    default_archetype,
    get_archetype,
)
from composer.models.intake import IntakeSpec

# Below this score we are not confident enough; surface "help me decide".
_CONFIDENCE_FLOOR = 1.0

_APPKIT_HINTS = ("appkit", "typescript", "react", "next.js", "nextjs", "node", "shadcn")
_PYTHON_HINTS = ("python", "streamlit", "fastapi", "dash")


@dataclass(frozen=True, slots=True)
class Classification:
    archetype_id: str
    target: str
    score: float
    rationale: str
    candidates: list[tuple[str, float]] = field(default_factory=list)
    needs_help: bool = False

    @property
    def archetype(self) -> Archetype:
        return ARCHETYPES[self.archetype_id]


def _intake_text(intake: IntakeSpec) -> str:
    parts = [
        intake.primary_use_case_description or "",
        " ".join(intake.user_stories or []),
        intake.workflow_requirements or "",
        intake.style_preferences or "",
        intake.access_requirements or "",
    ]
    return " ".join(parts).lower()


def _score_archetype(arch: Archetype, text: str, has_genie_ref: bool) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    for kw in arch.keywords:
        if kw in text:
            score += 1.0
            reasons.append(f"keyword '{kw}'")
    # A concrete Genie reference strongly implies a Genie-centric archetype.
    if has_genie_ref and "genie" in arch.required_primitives:
        score += 2.0
        reasons.append("intake references a Genie space")
    return score, reasons


def _pick_target(arch: Archetype, text: str) -> tuple[str, str | None]:
    for hint in _APPKIT_HINTS:
        if hint in text:
            return TARGET_APPKIT, f"intake mentions '{hint}'"
    for hint in _PYTHON_HINTS:
        if hint in text:
            return TARGET_PYTHON, f"intake mentions '{hint}'"
    return arch.default_target, None


def classify_intake(
    intake: IntakeSpec, *, llm_client: object | None = None
) -> Classification:
    """Return the best-fit archetype + target for ``intake``.

    ``llm_client`` is accepted for future LLM-assisted refinement but is never
    required: the rule-based result is deterministic and offline-safe.
    """
    text = _intake_text(intake)
    has_genie_ref = bool(intake.existing_genies) or "genie" in text

    scored: list[tuple[str, float, list[str]]] = []
    for arch in ARCHETYPES.values():
        score, reasons = _score_archetype(arch, text, has_genie_ref)
        scored.append((arch.id, score, reasons))
    scored.sort(key=lambda item: item[1], reverse=True)

    best_id, best_score, best_reasons = scored[0]
    candidates = [(aid, score) for aid, score, _ in scored if score > 0][:3]

    if best_score < _CONFIDENCE_FLOOR:
        # Fall back to the safe default and flag for user confirmation.
        arch = default_archetype()
        target, _ = _pick_target(arch, text)
        return Classification(
            archetype_id=arch.id,
            target=target,
            score=best_score,
            rationale=(
                "No hubo señales claras del tipo de app; usando el arquetipo "
                f"por defecto ({arch.title}). Confirma o elige otro."
            ),
            candidates=candidates,
            needs_help=True,
        )

    arch = get_archetype(best_id) or default_archetype()
    target, target_reason = _pick_target(arch, text)
    rationale = f"{arch.title}: " + ", ".join(best_reasons[:4])
    if target_reason:
        rationale += f"; target {target} ({target_reason})"
    else:
        rationale += f"; target {target} (default del arquetipo)"
    return Classification(
        archetype_id=arch.id,
        target=target,
        score=best_score,
        rationale=rationale,
        candidates=candidates,
        needs_help=False,
    )

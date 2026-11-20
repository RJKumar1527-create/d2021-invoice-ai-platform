from typing import Any


ALLOWED_DECISIONS = {
    "SAFE TO PROGRESS",
    "HOLD FOR REVIEW",
    "QUERY SUPPLIER",
    "CORRECTION REQUIRED",
    "CREDIT / REBILL REQUIRED",
    "ESCALATE FOR INVESTIGATION",
}


def validate_investigation_output(
    deterministic_context: dict[str, Any],
    generated_output: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate AI-generated invoice investigation output.

    The deterministic assurance decision is authoritative.
    The AI may explain the decision but cannot replace,
    weaken, or contradict it.
    """
    authoritative_decision = str(
        deterministic_context.get(
            "business_decision",
            {},
        ).get(
            "recommended_decision",
            "",
        )
    ).strip().upper()

    if (
        authoritative_decision
        not in ALLOWED_DECISIONS
    ):
        raise ValueError(
            "The deterministic assurance decision "
            "is missing or invalid."
        )

    if not isinstance(
        generated_output,
        dict,
    ):
        generated_output = {}

    validated = dict(
        generated_output
    )

    generated_decision = str(
        validated.get(
            "recommended_decision",
            authoritative_decision,
        )
    ).strip().upper()

    if (
        generated_decision
        not in ALLOWED_DECISIONS
        or generated_decision
        != authoritative_decision
    ):
        generated_decision = (
            authoritative_decision
        )

    validated[
        "recommended_decision"
    ] = generated_decision

    validated.setdefault(
        "root_cause_summary",
        (
            "The available deterministic controls "
            "identified an invoice-assurance exception."
        ),
    )

    validated.setdefault(
        "financial_impact_summary",
        (
            "The financial impact is based on the "
            "available reconciliation and exposure evidence."
        ),
    )

    validated.setdefault(
        "control_evidence_summary",
        (
            "The decision is supported by validation, "
            "reconciliation, anomaly, and risk controls."
        ),
    )

    resolution_steps = validated.get(
        "resolution_steps",
        [],
    )

    if not isinstance(
        resolution_steps,
        list,
    ):
        resolution_steps = [
            str(resolution_steps)
        ]

    validated[
        "resolution_steps"
    ] = [
        str(step)
        for step in resolution_steps
        if str(step).strip()
    ]

    validated[
        "supplier_query_draft"
    ] = str(
        validated.get(
            "supplier_query_draft",
            "",
        )
        or ""
    )

    limitations = validated.get(
        "limitations",
        [],
    )

    if not isinstance(
        limitations,
        list,
    ):
        limitations = [
            str(limitations)
        ]

    validated["limitations"] = [
        str(item)
        for item in limitations
        if str(item).strip()
    ]

    validated[
        "decision_authority"
    ] = "Deterministic assurance controls"

    validated[
        "automatic_payment_approval"
    ] = False

    validated[
        "requires_authorized_business_action"
    ] = (
        authoritative_decision
        != "SAFE TO PROGRESS"
    )

    return validated
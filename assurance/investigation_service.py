import json
import os
import time
from typing import Any

from assurance.guardrails import (
    validate_investigation_output,
)


def clean_json(content: str) -> dict[str, Any]:
    cleaned = str(content or "").strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]

    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return json.loads(
        cleaned.strip()
    )


def build_investigation_context(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the only evidence that the AI may use.

    The deterministic decision and financial exposure
    remain authoritative.
    """
    return {
        "invoice": {
            "alias": invoice.get(
                "safe_invoice_alias"
            ),
            "invoice_type": invoice.get(
                "invoice_type"
            ),
            "billing_period_start": (
                invoice.get(
                    "billing_period_start"
                )
            ),
            "billing_period_end": (
                invoice.get(
                    "billing_period_end"
                )
            ),
            "invoice_value": invoice.get(
                "invoice_value"
            ),
        },
        "authoritative_decision": {
            "decision": invoice.get(
                "decision"
            ),
            "reason": invoice.get(
                "decision_reason"
            ),
            "priority": invoice.get(
                "priority"
            ),
            "exception_category": (
                invoice.get(
                    "exception_category"
                )
            ),
            "blocks_approval": bool(
                invoice.get(
                    "blocks_approval"
                )
            ),
            "requires_supplier_query": bool(
                invoice.get(
                    "requires_supplier_query"
                )
            ),
        },
        "financial_exposure": {
            "estimated_exposure": (
                invoice.get(
                    "estimated_exposure",
                    0,
                )
            ),
            "exposure_percentage": (
                invoice.get(
                    "exposure_percentage",
                    0,
                )
            ),
            "exposure_basis": invoice.get(
                "exposure_basis"
            ),
            "exposure_confidence": (
                invoice.get(
                    "exposure_confidence"
                )
            ),
        },
        "control_evidence": {
            "risk_score": invoice.get(
                "risk_score"
            ),
            "risk_level": invoice.get(
                "risk_level"
            ),
            "anomaly_score": invoice.get(
                "anomaly_score"
            ),
            "reconciliation_status": (
                invoice.get(
                    "reconciliation_status"
                )
            ),
            "reconciliation_variance": (
                invoice.get(
                    "reconciliation_variance"
                )
            ),
            "unusual_features": invoice.get(
                "unusual_features",
                [],
            ),
            "validation_findings": (
                invoice.get(
                    "validation_findings",
                    [],
                )
            ),
            "business_rule_citations": (
                invoice.get(
                    "rule_citations",
                    [],
                )
            ),
        },
        "required_actions": invoice.get(
            "recommended_actions",
            [],
        ),
    }


def build_messages(
    context: dict[str, Any],
) -> list[dict[str, str]]:
    system_prompt = """
You are an enterprise electricity-invoice assurance assistant.

Use only the supplied deterministic invoice controls and evidence.

The deterministic business decision is authoritative.
Never replace, weaken, or contradict that decision.

Return valid JSON with exactly these keys:

recommended_decision
root_cause_summary
financial_impact_summary
control_evidence_summary
resolution_steps
supplier_query_draft
limitations

Rules:

1. Do not invent tariff values, meter readings, supplier responses,
   customer information, MPAN values, or confirmation evidence.

2. Do not describe statistical exposure as a confirmed overcharge.

3. State whether the exposure is confirmed or estimated.

4. resolution_steps must be a list of practical business actions.

5. supplier_query_draft must be an empty string when the
   deterministic evidence does not require a supplier query.

6. Do not recommend automatic payment, production-data changes,
   or bypassing business approval.

7. Cite only business-rule identifiers supplied in the context.

8. Keep the response concise and understandable to a finance
   operations user.
""".strip()

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": json.dumps(
                context,
                indent=2,
                default=str,
            ),
        },
    ]


def deterministic_investigation(
    context: dict[str, Any],
) -> dict[str, Any]:
    decision = context[
        "authoritative_decision"
    ]

    exposure = context[
        "financial_exposure"
    ]

    controls = context[
        "control_evidence"
    ]

    exposure_type = (
        "confirmed"
        if exposure.get(
            "exposure_confidence"
        )
        == "HIGH"
        else "estimated"
    )

    amount = float(
        exposure.get(
            "estimated_exposure",
            0,
        )
        or 0
    )

    percentage = float(
        exposure.get(
            "exposure_percentage",
            0,
        )
        or 0
    )

    supplier_query_draft = ""

    if decision.get(
        "requires_supplier_query"
    ):
        supplier_query_draft = (
            "Please provide the source billing values, "
            "applicable tariff or rate, charge calculation, "
            "and supporting evidence for the identified "
            f"difference of {amount:.2f}. "
            "The invoice will remain on hold until the "
            "supporting evidence is reviewed."
        )

    evidence_summary = (
        f"Risk level: "
        f"{controls.get('risk_level', 'UNKNOWN')}; "
        f"reconciliation: "
        f"{controls.get('reconciliation_status', 'UNKNOWN')}; "
        f"anomaly score: "
        f"{controls.get('anomaly_score', 0)}."
    )

    return {
        "recommended_decision": (
            decision.get("decision")
        ),
        "root_cause_summary": (
            decision.get("reason")
        ),
        "financial_impact_summary": (
            f"The {exposure_type} financial exposure is "
            f"{amount:.2f}, representing "
            f"{percentage:.2f}% of the invoice value. "
            f"Basis: "
            f"{exposure.get('exposure_basis', '')}."
        ),
        "control_evidence_summary": (
            evidence_summary
        ),
        "resolution_steps": list(
            context.get(
                "required_actions",
                [],
            )
        ),
        "supplier_query_draft": (
            supplier_query_draft
        ),
        "limitations": [
            (
                "The assessment uses the available "
                "validation, reconciliation, anomaly, "
                "risk, and business-rule evidence."
            ),
            (
                "Approved tariff, meter, capacity, or "
                "supplier evidence may still be required."
            ),
        ],
    }


def generate_investigation_summary(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate a grounded investigation using provider failover.

    Provider order:
        Groq -> OpenRouter -> deterministic fallback
    """
    started_at = time.perf_counter()

    context = build_investigation_context(
        invoice
    )

    messages = build_messages(
        context
    )

    provider_errors = []

    result = None
    provider = None
    model = None

    groq_key = os.getenv(
        "GROQ_API_KEY",
        "",
    )

    groq_model = os.getenv(
        "GROQ_CHAT_MODEL",
        "openai/gpt-oss-20b",
    )

    if groq_key:
        try:
            from groq import Groq

            client = Groq(
                api_key=groq_key,
                timeout=45,
                max_retries=1,
            )

            response = (
                client.chat.completions.create(
                    model=groq_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1600,
                    response_format={
                        "type": "json_object"
                    },
                )
            )

            result = clean_json(
                response.choices[
                    0
                ].message.content
            )

            provider = "Groq"
            model = groq_model

        except Exception as error:
            provider_errors.append(
                f"Groq: {error}"
            )

    openrouter_key = os.getenv(
        "OPENROUTER_API_KEY",
        "",
    )

    openrouter_model = os.getenv(
        "OPENROUTER_CHAT_MODEL",
        "openai/gpt-oss-20b",
    )

    if (
        result is None
        and openrouter_key
    ):
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=openrouter_key,
                base_url=(
                    "https://openrouter.ai/api/v1"
                ),
                timeout=60,
                max_retries=1,
            )

            response = (
                client.chat.completions.create(
                    model=openrouter_model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1600,
                    response_format={
                        "type": "json_object"
                    },
                )
            )

            result = clean_json(
                response.choices[
                    0
                ].message.content
            )

            provider = "OpenRouter"
            model = openrouter_model

        except Exception as error:
            provider_errors.append(
                f"OpenRouter: {error}"
            )

    if result is None:
        result = deterministic_investigation(
            context
        )

        provider = "Deterministic"
        model = "Assurance evidence fallback"

    result = validate_investigation_output(
        deterministic_context={
            "business_decision": {
                "recommended_decision": (
                    context[
                        "authoritative_decision"
                    ][
                        "decision"
                    ]
                )
            }
        },
        generated_output=result,
    )

    return {
        "investigation": result,
        "_internal": {
            "provider": provider,
            "model": model,
            "provider_errors": (
                provider_errors
            ),
            "latency_ms": round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                2,
            ),
        },
    }
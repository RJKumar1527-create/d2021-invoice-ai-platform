from assurance.investigation_service import (
    build_investigation_context,
    deterministic_investigation,
    generate_investigation_summary,
)


def sample_invoice():
    return {
        "run_id": "RUN-SYNTHETIC",
        "invoice_number": (
            "SYNTH-INV-002"
        ),
        "safe_invoice_alias": (
            "INV-00002"
        ),
        "invoice_type": "N",
        "billing_period_start": (
            "2026-10-01"
        ),
        "billing_period_end": (
            "2026-10-31"
        ),
        "invoice_value": 15000,
        "estimated_exposure": 7000,
        "exposure_percentage": 46.67,
        "exposure_basis": (
            "Statistical expected-value "
            "difference"
        ),
        "exposure_confidence": "MEDIUM",
        "decision": "QUERY SUPPLIER",
        "decision_reason": (
            "A supplier-controlled charge "
            "requires supporting evidence."
        ),
        "priority": "CRITICAL",
        "exception_category": (
            "Supplier Charge"
        ),
        "blocks_approval": True,
        "requires_supplier_query": True,
        "risk_score": 88,
        "risk_level": "HIGH",
        "anomaly_score": 90,
        "reconciliation_status": (
            "MATCHED"
        ),
        "reconciliation_variance": 0,
        "unusual_features": [
            (
                "Reactive Amount above "
                "99th percentile"
            )
        ],
        "validation_findings": [],
        "rule_citations": [
            "RULE-SYNTH-001"
        ],
        "recommended_actions": [
            "Verify supporting evidence.",
            "Raise a supplier query.",
        ],
    }


def test_context_preserves_authoritative_decision():
    context = build_investigation_context(
        sample_invoice()
    )

    assert (
        context[
            "authoritative_decision"
        ][
            "decision"
        ]
        == "QUERY SUPPLIER"
    )

    assert (
        context[
            "authoritative_decision"
        ][
            "blocks_approval"
        ]
        is True
    )


def test_deterministic_investigation():
    context = build_investigation_context(
        sample_invoice()
    )

    result = deterministic_investigation(
        context
    )

    assert (
        result[
            "recommended_decision"
        ]
        == "QUERY SUPPLIER"
    )

    assert (
        "estimated"
        in result[
            "financial_impact_summary"
        ].lower()
    )

    assert (
        result["supplier_query_draft"]
    )


def test_investigation_cannot_approve_invoice(
    monkeypatch,
):
    monkeypatch.delenv(
        "GROQ_API_KEY",
        raising=False,
    )

    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    result = generate_investigation_summary(
        sample_invoice()
    )

    investigation = result[
        "investigation"
    ]

    assert (
        investigation[
            "recommended_decision"
        ]
        == "QUERY SUPPLIER"
    )

    assert (
        investigation[
            "automatic_payment_approval"
        ]
        is False
    )

    assert (
        investigation[
            "decision_authority"
        ]
        == "Deterministic assurance controls"
    )


def test_supplier_query_not_generated_when_not_required():
    invoice = sample_invoice()

    invoice["decision"] = (
        "HOLD FOR REVIEW"
    )

    invoice[
        "requires_supplier_query"
    ] = False

    context = build_investigation_context(
        invoice
    )

    result = deterministic_investigation(
        context
    )

    assert (
        result["supplier_query_draft"]
        == ""
    )
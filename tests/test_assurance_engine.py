from assurance.decisions import (
    ESCALATE_INVESTIGATION,
    HOLD_FOR_REVIEW,
    QUERY_SUPPLIER,
    SAFE_TO_PROGRESS,
)
from assurance.exposure import (
    calculate_financial_exposure,
)
from assurance.models import (
    InvoiceAssuranceInput,
)
from assurance.processor import (
    build_cleared_invoice_register,
    build_daily_summary,
    build_exception_queue,
    process_daily_run,
)


def create_invoice(
    alias: str,
    invoice_value: float = 10000,
    risk_level: str = "LOW",
    anomaly_score: float = 10,
    risk_score: float = 10,
    model_result: str = "NORMAL",
    variance: float = 0,
    reconciliation_status: str = "MATCHED",
    unusual_features: list[str] | None = None,
    billed_charge_amount: float | None = None,
    robust_expected_amount: float | None = None,
) -> InvoiceAssuranceInput:
    return InvoiceAssuranceInput(
        invoice_number=alias,
        safe_invoice_alias=alias,
        source_file="synthetic_daily.uff",
        invoice_type="N",
        billing_period_start="2026-10-01",
        billing_period_end="2026-10-31",
        invoice_net_amount=invoice_value,
        reconciliation_variance=variance,
        anomaly_score=anomaly_score,
        risk_score=risk_score,
        risk_level=risk_level,
        critical_validation_failures=0,
        validation_warnings=0,
        reconciliation_status=(
            reconciliation_status
        ),
        model_result=model_result,
        unusual_features=(
            unusual_features or []
        ),
        billed_charge_amount=(
            billed_charge_amount
        ),
        robust_expected_amount=(
            robust_expected_amount
        ),
    )


def test_safe_invoice_progresses():
    invoice = create_invoice(
        alias="INV-00001",
    )

    run = process_daily_run(
        source_files=[
            "synthetic_daily.uff"
        ],
        invoices=[invoice],
    )

    result = run.invoices[0]

    assert (
        result.decision.decision
        == SAFE_TO_PROGRESS
    )

    assert (
        result.assurance_status
        == "CLEARED"
    )

    assert (
        result.decision.blocks_approval
        is False
    )


def test_supplier_charge_generates_query():
    invoice = create_invoice(
        alias="INV-00002",
        invoice_value=15000,
        risk_level="HIGH",
        anomaly_score=90,
        risk_score=88,
        model_result="ANOMALY",
        unusual_features=[
            (
                "Reactive Amount above "
                "99th percentile"
            )
        ],
        billed_charge_amount=15000,
        robust_expected_amount=8000,
    )

    run = process_daily_run(
        source_files=[
            "synthetic_daily.uff"
        ],
        invoices=[invoice],
    )

    result = run.invoices[0]

    assert (
        result.decision.decision
        == QUERY_SUPPLIER
    )

    assert (
        result.exposure
        .estimated_exposure
        == 7000
    )

    assert (
        result.exposure
        .exposure_confidence
        == "MEDIUM"
    )

    assert (
        result.decision
        .requires_supplier_query
        is True
    )

    assert (
        result.decision.blocks_approval
        is True
    )


def test_reconciliation_variance_is_confirmed_exposure():
    invoice = create_invoice(
        alias="INV-00003",
        risk_level="CRITICAL",
        anomaly_score=70,
        risk_score=75,
        model_result="ANOMALY",
        variance=2500,
        reconciliation_status="MISMATCHED",
    )

    exposure = (
        calculate_financial_exposure(
            invoice
        )
    )

    assert (
        exposure.confirmed_variance
        == 2500
    )

    assert (
        exposure.estimated_exposure
        == 2500
    )

    assert (
        exposure.exposure_confidence
        == "HIGH"
    )


def test_reconciliation_failure_is_escalated():
    invoice = create_invoice(
        alias="INV-00004",
        risk_level="CRITICAL",
        anomaly_score=75,
        risk_score=82,
        model_result="ANOMALY",
        variance=3000,
        reconciliation_status="MISMATCHED",
    )

    run = process_daily_run(
        source_files=[
            "synthetic_daily.uff"
        ],
        invoices=[invoice],
    )

    result = run.invoices[0]

    assert (
        result.decision.decision
        == ESCALATE_INVESTIGATION
    )

    assert (
        result.decision
        .exception_category
        == "Reconciliation"
    )

    assert (
        result.decision.blocks_approval
        is True
    )


def test_medium_anomaly_is_held():
    invoice = create_invoice(
        alias="INV-00005",
        risk_level="MEDIUM",
        anomaly_score=70,
        risk_score=45,
        model_result="ANOMALY",
    )

    run = process_daily_run(
        source_files=[
            "synthetic_daily.uff"
        ],
        invoices=[invoice],
    )

    result = run.invoices[0]

    assert (
        result.decision.decision
        == HOLD_FOR_REVIEW
    )

    assert (
        result.decision.priority
        == "MEDIUM"
    )

    assert (
        result.decision
        .requires_human_review
        is True
    )


def test_daily_summary():
    invoices = [
        create_invoice(
            alias="INV-00001",
            invoice_value=10000,
        ),
        create_invoice(
            alias="INV-00002",
            invoice_value=15000,
            risk_level="HIGH",
            anomaly_score=90,
            risk_score=88,
            model_result="ANOMALY",
            unusual_features=[
                (
                    "Reactive Amount above "
                    "normal range"
                )
            ],
            billed_charge_amount=15000,
            robust_expected_amount=8000,
        ),
    ]

    run = process_daily_run(
        source_files=[
            "daily_001.uff"
        ],
        invoices=invoices,
    )

    summary = build_daily_summary(
        run
    )

    assert (
        summary["total_invoices"]
        == 2
    )

    assert (
        summary["total_invoice_value"]
        == 25000
    )

    assert (
        summary["safe_to_progress"]
        == 1
    )

    assert summary["exceptions"] == 1

    assert (
        summary["held_invoice_value"]
        == 15000
    )

    assert (
        summary[
            "estimated_financial_exposure"
        ]
        == 7000
    )

    assert (
        summary[
            "supplier_queries_required"
        ]
        == 1
    )


def test_exception_queue_is_prioritized():
    medium_exception = create_invoice(
        alias="INV-00006",
        invoice_value=5000,
        risk_level="MEDIUM",
        anomaly_score=65,
        risk_score=40,
        model_result="ANOMALY",
    )

    critical_exception = create_invoice(
        alias="INV-00007",
        invoice_value=20000,
        risk_level="HIGH",
        anomaly_score=95,
        risk_score=92,
        model_result="ANOMALY",
        unusual_features=[
            (
                "Capacity charge above "
                "normal range"
            )
        ],
        billed_charge_amount=20000,
        robust_expected_amount=10000,
    )

    run = process_daily_run(
        source_files=[
            "daily_002.uff"
        ],
        invoices=[
            medium_exception,
            critical_exception,
        ],
    )

    queue = build_exception_queue(
        run
    )

    assert len(queue) == 2

    assert (
        queue[0]["safe_invoice_alias"]
        == "INV-00007"
    )

    assert (
        queue[0][
            "recommended_decision"
        ]
        == QUERY_SUPPLIER
    )

    assert (
        queue[0][
            "estimated_exposure"
        ]
        == 10000
    )

    assert (
        queue[0]["priority"]
        == "CRITICAL"
    )


def test_cleared_invoice_register():
    safe_invoice = create_invoice(
        alias="INV-00008",
    )

    exception_invoice = create_invoice(
        alias="INV-00009",
        risk_level="MEDIUM",
        anomaly_score=70,
        risk_score=45,
        model_result="ANOMALY",
    )

    run = process_daily_run(
        source_files=[
            "daily_003.uff"
        ],
        invoices=[
            safe_invoice,
            exception_invoice,
        ],
    )

    cleared = (
        build_cleared_invoice_register(
            run
        )
    )

    assert len(cleared) == 1

    assert (
        cleared[0][
            "safe_invoice_alias"
        ]
        == "INV-00008"
    )

    assert (
        cleared[0]["decision"]
        == SAFE_TO_PROGRESS
    )


def test_daily_run_requires_source_file():
    invoice = create_invoice(
        alias="INV-00010",
    )

    try:
        process_daily_run(
            source_files=[],
            invoices=[invoice],
        )

        assert False

    except ValueError as error:
        assert (
            "source file"
            in str(error).lower()
        )


def test_daily_run_requires_invoice():
    try:
        process_daily_run(
            source_files=[
                "daily_004.uff"
            ],
            invoices=[],
        )

        assert False

    except ValueError as error:
        assert (
            "invoice"
            in str(error).lower()
        )
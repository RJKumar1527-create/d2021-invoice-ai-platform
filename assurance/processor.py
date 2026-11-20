from collections import Counter
from typing import Any

from assurance.decisions import (
    SAFE_TO_PROGRESS,
    recommend_decision,
)
from assurance.exposure import (
    calculate_financial_exposure,
)
from assurance.models import (
    AssuredInvoice,
    DailyProcessingRun,
    InvoiceAssuranceInput,
)


PRIORITY_ORDER = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


def process_invoice(
    processing_run_id: str,
    invoice: InvoiceAssuranceInput,
) -> AssuredInvoice:
    """
    Calculate financial exposure and recommend a business
    decision for one invoice.
    """
    exposure = (
        calculate_financial_exposure(
            invoice
        )
    )

    decision = recommend_decision(
        invoice,
        exposure,
    )

    assurance_status = (
        "CLEARED"
        if decision.decision
        == SAFE_TO_PROGRESS
        else "EXCEPTION"
    )

    return AssuredInvoice(
        processing_run_id=(
            processing_run_id
        ),
        invoice=invoice,
        exposure=exposure,
        decision=decision,
        assurance_status=(
            assurance_status
        ),
    )


def process_daily_run(
    source_files: list[str],
    invoices: list[
        InvoiceAssuranceInput
    ],
) -> DailyProcessingRun:
    """
    Process all invoices received within one daily run.
    """
    if not source_files:
        raise ValueError(
            "At least one source file is required."
        )

    if not invoices:
        raise ValueError(
            "At least one invoice is required."
        )

    run = DailyProcessingRun.create(
        source_files=source_files
    )

    run.invoices = [
        process_invoice(
            processing_run_id=run.run_id,
            invoice=invoice,
        )
        for invoice in invoices
    ]

    run.complete()

    return run


def build_daily_summary(
    run: DailyProcessingRun,
) -> dict[str, Any]:
    """
    Create business-facing metrics for a daily assurance run.
    """
    total_invoices = len(
        run.invoices
    )

    total_invoice_value = round(
        sum(
            abs(
                float(
                    item.invoice
                    .invoice_net_amount
                    or 0.0
                )
            )
            for item in run.invoices
        ),
        2,
    )

    safe_to_progress = sum(
        item.assurance_status
        == "CLEARED"
        for item in run.invoices
    )

    exception_count = sum(
        item.assurance_status
        == "EXCEPTION"
        for item in run.invoices
    )

    supplier_queries_required = sum(
        item.decision
        .requires_supplier_query
        for item in run.invoices
    )

    held_invoice_value = round(
        sum(
            abs(
                float(
                    item.invoice
                    .invoice_net_amount
                    or 0.0
                )
            )
            for item in run.invoices
            if item.decision.blocks_approval
        ),
        2,
    )

    estimated_financial_exposure = round(
        sum(
            float(
                item.exposure
                .estimated_exposure
                or 0.0
            )
            for item in run.invoices
            if item.decision.blocks_approval
        ),
        2,
    )

    critical_exceptions = sum(
        item.decision.priority
        == "CRITICAL"
        for item in run.invoices
    )

    high_priority_exceptions = sum(
        item.decision.priority
        == "HIGH"
        for item in run.invoices
    )

    decision_counts = Counter(
        item.decision.decision
        for item in run.invoices
    )

    priority_counts = Counter(
        item.decision.priority
        for item in run.invoices
    )

    category_counts = Counter(
        item.decision
        .exception_category
        for item in run.invoices
        if item.assurance_status
        == "EXCEPTION"
    )

    exception_rate = (
        exception_count
        / total_invoices
        * 100
        if total_invoices
        else 0.0
    )

    clearance_rate = (
        safe_to_progress
        / total_invoices
        * 100
        if total_invoices
        else 0.0
    )

    exposure_rate = (
        estimated_financial_exposure
        / total_invoice_value
        * 100
        if total_invoice_value
        else 0.0
    )

    return {
        "run_id": run.run_id,
        "run_date": run.run_date,
        "run_status": run.status,
        "file_count": len(
            run.source_files
        ),
        "source_files": list(
            run.source_files
        ),
        "total_invoices": (
            total_invoices
        ),
        "total_invoice_value": (
            total_invoice_value
        ),
        "safe_to_progress": (
            safe_to_progress
        ),
        "exceptions": exception_count,
        "clearance_rate": round(
            clearance_rate,
            2,
        ),
        "exception_rate": round(
            exception_rate,
            2,
        ),
        "held_invoice_value": (
            held_invoice_value
        ),
        "estimated_financial_exposure": (
            estimated_financial_exposure
        ),
        "exposure_rate": round(
            exposure_rate,
            2,
        ),
        "supplier_queries_required": (
            supplier_queries_required
        ),
        "critical_exceptions": (
            critical_exceptions
        ),
        "high_priority_exceptions": (
            high_priority_exceptions
        ),
        "decision_counts": dict(
            decision_counts
        ),
        "priority_counts": dict(
            priority_counts
        ),
        "exception_category_counts": dict(
            category_counts
        ),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def exception_sort_key(
    item: AssuredInvoice,
) -> tuple[int, float, float]:
    """
    Sort exceptions by priority, estimated financial exposure,
    and risk score.
    """
    priority_score = (
        PRIORITY_ORDER.get(
            item.decision.priority,
            0,
        )
    )

    return (
        priority_score,
        float(
            item.exposure
            .estimated_exposure
            or 0.0
        ),
        float(
            item.invoice.risk_score
            or 0.0
        ),
    )


def build_exception_queue(
    run: DailyProcessingRun,
) -> list[dict[str, Any]]:
    """
    Create a prioritized business queue containing only
    invoices that require action.
    """
    exceptions = [
        item
        for item in run.invoices
        if item.assurance_status
        == "EXCEPTION"
    ]

    exceptions.sort(
        key=exception_sort_key,
        reverse=True,
    )

    return [
        {
            "run_id": (
                item.processing_run_id
            ),
            "invoice_number": (
                item.invoice
                .invoice_number
            ),
            "safe_invoice_alias": (
                item.invoice
                .safe_invoice_alias
            ),
            "source_file": (
                item.invoice.source_file
            ),
            "invoice_type": (
                item.invoice.invoice_type
            ),
            "billing_period_start": (
                item.invoice
                .billing_period_start
            ),
            "billing_period_end": (
                item.invoice
                .billing_period_end
            ),
            "billing_period": (
                f"{item.invoice.billing_period_start}"
                f" to "
                f"{item.invoice.billing_period_end}"
            ),
            "invoice_value": (
                item.invoice
                .invoice_net_amount
            ),
            "estimated_exposure": (
                item.exposure
                .estimated_exposure
            ),
            "exposure_percentage": (
                item.exposure
                .exposure_percentage
            ),
            "exposure_basis": (
                item.exposure
                .exposure_basis
            ),
            "exposure_confidence": (
                item.exposure
                .exposure_confidence
            ),
            "risk_score": (
                item.invoice.risk_score
            ),
            "risk_level": (
                item.invoice.risk_level
            ),
            "anomaly_score": (
                item.invoice.anomaly_score
            ),
            "reconciliation_status": (
                item.invoice
                .reconciliation_status
            ),
            "reconciliation_variance": (
                item.invoice
                .reconciliation_variance
            ),
            "exception_category": (
                item.decision
                .exception_category
            ),
            "recommended_decision": (
                item.decision.decision
            ),
            "decision_reason": (
                item.decision
                .decision_reason
            ),
            "recommended_actions": list(
                item.decision
                .recommended_actions
            ),
            "priority": (
                item.decision.priority
            ),
            "requires_human_review": (
                item.decision
                .requires_human_review
            ),
            "supplier_query_required": (
                item.decision
                .requires_supplier_query
            ),
            "blocks_approval": (
                item.decision
                .blocks_approval
            ),
            "unusual_features": list(
                item.invoice
                .unusual_features
            ),
            "validation_findings": list(
                item.invoice
                .validation_findings
            ),
            "rule_citations": list(
                item.invoice
                .rule_citations
            ),
            "workflow_status": "NEW",
            "owner": "",
            "due_date": "",
        }
        for item in exceptions
    ]


def build_cleared_invoice_register(
    run: DailyProcessingRun,
) -> list[dict[str, Any]]:
    """
    Create the register of invoices that passed assurance
    and may progress through the normal business process.
    """
    cleared = [
        item
        for item in run.invoices
        if item.assurance_status
        == "CLEARED"
    ]

    return [
        {
            "run_id": (
                item.processing_run_id
            ),
            "invoice_number": (
                item.invoice
                .invoice_number
            ),
            "safe_invoice_alias": (
                item.invoice
                .safe_invoice_alias
            ),
            "source_file": (
                item.invoice.source_file
            ),
            "billing_period": (
                f"{item.invoice.billing_period_start}"
                f" to "
                f"{item.invoice.billing_period_end}"
            ),
            "invoice_value": (
                item.invoice
                .invoice_net_amount
            ),
            "risk_level": (
                item.invoice.risk_level
            ),
            "reconciliation_status": (
                item.invoice
                .reconciliation_status
            ),
            "estimated_exposure": (
                item.exposure
                .estimated_exposure
            ),
            "decision": (
                item.decision.decision
            ),
            "decision_reason": (
                item.decision
                .decision_reason
            ),
            "assurance_status": (
                item.assurance_status
            ),
        }
        for item in cleared
    ]
from typing import Any

from assurance.adapters import (
    adapt_assurance_inputs,
    diagnose_adapter_coverage,
)
from assurance.processor import (
    build_cleared_invoice_register,
    build_daily_summary,
    build_exception_queue,
    process_daily_run,
)
from assurance.repository import (
    save_processing_run,
)


def run_daily_assurance(
    parsed_data: dict[str, Any],
    validation_results: Any = None,
    reconciliation_results: Any = None,
    anomaly_results: Any = None,
    risk_results: Any = None,
    rule_results: Any = None,
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    source_files = (
        source_files
        or ["UNKNOWN_SOURCE"]
    )

    assurance_inputs = (
        adapt_assurance_inputs(
            parsed_data=parsed_data,
            validation_results=(
                validation_results
            ),
            reconciliation_results=(
                reconciliation_results
            ),
            anomaly_results=(
                anomaly_results
            ),
            risk_results=risk_results,
            rule_results=rule_results,
            source_file=source_files[0],
        )
    )

    if not assurance_inputs:
        raise ValueError(
            "No invoice records were available "
            "for assurance processing."
        )

    run = process_daily_run(
        source_files=source_files,
        invoices=assurance_inputs,
    )

    summary = build_daily_summary(
        run
    )

    exception_queue = (
        build_exception_queue(run)
    )

    cleared_register = (
        build_cleared_invoice_register(
            run
        )
    )

    adapter_coverage = (
        diagnose_adapter_coverage(
            assurance_inputs
        )
    )

    save_processing_run(
        run=run,
        summary=summary,
    )

    return {
        "processing_run": run.to_dict(),
        "summary": summary,
        "exception_queue": (
            exception_queue
        ),
        "cleared_invoice_register": (
            cleared_register
        ),
        "adapter_coverage": (
            adapter_coverage
        ),
    }


def run_synthetic_demo():
    parsed_data = {
        "invoices": [
            {
                "invoice_number": (
                    "SYNTH-INV-001"
                ),
                "safe_invoice_alias": (
                    "INV-00001"
                ),
                "invoice_type": "N",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "final_net": 10000,
            },
            {
                "invoice_number": (
                    "SYNTH-INV-002"
                ),
                "safe_invoice_alias": (
                    "INV-00002"
                ),
                "invoice_type": "N",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "final_net": 15000,
            },
            {
                "invoice_number": (
                    "SYNTH-INV-003"
                ),
                "safe_invoice_alias": (
                    "INV-00003"
                ),
                "invoice_type": "N",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "final_net": 20000,
            },
        ]
    }

    reconciliation_results = [
        {
            "invoice_number": (
                "SYNTH-INV-001"
            ),
            "status": "MATCHED",
            "variance": 0,
        },
        {
            "invoice_number": (
                "SYNTH-INV-002"
            ),
            "status": "MATCHED",
            "variance": 0,
        },
        {
            "invoice_number": (
                "SYNTH-INV-003"
            ),
            "status": "MISMATCHED",
            "variance": 3500,
        },
    ]

    anomaly_results = [
        {
            "invoice_number": (
                "SYNTH-INV-001"
            ),
            "anomaly_score": 10,
            "model_result": "NORMAL",
        },
        {
            "invoice_number": (
                "SYNTH-INV-002"
            ),
            "anomaly_score": 90,
            "model_result": "ANOMALY",
            "unusual_features": [
                (
                    "Reactive Amount above "
                    "99th percentile"
                )
            ],
            "billed_charge_amount": 15000,
            "robust_expected_amount": 8000,
        },
        {
            "invoice_number": (
                "SYNTH-INV-003"
            ),
            "anomaly_score": 80,
            "model_result": "ANOMALY",
        },
    ]

    risk_results = [
        {
            "invoice_number": (
                "SYNTH-INV-001"
            ),
            "risk_score": 10,
            "risk_level": "LOW",
        },
        {
            "invoice_number": (
                "SYNTH-INV-002"
            ),
            "risk_score": 88,
            "risk_level": "HIGH",
        },
        {
            "invoice_number": (
                "SYNTH-INV-003"
            ),
            "risk_score": 91,
            "risk_level": "CRITICAL",
        },
    ]

    return run_daily_assurance(
        parsed_data=parsed_data,
        reconciliation_results=(
            reconciliation_results
        ),
        anomaly_results=(
            anomaly_results
        ),
        risk_results=risk_results,
        source_files=[
            "synthetic_daily_demo.txt"
        ],
    )
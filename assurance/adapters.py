from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from assurance.models import (
    InvoiceAssuranceInput,
)


def first_value(
    source: Any,
    names: Iterable[str],
    default: Any = None,
) -> Any:
    """
    Return the first populated value from a dictionary.

    Lists and tuples are returned directly because pipeline
    result collections may already be supplied as lists.
    """
    if source is None:
        return default

    if isinstance(
        source,
        (list, tuple),
    ):
        return source

    if not isinstance(source, dict):
        return default

    for name in names:
        value = source.get(name)

        if value is not None and value != "":
            return value

    return default


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value is None or value == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None or value == "":
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def normalize_invoice_reference(
    record: dict[str, Any],
) -> str:
    return str(
        first_value(
            record,
            [
                "invoice_number",
                "invoice_reference",
                "invoice_no",
                "invoice_id",
                "reference",
                "safe_invoice_alias",
            ],
            "",
        )
    ).strip()


def create_lookup(
    records: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    lookup = {}

    for record in safe_list(records):
        if not isinstance(record, dict):
            continue

        invoice_reference = (
            normalize_invoice_reference(record)
        )

        if invoice_reference:
            lookup[invoice_reference] = record

    return lookup


def extract_validation_findings(
    invoice_reference: str,
    validation_results: Any,
) -> list[dict[str, Any]]:
    findings = []

    if isinstance(validation_results, dict):
        possible_records = first_value(
            validation_results,
            [
                "results",
                "invoices",
                "validation_results",
                "findings",
                "issues",
            ],
            [],
        )

    else:
        possible_records = validation_results

    for record in safe_list(possible_records):
        if not isinstance(record, dict):
            continue

        record_reference = (
            normalize_invoice_reference(record)
        )

        if (
            record_reference
            and record_reference
            != invoice_reference
        ):
            continue

        nested_findings = first_value(
            record,
            [
                "findings",
                "issues",
                "validation_findings",
                "errors",
                "warnings",
            ],
            None,
        )

        if nested_findings is not None:
            for nested in safe_list(
                nested_findings
            ):
                if isinstance(nested, dict):
                    findings.append(nested)
                else:
                    findings.append(
                        {
                            "severity": "WARNING",
                            "message": str(nested),
                        }
                    )

        elif any(
            key in record
            for key in [
                "message",
                "rule",
                "severity",
                "status",
            ]
        ):
            findings.append(record)

    return findings


def create_validation_findings_lookup(
    validation_results: Any,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
]:
    """
    Index validation findings once per processing run.

    Referenced findings are stored by invoice number.
    Findings without an invoice reference are retained as
    global findings and applied to every invoice, preserving
    the previous adapter behavior.
    """
    if isinstance(
        validation_results,
        dict,
    ):
        possible_records = first_value(
            validation_results,
            [
                "results",
                "invoices",
                "validation_results",
                "findings",
                "issues",
            ],
            [],
        )

    else:
        possible_records = validation_results

    findings_by_invoice = {}
    global_findings = []

    for record in safe_list(
        possible_records
    ):
        if not isinstance(
            record,
            dict,
        ):
            continue

        record_reference = (
            normalize_invoice_reference(
                record
            )
        )

        extracted = (
            extract_validation_findings(
                record_reference,
                [record],
            )
        )

        if not extracted:
            continue

        if record_reference:
            findings_by_invoice.setdefault(
                record_reference,
                [],
            ).extend(
                extracted
            )

        else:
            global_findings.extend(
                extracted
            )

    return (
        findings_by_invoice,
        global_findings,
    )


def count_validation_findings(
    findings: list[dict[str, Any]],
) -> tuple[int, int]:
    critical_count = 0
    warning_count = 0

    for finding in findings:
        severity = str(
            first_value(
                finding,
                [
                    "severity",
                    "level",
                    "risk_level",
                    "status",
                ],
                "WARNING",
            )
        ).upper()

        if severity in {
            "CRITICAL",
            "ERROR",
            "FAILED",
            "FAIL",
            "HIGH",
        }:
            critical_count += 1

        else:
            warning_count += 1

    return critical_count, warning_count


def extract_unusual_features(
    anomaly_record: dict[str, Any],
) -> list[str]:
    values = first_value(
        anomaly_record,
        [
            "unusual_features",
            "anomaly_reasons",
            "reasons",
            "drivers",
            "explanations",
            "anomaly_features",
        ],
        [],
    )

    output = []

    for value in safe_list(values):
        if isinstance(value, dict):
            output.append(
                str(
                    first_value(
                        value,
                        [
                            "feature",
                            "message",
                            "reason",
                            "description",
                        ],
                        value,
                    )
                )
            )
        else:
            output.append(str(value))

    return output


def resolve_invoice_records(
    parsed_data: dict[str, Any],
) -> list[dict[str, Any]]:
    invoices = first_value(
        parsed_data,
        [
            "invoices",
            "invoice_records",
            "bcd_records",
        ],
        [],
    )

    return [
        invoice
        for invoice in safe_list(invoices)
        if isinstance(invoice, dict)
    ]


def adapt_assurance_inputs(
    parsed_data: dict[str, Any],
    validation_results: Any = None,
    reconciliation_results: Any = None,
    anomaly_results: Any = None,
    risk_results: Any = None,
    rule_results: Any = None,
    source_file: str = "UNKNOWN",
) -> list[InvoiceAssuranceInput]:
    """
    Convert existing Project 1 processing outputs into
    business-facing assurance inputs.

    The adapter accepts multiple possible field names because
    the original workflow pages use different result schemas.
    """

    (
        validation_findings_lookup,
        global_validation_findings,
    ) = create_validation_findings_lookup(
        validation_results
    )

    reconciliation_lookup = create_lookup(
        first_value(
            reconciliation_results,
            [
                "results",
                "invoices",
                "reconciliation_results",
            ],
            reconciliation_results
            if isinstance(
                reconciliation_results,
                list,
            )
            else [],
        )
        if reconciliation_results
        is not None
        else []
    )

    anomaly_lookup = create_lookup(
        first_value(
            anomaly_results,
            [
                "results",
                "invoices",
                "anomaly_results",
            ],
            anomaly_results
            if isinstance(
                anomaly_results,
                list,
            )
            else [],
        )
        if anomaly_results
        is not None
        else []
    )

    risk_lookup = create_lookup(
        first_value(
            risk_results,
            [
                "results",
                "invoices",
                "risk_results",
            ],
            risk_results
            if isinstance(
                risk_results,
                list,
            )
            else [],
        )
        if risk_results
        is not None
        else []
    )

    rule_lookup = create_lookup(
        first_value(
            rule_results,
            [
                "results",
                "invoices",
                "rule_results",
            ],
            rule_results
            if isinstance(
                rule_results,
                list,
            )
            else [],
        )
        if rule_results
        is not None
        else []
    )

    adapted = []

    for index, invoice in enumerate(
        resolve_invoice_records(parsed_data),
        start=1,
    ):
        invoice_reference = (
            normalize_invoice_reference(
                invoice
            )
            or f"INTERNAL-{index:05d}"
        )

        safe_alias = str(
            first_value(
                invoice,
                [
                    "safe_invoice_alias",
                    "masked_invoice_number",
                    "invoice_alias",
                ],
                f"INV-{index:05d}",
            )
        )

        reconciliation = (
            reconciliation_lookup.get(
                invoice_reference,
                {},
            )
        )

        anomaly = anomaly_lookup.get(
            invoice_reference,
            {},
        )

        risk = risk_lookup.get(
            invoice_reference,
            {},
        )

        rules = rule_lookup.get(
            invoice_reference,
            {},
        )

        findings = list(
            global_validation_findings
        )

        findings.extend(
            validation_findings_lookup.get(
                invoice_reference,
                [],
            )
        )

        (
            critical_failures,
            validation_warnings,
        ) = count_validation_findings(
            findings
        )

        reconciliation_variance = (
            safe_float(
                first_value(
                    reconciliation,
                    [
                        "variance",
                        "absolute_variance",
                        "difference",
                        "reconciliation_variance",
                        "net_variance",
                    ],
                    0,
                )
            )
        )

        reconciliation_status = str(
            first_value(
                reconciliation,
                [
                    "status",
                    "reconciliation_status",
                    "result",
                ],
                (
                    "MATCHED"
                    if abs(
                        reconciliation_variance
                    )
                    < 0.01
                    else "MISMATCHED"
                ),
            )
        ).upper()

        anomaly_score = safe_float(
            first_value(
                anomaly,
                [
                    "anomaly_score",
                    "score",
                    "ml_score",
                    "risk_score",
                ],
                0,
            )
        )

        model_result = str(
            first_value(
                anomaly,
                [
                    "model_result",
                    "prediction",
                    "anomaly_result",
                    "classification",
                ],
                (
                    "ANOMALY"
                    if anomaly_score >= 60
                    else "NORMAL"
                ),
            )
        ).upper()

        risk_score = safe_float(
            first_value(
                risk,
                [
                    "risk_score",
                    "score",
                    "final_risk_score",
                ],
                anomaly_score,
            )
        )

        risk_level = str(
            first_value(
                risk,
                [
                    "risk_level",
                    "level",
                    "final_risk_level",
                ],
                (
                    "CRITICAL"
                    if risk_score >= 75
                    else "HIGH"
                    if risk_score >= 50
                    else "MEDIUM"
                    if risk_score >= 25
                    else "LOW"
                ),
            )
        ).upper()

        rule_citations = safe_list(
            first_value(
                rules,
                [
                    "rule_citations",
                    "citations",
                    "rules",
                    "retrieved_rule_ids",
                ],
                [],
            )
        )

        adapted.append(
            InvoiceAssuranceInput(
                invoice_number=(
                    invoice_reference
                ),
                safe_invoice_alias=(
                    safe_alias
                ),
                source_file=str(
                    first_value(
                        invoice,
                        [
                            "source_file",
                            "file_name",
                        ],
                        source_file,
                    )
                ),
                invoice_type=str(
                    first_value(
                        invoice,
                        [
                            "invoice_type",
                            "type",
                        ],
                        "N",
                    )
                ),
                billing_period_start=str(
                    first_value(
                        invoice,
                        [
                            "period_start",
                            "billing_period_start",
                            "start_date",
                        ],
                        "",
                    )
                ),
                billing_period_end=str(
                    first_value(
                        invoice,
                        [
                            "period_end",
                            "billing_period_end",
                            "end_date",
                        ],
                        "",
                    )
                ),
                invoice_net_amount=(
                    safe_float(
                        first_value(
                            invoice,
                            [
                                "final_net",
                                "net_amount",
                                "invoice_net_amount",
                                "net",
                            ],
                            0,
                        )
                    )
                ),
                reconciliation_variance=(
                    reconciliation_variance
                ),
                anomaly_score=(
                    anomaly_score
                ),
                risk_score=risk_score,
                risk_level=risk_level,
                critical_validation_failures=(
                    critical_failures
                ),
                validation_warnings=(
                    validation_warnings
                ),
                reconciliation_status=(
                    reconciliation_status
                ),
                model_result=model_result,
                billed_rate=safe_float(
                    first_value(
                        anomaly,
                        [
                            "billed_rate",
                            "maximum_rate",
                            "average_rate",
                        ],
                        0,
                    )
                )
                or None,
                expected_rate=safe_float(
                    first_value(
                        anomaly,
                        [
                            "expected_rate",
                            "reference_rate",
                            "median_rate",
                        ],
                        0,
                    )
                )
                or None,
                billed_quantity=safe_float(
                    first_value(
                        anomaly,
                        [
                            "billed_quantity",
                            "total_quantity",
                            "quantity",
                        ],
                        0,
                    )
                )
                or None,
                billed_capacity=safe_float(
                    first_value(
                        anomaly,
                        [
                            "billed_capacity",
                            "capacity",
                        ],
                        0,
                    )
                )
                or None,
                approved_capacity=safe_float(
                    first_value(
                        anomaly,
                        [
                            "approved_capacity",
                            "reference_capacity",
                        ],
                        0,
                    )
                )
                or None,
                capacity_rate=safe_float(
                    first_value(
                        anomaly,
                        [
                            "capacity_rate",
                            "charge_per_kva",
                        ],
                        0,
                    )
                )
                or None,
                billed_charge_amount=safe_float(
                    first_value(
                        anomaly,
                        [
                            "billed_charge_amount",
                            "anomalous_charge_amount",
                            "charge_amount",
                        ],
                        0,
                    )
                )
                or None,
                robust_expected_amount=safe_float(
                    first_value(
                        anomaly,
                        [
                            "robust_expected_amount",
                            "expected_amount",
                            "median_amount",
                            "reference_amount",
                        ],
                        0,
                    )
                )
                or None,
                unusual_features=(
                    extract_unusual_features(
                        anomaly
                    )
                ),
                validation_findings=(
                    findings
                ),
                rule_citations=[
                    str(value)
                    for value
                    in rule_citations
                ],
            )
        )

    return adapted


def diagnose_adapter_coverage(
    adapted: list[
        InvoiceAssuranceInput
    ],
) -> dict[str, Any]:
    total = len(adapted)

    return {
        "invoice_count": total,
        "with_reconciliation_status": sum(
            invoice.reconciliation_status
            != "UNKNOWN"
            for invoice in adapted
        ),
        "with_anomaly_score": sum(
            invoice.anomaly_score > 0
            for invoice in adapted
        ),
        "with_risk_score": sum(
            invoice.risk_score > 0
            for invoice in adapted
        ),
        "with_validation_findings": sum(
            bool(
                invoice.validation_findings
            )
            for invoice in adapted
        ),
        "with_rule_citations": sum(
            bool(invoice.rule_citations)
            for invoice in adapted
        ),
    }
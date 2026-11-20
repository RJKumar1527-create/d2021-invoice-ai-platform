from assurance.models import (
    AssuranceDecision,
    FinancialExposure,
    InvoiceAssuranceInput,
)


SAFE_TO_PROGRESS = "SAFE TO PROGRESS"

HOLD_FOR_REVIEW = "HOLD FOR REVIEW"

QUERY_SUPPLIER = "QUERY SUPPLIER"

CORRECTION_REQUIRED = "CORRECTION REQUIRED"

CREDIT_REBILL_REQUIRED = (
    "CREDIT / REBILL REQUIRED"
)

ESCALATE_INVESTIGATION = (
    "ESCALATE FOR INVESTIGATION"
)


def normalize_text(
    value: str | None,
) -> str:
    """Normalize a text value for business-rule comparisons."""
    return str(
        value or ""
    ).strip().upper()


def finding_messages(
    invoice: InvoiceAssuranceInput,
) -> list[str]:
    """Extract readable validation messages."""
    messages = []

    for finding in invoice.validation_findings:
        if isinstance(finding, dict):
            message = (
                finding.get("message")
                or finding.get("description")
                or finding.get("rule")
                or finding.get("code")
                or ""
            )

            messages.append(
                str(message)
            )

        else:
            messages.append(
                str(finding)
            )

    return messages


def contains_any(
    values: list[str],
    keywords: set[str],
) -> bool:
    """Check whether any business keyword is present."""
    combined = " ".join(
        str(value).upper()
        for value in values
    )

    return any(
        keyword in combined
        for keyword in keywords
    )


def exposure_is_material(
    exposure: FinancialExposure,
) -> bool:
    """
    Material exposure threshold.

    An invoice requires material review when:
    - estimated exposure is at least 1,000; or
    - estimated exposure is at least 10% of invoice value.
    """
    return (
        exposure.estimated_exposure
        >= 1000
        or exposure.exposure_percentage
        >= 10
    )


def exposure_is_high_value(
    exposure: FinancialExposure,
) -> bool:
    """
    High-value exposure threshold.

    An invoice is high value when:
    - estimated exposure is at least 5,000; or
    - estimated exposure is at least 20% of invoice value.
    """
    return (
        exposure.estimated_exposure
        >= 5000
        or exposure.exposure_percentage
        >= 20
    )


def is_credit_relationship_issue(
    invoice: InvoiceAssuranceInput,
) -> bool:
    invoice_type = normalize_text(
        invoice.invoice_type
    )

    if invoice_type not in {
        "C",
        "R",
        "A",
        "W",
    }:
        return False

    return contains_any(
        finding_messages(invoice),
        {
            "REFERENCE",
            "REFERENCED INVOICE",
            "ORIGINAL INVOICE",
            "CREDIT",
            "REPLACEMENT",
            "WITHDRAWAL",
            "AMENDMENT",
            "SIGN",
            "NEGATIVE",
            "POSITIVE",
        },
    )


def is_master_data_issue(
    invoice: InvoiceAssuranceInput,
) -> bool:
    evidence = (
        invoice.unusual_features
        + finding_messages(invoice)
    )

    return contains_any(
        evidence,
        {
            "MPAN",
            "MASTER DATA",
            "INACTIVE",
            "INVALID DATE",
            "CUSTOMER DATA",
            "MISSING ACCOUNT",
            "MISSING SITE",
            "EFFECTIVE DATE",
        },
    )


def is_supplier_charge_issue(
    invoice: InvoiceAssuranceInput,
    exposure: FinancialExposure,
) -> bool:
    evidence = (
        invoice.unusual_features
        + finding_messages(invoice)
    )

    return (
        contains_any(
            evidence,
            {
                "RATE",
                "TARIFF",
                "CAPACITY",
                "REACTIVE",
                "CONSUMPTION",
                "QUANTITY",
                "STANDING CHARGE",
                "UNIT CHARGE",
                "CHARGE AMOUNT",
            },
        )
        or exposure.rate_exposure > 0
        or exposure.capacity_exposure > 0
        or exposure.statistical_exposure > 0
    )


def recommend_decision(
    invoice: InvoiceAssuranceInput,
    exposure: FinancialExposure,
) -> AssuranceDecision:
    """
    Recommend the business action for one invoice.

    The deterministic decision remains authoritative.
    AI explanation may explain the decision but cannot change it.
    """
    risk_level = normalize_text(
        invoice.risk_level
    )

    reconciliation_status = normalize_text(
        invoice.reconciliation_status
    )

    model_result = normalize_text(
        invoice.model_result
    )

    material_exposure = (
        exposure_is_material(
            exposure
        )
    )

    high_value_exposure = (
        exposure_is_high_value(
            exposure
        )
    )

    if is_credit_relationship_issue(
        invoice
    ):
        return AssuranceDecision(
            decision=(
                CREDIT_REBILL_REQUIRED
            ),
            decision_reason=(
                "The credit, replacement, amendment, or "
                "withdrawal relationship does not satisfy "
                "the required invoice-reference or value-sign controls."
            ),
            recommended_actions=[
                (
                    "Verify the original invoice reference "
                    "and the relationship between the original "
                    "and corrective invoice."
                ),
                (
                    "Confirm that credit, replacement, amendment, "
                    "or withdrawal values use the required signs."
                ),
                (
                    "Prevent approval until a valid corrected "
                    "invoice relationship is received."
                ),
            ],
            exception_category=(
                "Invoice Relationship"
            ),
            priority="HIGH",
            requires_human_review=True,
            requires_supplier_query=True,
            blocks_approval=True,
        )

    if (
        invoice.critical_validation_failures
        > 0
        and is_master_data_issue(invoice)
    ):
        return AssuranceDecision(
            decision=CORRECTION_REQUIRED,
            decision_reason=(
                "A critical MPAN, account, billing-date, "
                "or reference-data control has failed."
            ),
            recommended_actions=[
                (
                    "Verify the affected account, site, MPAN, "
                    "and effective-date records."
                ),
                (
                    "Correct the source or reference data "
                    "through the approved business process."
                ),
                (
                    "Reprocess the invoice after the "
                    "data correction is completed."
                ),
            ],
            exception_category="Data Quality",
            priority="HIGH",
            requires_human_review=True,
            requires_supplier_query=False,
            blocks_approval=True,
        )

    if (
        reconciliation_status
        in {
            "MISMATCHED",
            "FAILED",
            "FAIL",
        }
        or exposure.confirmed_variance
        > 0.01
    ):
        return AssuranceDecision(
            decision=(
                ESCALATE_INVESTIGATION
            ),
            decision_reason=(
                "The invoice total does not reconcile with "
                "its associated charge-line amounts."
            ),
            recommended_actions=[
                (
                    "Identify missing, duplicated, or "
                    "incorrectly valued charge lines."
                ),
                (
                    "Compare the invoice net amount with "
                    "the complete charge-line total."
                ),
                (
                    "Place the invoice on hold until the "
                    "financial variance is explained and resolved."
                ),
                (
                    "Raise a supplier query when the variance "
                    "originates from supplier-controlled billing data."
                ),
            ],
            exception_category="Reconciliation",
            priority=(
                "CRITICAL"
                if high_value_exposure
                else "HIGH"
            ),
            requires_human_review=True,
            requires_supplier_query=(
                exposure.confirmed_variance
                > 0.01
            ),
            blocks_approval=True,
        )

    if (
        is_supplier_charge_issue(
            invoice,
            exposure,
        )
        and (
            material_exposure
            or risk_level
            in {
                "HIGH",
                "CRITICAL",
            }
        )
    ):
        return AssuranceDecision(
            decision=QUERY_SUPPLIER,
            decision_reason=(
                "A supplier-controlled rate, tariff, quantity, "
                "capacity, reactive-power, or charge value "
                "requires supporting evidence."
            ),
            recommended_actions=[
                (
                    "Verify the billed charge against the "
                    "available source-consumption, capacity, "
                    "and effective-tariff evidence."
                ),
                (
                    "Compare the charge with recent billing "
                    "periods and comparable invoices."
                ),
                (
                    "Raise a supplier query for any unsupported "
                    "material difference."
                ),
                (
                    "Keep the invoice on hold until the supplier "
                    "response and supporting evidence are accepted."
                ),
            ],
            exception_category=(
                "Supplier Charge"
            ),
            priority=(
                "CRITICAL"
                if high_value_exposure
                else "HIGH"
            ),
            requires_human_review=True,
            requires_supplier_query=True,
            blocks_approval=True,
        )

    if (
        risk_level
        in {
            "MEDIUM",
            "HIGH",
            "CRITICAL",
        }
        or model_result == "ANOMALY"
        or invoice.anomaly_score >= 60
    ):
        return AssuranceDecision(
            decision=HOLD_FOR_REVIEW,
            decision_reason=(
                "The invoice contains unusual billing behaviour "
                "that requires business review before approval."
            ),
            recommended_actions=[
                (
                    "Review the unusual invoice features "
                    "and historical comparison."
                ),
                (
                    "Confirm that the current billing pattern "
                    "is operationally reasonable."
                ),
                (
                    "Verify supporting evidence before "
                    "authorizing the invoice."
                ),
            ],
            exception_category=(
                "Billing Anomaly"
            ),
            priority=(
                "HIGH"
                if risk_level
                in {
                    "HIGH",
                    "CRITICAL",
                }
                else "MEDIUM"
            ),
            requires_human_review=True,
            requires_supplier_query=False,
            blocks_approval=True,
        )

    safe_reconciliation = (
        reconciliation_status
        in {
            "MATCHED",
            "PASSED",
            "PASS",
        }
    )

    if (
        invoice.critical_validation_failures
        == 0
        and safe_reconciliation
        and risk_level == "LOW"
        and exposure.estimated_exposure
        < 100
    ):
        return AssuranceDecision(
            decision=SAFE_TO_PROGRESS,
            decision_reason=(
                "The invoice passed critical controls, "
                "reconciled successfully, and has no "
                "material financial exposure."
            ),
            recommended_actions=[
                (
                    "Progress the invoice through the "
                    "normal business approval process."
                ),
                (
                    "Retain the automated assurance result "
                    "for audit and reporting."
                ),
            ],
            exception_category="None",
            priority="LOW",
            requires_human_review=False,
            requires_supplier_query=False,
            blocks_approval=False,
        )

    return AssuranceDecision(
        decision=HOLD_FOR_REVIEW,
        decision_reason=(
            "The available controls do not provide enough "
            "evidence for automatic invoice progression."
        ),
        recommended_actions=[
            (
                "Review the validation, reconciliation, "
                "anomaly, risk, and financial-exposure evidence."
            ),
            (
                "Record an authorized human assurance decision."
            ),
        ],
        exception_category=(
            "Control Review"
        ),
        priority="MEDIUM",
        requires_human_review=True,
        requires_supplier_query=False,
        blocks_approval=True,
    )
from assurance.models import (
    FinancialExposure,
    InvoiceAssuranceInput,
)


def safe_float(
    value: float | int | str | None,
    default: float = 0.0,
) -> float:
    """Convert a value to float without raising an exception."""
    try:
        if value is None or value == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def positive_value(
    value: float | int | str | None,
) -> float:
    """Return a non-negative numeric value."""
    return max(
        safe_float(value),
        0.0,
    )


def calculate_rate_exposure(
    invoice: InvoiceAssuranceInput,
) -> float:
    """
    Estimate exposure caused by a billed rate above
    the expected or approved rate.

    Formula:
        quantity x maximum(billed rate - expected rate, 0)
    """
    if (
        invoice.billed_quantity is None
        or invoice.billed_rate is None
        or invoice.expected_rate is None
    ):
        return 0.0

    quantity = positive_value(
        invoice.billed_quantity
    )

    billed_rate = safe_float(
        invoice.billed_rate
    )

    expected_rate = safe_float(
        invoice.expected_rate
    )

    rate_difference = max(
        billed_rate - expected_rate,
        0.0,
    )

    return round(
        quantity * rate_difference,
        2,
    )


def calculate_capacity_exposure(
    invoice: InvoiceAssuranceInput,
) -> float:
    """
    Estimate exposure caused by billed capacity above
    the approved capacity.

    Formula:
        capacity difference
        x capacity rate
        x billing-period factor
    """
    if (
        invoice.billed_capacity is None
        or invoice.approved_capacity is None
        or invoice.capacity_rate is None
    ):
        return 0.0

    billed_capacity = positive_value(
        invoice.billed_capacity
    )

    approved_capacity = positive_value(
        invoice.approved_capacity
    )

    capacity_rate = positive_value(
        invoice.capacity_rate
    )

    period_factor = positive_value(
        invoice.billing_period_factor
    )

    capacity_difference = max(
        billed_capacity - approved_capacity,
        0.0,
    )

    return round(
        capacity_difference
        * capacity_rate
        * period_factor,
        2,
    )


def calculate_statistical_exposure(
    invoice: InvoiceAssuranceInput,
) -> float:
    """
    Estimate exposure by comparing the billed charge with
    a robust expected value, such as a historical median.

    This is estimated exposure, not a confirmed overcharge.
    """
    if (
        invoice.billed_charge_amount is None
        or invoice.robust_expected_amount is None
    ):
        return 0.0

    billed_amount = safe_float(
        invoice.billed_charge_amount
    )

    expected_amount = safe_float(
        invoice.robust_expected_amount
    )

    return round(
        max(
            billed_amount - expected_amount,
            0.0,
        ),
        2,
    )


def calculate_financial_exposure(
    invoice: InvoiceAssuranceInput,
) -> FinancialExposure:
    """
    Calculate the strongest supported financial exposure.

    Exposure types are not added together because multiple
    controls may identify the same underlying billing issue.
    Using the largest supported amount prevents double counting.
    """
    confirmed_variance = round(
        abs(
            safe_float(
                invoice.reconciliation_variance
            )
        ),
        2,
    )

    rate_exposure = (
        calculate_rate_exposure(
            invoice
        )
    )

    capacity_exposure = (
        calculate_capacity_exposure(
            invoice
        )
    )

    statistical_exposure = (
        calculate_statistical_exposure(
            invoice
        )
    )

    confirmed_exposure = max(
        confirmed_variance,
        rate_exposure,
        capacity_exposure,
    )

    if confirmed_exposure > 0:
        estimated_exposure = (
            confirmed_exposure
        )

        exposure_basis = (
            "Confirmed financial control variance"
        )

        exposure_confidence = "HIGH"

    elif statistical_exposure > 0:
        estimated_exposure = (
            statistical_exposure
        )

        exposure_basis = (
            "Statistical expected-value difference"
        )

        exposure_confidence = "MEDIUM"

    else:
        estimated_exposure = 0.0

        exposure_basis = (
            "No measurable exposure identified"
        )

        exposure_confidence = "LOW"

    invoice_value = abs(
        safe_float(
            invoice.invoice_net_amount
        )
    )

    exposure_percentage = (
        estimated_exposure
        / invoice_value
        * 100
        if invoice_value > 0
        else 0.0
    )

    return FinancialExposure(
        confirmed_variance=(
            confirmed_variance
        ),
        rate_exposure=rate_exposure,
        capacity_exposure=(
            capacity_exposure
        ),
        statistical_exposure=(
            statistical_exposure
        ),
        estimated_exposure=round(
            estimated_exposure,
            2,
        ),
        exposure_percentage=round(
            exposure_percentage,
            2,
        ),
        exposure_basis=exposure_basis,
        exposure_confidence=(
            exposure_confidence
        ),
    )
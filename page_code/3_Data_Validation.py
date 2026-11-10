from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st


MONEY_TOLERANCE = Decimal("0.02")


def to_decimal(value):
    """Convert a value safely to Decimal."""
    if value is None or str(value).strip() == "":
        return None

    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def parse_date(value):
    """Parse a D2021 date in YYYYMMDD format."""
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def calculate_charge_amount(charge):
    """
    Calculate the expected CCD charge amount.

    A: quantity x rate x days / 100
    S: days x rate / 100
    Others: quantity x rate / 100
    """
    charge_type = str(charge.get("charge_type", "")).upper()

    days = to_decimal(charge.get("number_of_days"))
    quantity = to_decimal(charge.get("quantity"))
    rate = to_decimal(charge.get("rate"))

    if rate is None:
        return None

    if charge_type == "A":
        if quantity is None or days is None:
            return None
        result = quantity * rate * days / Decimal("100")

    elif charge_type == "S":
        if days is None:
            return None
        result = days * rate / Decimal("100")

    else:
        if quantity is None:
            return None
        result = quantity * rate / Decimal("100")

    return result.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def add_result(
    results,
    invoice_number,
    rule,
    category,
    severity,
    expected,
    actual,
    passed,
):
    results.append(
        {
            "Invoice Number": invoice_number,
            "Category": category,
            "Rule": rule,
            "Severity": severity,
            "Expected": expected,
            "Actual": actual,
            "Result": "PASS" if passed else "FAIL",
        }
    )


def validate_invoices(parsed_data):
    """Validate all parsed D2021 invoices."""
    results = []
    invoice_numbers = {}

    for invoice in parsed_data.get("invoices", []):
        invoice_number = invoice.get("invoice_number", "").strip()

        invoice_numbers[invoice_number] = (
            invoice_numbers.get(invoice_number, 0) + 1
        )

    for invoice in parsed_data.get("invoices", []):
        invoice_number = invoice.get("invoice_number", "").strip()
        display_number = invoice_number or "MISSING"

        # 1. Mandatory invoice number
        add_result(
            results,
            display_number,
            "Invoice number is mandatory",
            "Mandatory Field",
            "Critical",
            "Non-empty invoice number",
            invoice_number or "Blank",
            bool(invoice_number),
        )

        # 2. Duplicate invoice number
        duplicate_count = invoice_numbers.get(invoice_number, 0)

        add_result(
            results,
            display_number,
            "Invoice number must be unique in the file",
            "Duplicate Check",
            "Critical",
            "1 occurrence",
            f"{duplicate_count} occurrence(s)",
            bool(invoice_number) and duplicate_count == 1,
        )

        # 3. Invoice type
        invoice_type = invoice.get("invoice_type", "").strip().upper()
        allowed_types = {"N", "C", "R"}

        add_result(
            results,
            display_number,
            "Invoice type must be recognized",
            "Invoice Type",
            "Critical",
            "C or R",
            invoice_type or "Blank",
            invoice_type in allowed_types,
        )

        # 4. MPAN presence
        mpans = [
            str(mpan).strip()
            for mpan in invoice.get("mpans", [])
            if str(mpan).strip()
        ]

        add_result(
            results,
            display_number,
            "At least one MPAN must be linked",
            "MPAN",
            "Critical",
            "One or more MPANs",
            f"{len(mpans)} MPAN(s)",
            len(mpans) > 0,
        )

        # 5. MPAN format
        invalid_mpans = [
            mpan
            for mpan in mpans
            if not mpan.isdigit() or len(mpan) != 13
        ]

        add_result(
            results,
            display_number,
            "Core MPAN must contain 13 digits",
            "MPAN",
            "Critical",
            "13 numeric digits",
            (
                ", ".join(invalid_mpans)
                if invalid_mpans
                else "All MPANs valid"
            ),
            len(invalid_mpans) == 0,
        )

        # 6. Required dates
        invoice_date_raw = invoice.get("invoice_date", "")
        period_start_raw = invoice.get("period_start", "")
        period_end_raw = invoice.get("period_end", "")

        invoice_date = parse_date(invoice_date_raw)
        period_start = parse_date(period_start_raw)
        period_end = parse_date(period_end_raw)

        add_result(
            results,
            display_number,
            "Invoice date must be valid YYYYMMDD",
            "Date",
            "Critical",
            "Valid YYYYMMDD date",
            invoice_date_raw or "Blank",
            invoice_date is not None,
        )

        add_result(
            results,
            display_number,
            "Invoice period start must be valid",
            "Date",
            "Critical",
            "Valid YYYYMMDD date",
            period_start_raw or "Blank",
            period_start is not None,
        )

        add_result(
            results,
            display_number,
            "Invoice period end must be valid",
            "Date",
            "Critical",
            "Valid YYYYMMDD date",
            period_end_raw or "Blank",
            period_end is not None,
        )

        valid_period = (
            period_start is not None
            and period_end is not None
            and period_start <= period_end
        )

        add_result(
            results,
            display_number,
            "Invoice period start must not exceed period end",
            "Date",
            "Critical",
            "Start date <= end date",
            f"{period_start_raw} to {period_end_raw}",
            valid_period,
        )

        # 7. Charges must exist
        charges = invoice.get("charges", [])

        add_result(
            results,
            display_number,
            "Invoice must contain CCD charge records",
            "Charge",
            "Critical",
            "One or more CCD records",
            f"{len(charges)} CCD record(s)",
            len(charges) > 0,
        )

        # 8. Net + VAT = Gross
        final_net = to_decimal(invoice.get("final_net"))
        final_vat = to_decimal(invoice.get("final_vat"))
        final_gross = to_decimal(invoice.get("final_gross"))

        financial_values_available = all(
            value is not None
            for value in [final_net, final_vat, final_gross]
        )

        totals_match = False
        calculated_gross = None

        if financial_values_available:
            calculated_gross = (
                final_net + final_vat
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            totals_match = (
                abs(calculated_gross - final_gross)
                <= MONEY_TOLERANCE
            )

        add_result(
            results,
            display_number,
            "Net amount plus VAT must equal gross amount",
            "Financial",
            "Critical",
            (
                str(calculated_gross)
                if calculated_gross is not None
                else "Numeric net, VAT and gross"
            ),
            (
                str(final_gross)
                if final_gross is not None
                else "Missing or invalid value"
            ),
            financial_values_available and totals_match,
        )

        # 9. Credit and rebill signs
        if invoice_type == "C":
            sign_valid = all(
                value is not None and value <= 0
                for value in [final_net, final_vat, final_gross]
            )

            add_result(
                results,
                display_number,
                "Credit invoice values must be zero or negative",
                "Invoice Type",
                "Critical",
                "Net, VAT and gross <= 0",
                (
                    f"Net={final_net}, VAT={final_vat}, "
                    f"Gross={final_gross}"
                ),
                sign_valid,
            )

        elif invoice_type == "R":
            sign_valid = all(
                value is not None and value >= 0
                for value in [final_net, final_vat, final_gross]
            )

            add_result(
                results,
                display_number,
                "Rebill invoice values must be zero or positive",
                "Invoice Type",
                "Critical",
                "Net, VAT and gross >= 0",
                (
                    f"Net={final_net}, VAT={final_vat}, "
                    f"Gross={final_gross}"
                ),
                sign_valid,
            )

        # 10. Validate each CCD amount
        charge_sum = Decimal("0.00")
        valid_charge_amounts = True

        for charge_position, charge in enumerate(charges, start=1):
            actual_amount = to_decimal(charge.get("amount"))
            expected_amount = calculate_charge_amount(charge)

            if actual_amount is not None:
                charge_sum += actual_amount

            amount_matches = (
                actual_amount is not None
                and expected_amount is not None
                and abs(actual_amount - expected_amount)
                <= MONEY_TOLERANCE
            )

            if not amount_matches:
                valid_charge_amounts = False

                add_result(
                    results,
                    display_number,
                    (
                        f"CCD charge {charge_position} calculation: "
                        f"{charge.get('description', '')}"
                    ),
                    "Charge Calculation",
                    "Warning",
                    (
                        str(expected_amount)
                        if expected_amount is not None
                        else "Calculable amount"
                    ),
                    (
                        str(actual_amount)
                        if actual_amount is not None
                        else "Invalid amount"
                    ),
                    False,
                )

        if valid_charge_amounts and charges:
            add_result(
                results,
                display_number,
                "All CCD charge calculations are correct",
                "Charge Calculation",
                "Warning",
                "Calculated amounts within £0.02 tolerance",
                f"{len(charges)} charge(s) checked",
                True,
            )

        # 11. BCD net versus CCD sum
        charge_sum = charge_sum.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        bcd_ccd_match = (
            final_net is not None
            and abs(final_net - charge_sum)
            <= MONEY_TOLERANCE
        )

        add_result(
            results,
            display_number,
            "BCD final net must equal the sum of CCD amounts",
            "Reconciliation",
            "Critical",
            str(charge_sum),
            (
                str(final_net)
                if final_net is not None
                else "Missing final net"
            ),
            bcd_ccd_match,
        )

    return results


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 3: Data Validation")

parsed_data = st.session_state.get("parsed_d2021")

if not parsed_data:
    st.warning("No parsed D2021 data is available.")
    st.info(
        "Complete Step 1: File Upload and "
        "Step 2: Parse & Structure first."
    )
    st.stop()

with st.spinner("Validating D2021 invoices..."):
    validation_results = validate_invoices(parsed_data)

validation_df = pd.DataFrame(validation_results)

if validation_df.empty:
    st.warning("No invoices were available for validation.")
    st.stop()

failed_df = validation_df[
    validation_df["Result"] == "FAIL"
]

critical_failures = failed_df[
    failed_df["Severity"] == "Critical"
]

warning_failures = failed_df[
    failed_df["Severity"] == "Warning"
]

failed_invoice_numbers = set(
    critical_failures["Invoice Number"].tolist()
)

all_invoice_numbers = set(
    validation_df["Invoice Number"].tolist()
)

passed_invoice_count = (
    len(all_invoice_numbers) - len(failed_invoice_numbers)
)

metric1, metric2, metric3, metric4, metric5 = st.columns(5)

metric1.metric(
    "Invoices",
    len(all_invoice_numbers),
)

metric2.metric(
    "Passed Invoices",
    passed_invoice_count,
)

metric3.metric(
    "Failed Invoices",
    len(failed_invoice_numbers),
)

metric4.metric(
    "Critical Failures",
    len(critical_failures),
)

metric5.metric(
    "Warnings",
    len(warning_failures),
)

if len(critical_failures) == 0:
    st.success(
        "All invoices passed the critical validation rules."
    )
else:
    st.error(
        f"{len(failed_invoice_numbers)} invoice(s) failed "
        "one or more critical validation rules."
    )

st.markdown("---")
st.subheader("Validation Filters")

filter1, filter2, filter3 = st.columns(3)

with filter1:
    selected_result = st.selectbox(
        "Result",
        ["ALL", "FAIL", "PASS"],
    )

with filter2:
    selected_severity = st.selectbox(
        "Severity",
        ["ALL", "Critical", "Warning"],
    )

with filter3:
    invoice_options = ["ALL"] + sorted(
        validation_df["Invoice Number"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_invoice = st.selectbox(
        "Invoice",
        invoice_options,
    )

filtered_df = validation_df.copy()

if selected_result != "ALL":
    filtered_df = filtered_df[
        filtered_df["Result"] == selected_result
    ]

if selected_severity != "ALL":
    filtered_df = filtered_df[
        filtered_df["Severity"] == selected_severity
    ]

if selected_invoice != "ALL":
    filtered_df = filtered_df[
        filtered_df["Invoice Number"] == selected_invoice
    ]

st.markdown("---")
st.subheader("Validation Results")

st.dataframe(
    filtered_df,
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")
st.subheader("Failures by Category")

if not failed_df.empty:
    category_summary = (
        failed_df.groupby(
            ["Category", "Severity"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "Failure Count"})
        .sort_values(
            "Failure Count",
            ascending=False,
        )
    )

    st.dataframe(
        category_summary,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.success("No validation failures were identified.")

st.session_state.validation_results = validation_results
st.session_state.validation_summary = {
    "total_invoices": len(all_invoice_numbers),
    "passed_invoices": passed_invoice_count,
    "failed_invoices": len(failed_invoice_numbers),
    "critical_failures": len(critical_failures),
    "warnings": len(warning_failures),
}

st.session_state.latest_result["status"] = "VALIDATED"

st.markdown("---")
st.success(
    "Validation results have been saved for the next step: "
    "Invoice Reconciliation."
)
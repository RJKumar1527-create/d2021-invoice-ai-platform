from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st


MONEY_TOLERANCE = Decimal("0.02")


def to_decimal(value):
    """Convert a D2021 numeric value safely to Decimal."""
    if value is None or str(value).strip() == "":
        return None

    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def money(value):
    """Round a Decimal value to two decimal places."""
    if value is None:
        return None

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def calculate_percentage_variance(expected, actual):
    """Calculate percentage variance safely."""
    if expected is None or actual is None:
        return None

    if expected == 0:
        return Decimal("0.00") if actual == 0 else None

    percentage = (
        abs(actual - expected)
        / abs(expected)
        * Decimal("100")
    )

    return percentage.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def reconcile_invoices(parsed_data):
    """
    Compare the BCD final net amount with the sum of CCD billed amounts.

    This stage uses the billed CCD amount values.
    It does not yet use external tariff-reference data.
    """
    reconciliation_rows = []
    charge_rows = []

    for invoice in parsed_data.get("invoices", []):
        invoice_number = (
            invoice.get("invoice_number", "").strip()
            or "MISSING"
        )

        bcd_net = to_decimal(invoice.get("final_net"))
        charges = invoice.get("charges", [])

        ccd_total = Decimal("0.00")
        invalid_charge_count = 0

        for position, charge in enumerate(charges, start=1):
            billed_amount = to_decimal(
                charge.get("amount")
            )

            if billed_amount is None:
                invalid_charge_count += 1
            else:
                ccd_total += billed_amount

            charge_rows.append(
                {
                    "Invoice Number": invoice_number,
                    "Charge Position": position,
                    "Charge Type": charge.get(
                        "charge_type",
                        "",
                    ),
                    "Description": charge.get(
                        "description",
                        "",
                    ),
                    "Days": charge.get(
                        "number_of_days",
                        "",
                    ),
                    "Unit Code": charge.get(
                        "unit_code",
                        "",
                    ),
                    "Quantity": charge.get(
                        "quantity",
                        "",
                    ),
                    "Rate": charge.get(
                        "rate",
                        "",
                    ),
                    "Billed Amount": (
                        float(billed_amount)
                        if billed_amount is not None
                        else None
                    ),
                }
            )

        ccd_total = money(ccd_total)

        variance = None

        if bcd_net is not None:
            bcd_net = money(bcd_net)
            variance = money(bcd_net - ccd_total)

        absolute_variance = (
            money(abs(variance))
            if variance is not None
            else None
        )

        variance_percentage = calculate_percentage_variance(
            ccd_total,
            bcd_net,
        )

        if bcd_net is None:
            status = "INVALID BCD NET"

        elif invalid_charge_count > 0:
            status = "INVALID CCD AMOUNT"

        elif absolute_variance <= MONEY_TOLERANCE:
            status = "MATCHED"

        else:
            status = "MISMATCHED"

        reconciliation_rows.append(
            {
                "Invoice Number": invoice_number,
                "Invoice Type": invoice.get(
                    "invoice_type",
                    "",
                ),
                "Site": invoice.get(
                    "site_name",
                    "",
                ),
                "MPAN Count": len(
                    invoice.get("mpans", [])
                ),
                "Charge Count": len(charges),
                "Invalid Charges": invalid_charge_count,
                "BCD Net": (
                    float(bcd_net)
                    if bcd_net is not None
                    else None
                ),
                "CCD Total": float(ccd_total),
                "Variance": (
                    float(variance)
                    if variance is not None
                    else None
                ),
                "Absolute Variance": (
                    float(absolute_variance)
                    if absolute_variance is not None
                    else None
                ),
                "Variance %": (
                    float(variance_percentage)
                    if variance_percentage is not None
                    else None
                ),
                "Status": status,
            }
        )

    return reconciliation_rows, charge_rows


def format_currency(value):
    """Format a value as GBP."""
    if value is None:
        return "Unavailable"

    return f"£{value:,.2f}"


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 4: Invoice Reconciliation")

parsed_data = st.session_state.get("parsed_d2021")
validation_summary = st.session_state.get(
    "validation_summary"
)

if not parsed_data:
    st.warning("No parsed D2021 data is available.")
    st.info(
        "Complete File Upload and Parse & Structure first."
    )
    st.stop()

if not validation_summary:
    st.warning("Data Validation has not been completed.")
    st.info(
        "Complete Step 3: Data Validation before reconciliation."
    )
    st.stop()


with st.spinner("Reconciling BCD and CCD amounts..."):
    reconciliation_rows, charge_rows = reconcile_invoices(
        parsed_data
    )

reconciliation_df = pd.DataFrame(
    reconciliation_rows
)

charge_df = pd.DataFrame(charge_rows)

if reconciliation_df.empty:
    st.warning("No invoices are available for reconciliation.")
    st.stop()


matched_df = reconciliation_df[
    reconciliation_df["Status"] == "MATCHED"
]

mismatched_df = reconciliation_df[
    reconciliation_df["Status"] == "MISMATCHED"
]

invalid_df = reconciliation_df[
    reconciliation_df["Status"].isin(
        [
            "INVALID BCD NET",
            "INVALID CCD AMOUNT",
        ]
    )
]

total_bcd_net = reconciliation_df[
    "BCD Net"
].fillna(0).sum()

total_ccd_amount = reconciliation_df[
    "CCD Total"
].fillna(0).sum()

total_absolute_variance = reconciliation_df[
    "Absolute Variance"
].fillna(0).sum()


st.info(
    "This stage compares the BCD final net amount with the "
    "sum of billed CCD charge amounts. The tolerance is £0.02."
)

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Total Invoices",
    len(reconciliation_df),
)

metric2.metric(
    "Matched",
    len(matched_df),
)

metric3.metric(
    "Mismatched",
    len(mismatched_df),
)

metric4.metric(
    "Invalid",
    len(invalid_df),
)

amount1, amount2, amount3 = st.columns(3)

amount1.metric(
    "Total BCD Net",
    format_currency(total_bcd_net),
)

amount2.metric(
    "Total CCD Amount",
    format_currency(total_ccd_amount),
)

amount3.metric(
    "Total Absolute Variance",
    format_currency(total_absolute_variance),
)


if len(mismatched_df) == 0 and len(invalid_df) == 0:
    st.success(
        "All invoice BCD net amounts match their CCD charge totals."
    )
else:
    st.warning(
        f"{len(mismatched_df)} invoice(s) are mismatched and "
        f"{len(invalid_df)} invoice(s) contain invalid values."
    )


st.markdown("---")
st.subheader("Reconciliation Filters")

filter1, filter2, filter3 = st.columns(3)

with filter1:
    selected_status = st.selectbox(
        "Status",
        [
            "ALL",
            "MATCHED",
            "MISMATCHED",
            "INVALID BCD NET",
            "INVALID CCD AMOUNT",
        ],
    )

with filter2:
    selected_type = st.selectbox(
        "Invoice Type",
        ["ALL"]
        + sorted(
            reconciliation_df["Invoice Type"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        ),
    )

with filter3:
    invoice_options = (
        ["ALL"]
        + sorted(
            reconciliation_df["Invoice Number"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )
    )

    selected_invoice = st.selectbox(
        "Invoice Number",
        invoice_options,
    )


filtered_df = reconciliation_df.copy()

if selected_status != "ALL":
    filtered_df = filtered_df[
        filtered_df["Status"] == selected_status
    ]

if selected_type != "ALL":
    filtered_df = filtered_df[
        filtered_df["Invoice Type"] == selected_type
    ]

if selected_invoice != "ALL":
    filtered_df = filtered_df[
        filtered_df["Invoice Number"]
        == selected_invoice
    ]


st.markdown("---")
st.subheader("Invoice Reconciliation Results")

display_df = filtered_df.copy()

currency_columns = [
    "BCD Net",
    "CCD Total",
    "Variance",
    "Absolute Variance",
]

for column in currency_columns:
    display_df[column] = display_df[column].apply(
        lambda value: (
            f"£{value:,.2f}"
            if pd.notna(value)
            else ""
        )
    )

display_df["Variance %"] = display_df[
    "Variance %"
].apply(
    lambda value: (
        f"{value:,.2f}%"
        if pd.notna(value)
        else ""
    )
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)


st.markdown("---")
st.subheader("Invoice Detail")

detail_invoice = st.selectbox(
    "Select an invoice to view its CCD charges",
    sorted(
        reconciliation_df[
            "Invoice Number"
        ].unique().tolist()
    ),
    key="reconciliation_detail_invoice",
)

invoice_summary = reconciliation_df[
    reconciliation_df["Invoice Number"]
    == detail_invoice
].iloc[0]

detail1, detail2, detail3, detail4 = st.columns(4)

detail1.metric(
    "BCD Net",
    format_currency(
        invoice_summary["BCD Net"]
    ),
)

detail2.metric(
    "CCD Total",
    format_currency(
        invoice_summary["CCD Total"]
    ),
)

detail3.metric(
    "Variance",
    format_currency(
        invoice_summary["Variance"]
    ),
)

detail4.metric(
    "Status",
    invoice_summary["Status"],
)


selected_charges = charge_df[
    charge_df["Invoice Number"] == detail_invoice
].copy()

if not selected_charges.empty:
    selected_charges[
        "Billed Amount"
    ] = selected_charges[
        "Billed Amount"
    ].apply(
        lambda value: (
            f"£{value:,.2f}"
            if pd.notna(value)
            else "Invalid"
        )
    )

    st.dataframe(
        selected_charges,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info(
        "No CCD charge records were found for this invoice."
    )


st.markdown("---")
st.subheader("Largest Variances")

largest_variances = (
    reconciliation_df[
        reconciliation_df["Status"] == "MISMATCHED"
    ]
    .sort_values(
        "Absolute Variance",
        ascending=False,
    )
    .head(20)
)

if largest_variances.empty:
    st.success(
        "No BCD-to-CCD reconciliation mismatches were found."
    )
else:
    st.dataframe(
        largest_variances,
        use_container_width=True,
        hide_index=True,
    )


csv_data = reconciliation_df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    label="Download Reconciliation Results",
    data=csv_data,
    file_name="d2021_reconciliation_results.csv",
    mime="text/csv",
    use_container_width=True,
)


st.session_state.reconciliation_results = (
    reconciliation_rows
)

st.session_state.reconciliation_summary = {
    "total_invoices": len(reconciliation_df),
    "matched": len(matched_df),
    "mismatched": len(mismatched_df),
    "invalid": len(invalid_df),
    "total_bcd_net": float(total_bcd_net),
    "total_ccd_amount": float(total_ccd_amount),
    "total_absolute_variance": float(
        total_absolute_variance
    ),
}

latest_result = st.session_state.get(
    "latest_result"
)

if latest_result:
    latest_result["status"] = "RECONCILED"

st.markdown("---")
st.success(
    "Reconciliation results have been saved for the next step: "
    "Anomaly Detection."
)
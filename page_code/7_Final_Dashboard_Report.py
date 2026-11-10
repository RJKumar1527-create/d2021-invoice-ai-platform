import io
import zipfile

import pandas as pd
import streamlit as st


def safe_dataframe(data):
    """Convert stored session data into a DataFrame."""
    if not data:
        return pd.DataFrame()

    return pd.DataFrame(data)


def format_currency(value):
    """Format a numeric value as GBP."""
    try:
        return f"£{float(value):,.2f}"
    except (TypeError, ValueError):
        return "£0.00"


def create_invoice_summary(
    parsed_data,
    validation_results,
    reconciliation_results,
    anomaly_results,
    risk_results,
):
    """Create one consolidated row per invoice."""

    validation_df = safe_dataframe(validation_results)
    reconciliation_df = safe_dataframe(
        reconciliation_results
    )
    anomaly_df = safe_dataframe(anomaly_results)
    risk_df = safe_dataframe(risk_results)

    validation_lookup = {}

    if not validation_df.empty:
        for invoice_number, group in validation_df.groupby(
            "Invoice Number"
        ):
            failures = group[
                group["Result"] == "FAIL"
            ]

            critical_count = len(
                failures[
                    failures["Severity"] == "Critical"
                ]
            )

            warning_count = len(
                failures[
                    failures["Severity"] == "Warning"
                ]
            )

            validation_lookup[str(invoice_number)] = {
                "validation_status": (
                    "FAILED"
                    if critical_count > 0
                    else "PASSED"
                ),
                "critical_failures": critical_count,
                "warnings": warning_count,
            }

    reconciliation_lookup = {}

    if not reconciliation_df.empty:
        reconciliation_lookup = {
            str(row["Invoice Number"]): row
            for _, row in reconciliation_df.iterrows()
        }

    anomaly_lookup = {}

    if not anomaly_df.empty:
        anomaly_lookup = {
            str(row["invoice_number"]): row
            for _, row in anomaly_df.iterrows()
        }

    risk_lookup = {}

    if not risk_df.empty:
        risk_lookup = {
            str(row["Invoice Number"]): row
            for _, row in risk_df.iterrows()
        }

    rows = []

    for invoice in parsed_data.get("invoices", []):
        invoice_number = str(
            invoice.get("invoice_number", "MISSING")
        )

        validation = validation_lookup.get(
            invoice_number,
            {
                "validation_status": "NOT AVAILABLE",
                "critical_failures": 0,
                "warnings": 0,
            },
        )

        reconciliation = reconciliation_lookup.get(
            invoice_number,
            {},
        )

        anomaly = anomaly_lookup.get(
            invoice_number,
            {},
        )

        risk = risk_lookup.get(
            invoice_number,
            {},
        )

        rows.append(
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
                "Charge Count": len(
                    invoice.get("charges", [])
                ),
                "Period Start": invoice.get(
                    "period_start",
                    "",
                ),
                "Period End": invoice.get(
                    "period_end",
                    "",
                ),
                "Net Amount": reconciliation.get(
                    "BCD Net",
                    invoice.get("final_net", 0),
                ),
                "Validation Status": validation[
                    "validation_status"
                ],
                "Critical Failures": validation[
                    "critical_failures"
                ],
                "Validation Warnings": validation[
                    "warnings"
                ],
                "Reconciliation Status": reconciliation.get(
                    "Status",
                    "NOT AVAILABLE",
                ),
                "Reconciliation Variance": (
                    reconciliation.get(
                        "Variance",
                        0,
                    )
                ),
                "Anomaly Score": anomaly.get(
                    "anomaly_score",
                    0,
                ),
                "ML Result": (
                    "ANOMALY"
                    if anomaly.get(
                        "model_prediction",
                        1,
                    ) == -1
                    else "NORMAL"
                ),
                "Unusual Features": anomaly.get(
                    "unusual_features",
                    "",
                ),
                "Final Risk Score": risk.get(
                    "Final Risk Score",
                    0,
                ),
                "Risk Level": risk.get(
                    "Risk Level",
                    "NOT AVAILABLE",
                ),
                "Explanation": risk.get(
                    "Explanation",
                    "",
                ),
                "Recommended Action": risk.get(
                    "Recommended Action",
                    "",
                ),
            }
        )

    return pd.DataFrame(rows)


def create_zip_report(
    invoice_summary_df,
    validation_df,
    reconciliation_df,
    anomaly_df,
    risk_df,
):
    """Create a ZIP file containing all CSV reports."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as report_zip:

        report_zip.writestr(
            "invoice_summary.csv",
            invoice_summary_df.to_csv(
                index=False
            ),
        )

        report_zip.writestr(
            "validation_results.csv",
            validation_df.to_csv(
                index=False
            ),
        )

        report_zip.writestr(
            "reconciliation_results.csv",
            reconciliation_df.to_csv(
                index=False
            ),
        )

        report_zip.writestr(
            "anomaly_results.csv",
            anomaly_df.to_csv(
                index=False
            ),
        )

        report_zip.writestr(
            "risk_results.csv",
            risk_df.to_csv(
                index=False
            ),
        )

    zip_buffer.seek(0)

    return zip_buffer.getvalue()


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 7: Final Dashboard & Report")

latest_result = st.session_state.get("latest_result")
parsed_data = st.session_state.get("parsed_d2021")
validation_results = st.session_state.get(
    "validation_results"
)
reconciliation_results = st.session_state.get(
    "reconciliation_results"
)
anomaly_results = st.session_state.get(
    "anomaly_results"
)
risk_results = st.session_state.get(
    "risk_results"
)

missing_steps = []

if not parsed_data:
    missing_steps.append("Parse & Structure")

if validation_results is None:
    missing_steps.append("Data Validation")

if reconciliation_results is None:
    missing_steps.append("Invoice Reconciliation")

if anomaly_results is None:
    missing_steps.append("Anomaly Detection")

if risk_results is None:
    missing_steps.append(
        "Risk Scoring & AI Explanation"
    )

if missing_steps:
    st.warning(
        "Complete these workflow steps first: "
        + ", ".join(missing_steps)
    )
    st.stop()


validation_df = safe_dataframe(
    validation_results
)

reconciliation_df = safe_dataframe(
    reconciliation_results
)

anomaly_df = safe_dataframe(
    anomaly_results
)

risk_df = safe_dataframe(
    risk_results
)

invoice_summary_df = create_invoice_summary(
    parsed_data,
    validation_results,
    reconciliation_results,
    anomaly_results,
    risk_results,
)


st.info(
    f"File: {latest_result.get('file_name', 'Unknown')} | "
    f"Processing ID: "
    f"{latest_result.get('processing_id', 'Unknown')}"
)


st.markdown("### Processing Overview")

overview1, overview2, overview3, overview4 = st.columns(4)

overview1.metric(
    "Invoices",
    len(invoice_summary_df),
)

overview2.metric(
    "MPAN Records",
    sum(
        len(site.get("mpans", []))
        for site in parsed_data.get("sites", [])
    ),
)

overview3.metric(
    "Charge Records",
    sum(
        len(invoice.get("charges", []))
        for invoice in parsed_data.get(
            "invoices",
            [],
        )
    ),
)

overview4.metric(
    "Parsing Errors",
    len(parsed_data.get("errors", [])),
)


st.markdown("---")
st.markdown("### Validation and Reconciliation")

failed_invoices = invoice_summary_df[
    invoice_summary_df["Validation Status"]
    == "FAILED"
]

warning_invoices = invoice_summary_df[
    invoice_summary_df["Validation Warnings"] > 0
]

matched_invoices = invoice_summary_df[
    invoice_summary_df["Reconciliation Status"]
    == "MATCHED"
]

mismatched_invoices = invoice_summary_df[
    invoice_summary_df["Reconciliation Status"]
    == "MISMATCHED"
]

result1, result2, result3, result4 = st.columns(4)

result1.metric(
    "Validation Passed",
    len(invoice_summary_df) - len(failed_invoices),
)

result2.metric(
    "Validation Failed",
    len(failed_invoices),
)

result3.metric(
    "Reconciliation Matched",
    len(matched_invoices),
)

result4.metric(
    "Reconciliation Mismatched",
    len(mismatched_invoices),
)


st.markdown("---")
st.markdown("### ML Anomaly and Risk Summary")

anomaly_invoices = invoice_summary_df[
    invoice_summary_df["ML Result"] == "ANOMALY"
]

critical_invoices = invoice_summary_df[
    invoice_summary_df["Risk Level"] == "CRITICAL"
]

high_invoices = invoice_summary_df[
    invoice_summary_df["Risk Level"] == "HIGH"
]

medium_invoices = invoice_summary_df[
    invoice_summary_df["Risk Level"] == "MEDIUM"
]

low_invoices = invoice_summary_df[
    invoice_summary_df["Risk Level"] == "LOW"
]

risk1, risk2, risk3, risk4, risk5 = st.columns(5)

risk1.metric(
    "ML Anomalies",
    len(anomaly_invoices),
)

risk2.metric(
    "Critical Risk",
    len(critical_invoices),
)

risk3.metric(
    "High Risk",
    len(high_invoices),
)

risk4.metric(
    "Medium Risk",
    len(medium_invoices),
)

risk5.metric(
    "Low Risk",
    len(low_invoices),
)


st.markdown("---")
st.markdown("### Financial Summary")

total_net = pd.to_numeric(
    invoice_summary_df["Net Amount"],
    errors="coerce",
).fillna(0).sum()

total_variance = pd.to_numeric(
    invoice_summary_df[
        "Reconciliation Variance"
    ],
    errors="coerce",
).fillna(0).abs().sum()

priority_value = pd.to_numeric(
    invoice_summary_df[
        invoice_summary_df["Risk Level"].isin(
            [
                "CRITICAL",
                "HIGH",
                "MEDIUM",
            ]
        )
    ]["Net Amount"],
    errors="coerce",
).fillna(0).sum()

finance1, finance2, finance3 = st.columns(3)

finance1.metric(
    "Total Invoice Net",
    format_currency(total_net),
)

finance2.metric(
    "Total Absolute Variance",
    format_currency(total_variance),
)

finance3.metric(
    "Priority Review Value",
    format_currency(priority_value),
)


st.markdown("---")
st.markdown("### Risk Distribution")

risk_distribution = (
    invoice_summary_df["Risk Level"]
    .value_counts()
    .reindex(
        [
            "CRITICAL",
            "HIGH",
            "MEDIUM",
            "LOW",
        ],
        fill_value=0,
    )
)

st.bar_chart(risk_distribution)


st.markdown("---")
st.markdown("### Priority Review Queue")

priority_df = invoice_summary_df[
    invoice_summary_df["Risk Level"].isin(
        [
            "CRITICAL",
            "HIGH",
            "MEDIUM",
        ]
    )
].sort_values(
    "Final Risk Score",
    ascending=False,
)

if priority_df.empty:
    st.success(
        "No invoices currently require priority review."
    )
else:
    priority_columns = [
        "Invoice Number",
        "Site",
        "Net Amount",
        "Anomaly Score",
        "Final Risk Score",
        "Risk Level",
        "Unusual Features",
        "Recommended Action",
    ]

    st.dataframe(
        priority_df[priority_columns],
        use_container_width=True,
        hide_index=True,
    )


st.markdown("---")
st.markdown("### Consolidated Invoice Report")

filter1, filter2, filter3 = st.columns(3)

with filter1:
    selected_risk = st.selectbox(
        "Risk Level",
        [
            "ALL",
            "CRITICAL",
            "HIGH",
            "MEDIUM",
            "LOW",
        ],
    )

with filter2:
    selected_validation = st.selectbox(
        "Validation Status",
        [
            "ALL",
            "PASSED",
            "FAILED",
        ],
    )

with filter3:
    selected_ml = st.selectbox(
        "ML Result",
        [
            "ALL",
            "ANOMALY",
            "NORMAL",
        ],
    )

filtered_report = invoice_summary_df.copy()

if selected_risk != "ALL":
    filtered_report = filtered_report[
        filtered_report["Risk Level"]
        == selected_risk
    ]

if selected_validation != "ALL":
    filtered_report = filtered_report[
        filtered_report["Validation Status"]
        == selected_validation
    ]

if selected_ml != "ALL":
    filtered_report = filtered_report[
        filtered_report["ML Result"]
        == selected_ml
    ]

filtered_report = filtered_report.sort_values(
    "Final Risk Score",
    ascending=False,
)

st.dataframe(
    filtered_report,
    use_container_width=True,
    hide_index=True,
    height=550,
)


st.markdown("---")
st.markdown("### Downloads")

download1, download2 = st.columns(2)

with download1:
    consolidated_csv = invoice_summary_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download Consolidated Invoice Report",
        data=consolidated_csv,
        file_name=(
            "d2021_consolidated_invoice_report.csv"
        ),
        mime="text/csv",
        use_container_width=True,
    )

with download2:
    zip_report = create_zip_report(
        invoice_summary_df,
        validation_df,
        reconciliation_df,
        anomaly_df,
        risk_df,
    )

    st.download_button(
        "Download Complete Report Package",
        data=zip_report,
        file_name="d2021_complete_report_package.zip",
        mime="application/zip",
        use_container_width=True,
    )


if latest_result:
    latest_result["status"] = "COMPLETED"

st.markdown("---")
st.success(
    "The complete D2021 validation, reconciliation, "
    "anomaly detection and risk analysis workflow is finished."
)
import pandas as pd
import streamlit as st


def clamp(value, minimum=0.0, maximum=100.0):
    """Keep a numeric value within the specified range."""
    return max(minimum, min(float(value), maximum))


def build_validation_lookup(validation_results):
    """Summarize validation results by invoice."""
    lookup = {}

    for result in validation_results:
        invoice_number = str(
            result.get("Invoice Number", "")
        ).strip()

        if not invoice_number:
            continue

        if invoice_number not in lookup:
            lookup[invoice_number] = {
                "critical_failures": 0,
                "warnings": 0,
                "failed_rules": [],
            }

        if result.get("Result") != "FAIL":
            continue

        severity = result.get("Severity", "")
        rule = result.get("Rule", "")

        if severity == "Critical":
            lookup[invoice_number][
                "critical_failures"
            ] += 1
        else:
            lookup[invoice_number]["warnings"] += 1

        if rule:
            lookup[invoice_number][
                "failed_rules"
            ].append(rule)

    return lookup


def build_reconciliation_lookup(reconciliation_results):
    """Create invoice reconciliation lookup."""
    return {
        str(row.get("Invoice Number", "")).strip(): row
        for row in reconciliation_results
        if row.get("Invoice Number")
    }


def build_anomaly_lookup(anomaly_results):
    """Create anomaly-result lookup."""
    return {
        str(row.get("invoice_number", "")).strip(): row
        for row in anomaly_results
        if row.get("invoice_number")
    }


def calculate_validation_score(summary):
    """
    Validation contributes a maximum of 35 points.

    Critical failure: 20 points each
    Warning: 3 points each
    """
    critical_failures = summary.get(
        "critical_failures",
        0,
    )

    warnings = summary.get("warnings", 0)

    return min(
        critical_failures * 20 + warnings * 3,
        35,
    )


def calculate_reconciliation_score(row):
    """
    Reconciliation contributes a maximum of 35 points.
    """
    if not row:
        return 10.0

    status = row.get("Status", "")

    if status.startswith("INVALID"):
        return 35.0

    absolute_variance = float(
        row.get("Absolute Variance") or 0
    )

    variance_percentage = float(
        row.get("Variance %") or 0
    )

    if status == "MATCHED":
        return 0.0

    monetary_score = min(
        absolute_variance / 10,
        20,
    )

    percentage_score = min(
        variance_percentage,
        15,
    )

    return clamp(
        monetary_score + percentage_score,
        maximum=35,
    )


def calculate_anomaly_score(row):
    """
    ML anomaly contributes a maximum of 30 points.
    """
    if not row:
        return 0.0

    raw_score = clamp(
        row.get("anomaly_score", 0)
    )

    model_prediction = row.get(
        "model_prediction",
        1,
    )

    if model_prediction == -1:
        return raw_score * 0.30

    return raw_score * 0.10


def assign_risk_level(score):
    """Convert final score into a risk level."""
    if score >= 75:
        return "CRITICAL"

    if score >= 50:
        return "HIGH"

    if score >= 25:
        return "MEDIUM"

    return "LOW"


def recommended_action(risk_level):
    """Return a controlled review recommendation."""
    actions = {
        "CRITICAL": (
            "Hold the invoice for immediate manual review. "
            "Verify validation failures, charge values, MPAN "
            "details and supporting billing evidence."
        ),
        "HIGH": (
            "Perform a priority invoice review before approval. "
            "Confirm the unusual values against source billing "
            "and reference information."
        ),
        "MEDIUM": (
            "Review the highlighted features and confirm whether "
            "the variance is expected for the site and period."
        ),
        "LOW": (
            "No immediate action is required. Continue through "
            "the standard invoice-processing workflow."
        ),
    }

    return actions[risk_level]


def build_explanation(
    invoice_number,
    validation_summary,
    reconciliation_row,
    anomaly_row,
    final_score,
    risk_level,
):
    """
    Produce an evidence-based explanation.

    This explanation uses calculated evidence only and does not
    claim that an unusual invoice is incorrect or fraudulent.
    """
    evidence = []

    critical_count = validation_summary.get(
        "critical_failures",
        0,
    )

    warning_count = validation_summary.get(
        "warnings",
        0,
    )

    if critical_count:
        evidence.append(
            f"{critical_count} critical validation "
            f"failure(s) were identified"
        )
    elif warning_count:
        evidence.append(
            f"{warning_count} validation warning(s) "
            f"were identified"
        )
    else:
        evidence.append(
            "the invoice passed all critical validation rules"
        )

    if reconciliation_row:
        status = reconciliation_row.get(
            "Status",
            "UNKNOWN",
        )

        variance = float(
            reconciliation_row.get("Variance") or 0
        )

        if status == "MATCHED":
            evidence.append(
                "the BCD net amount matches the total CCD "
                "charge amount"
            )
        else:
            evidence.append(
                f"the reconciliation status is {status} "
                f"with a variance of £{variance:,.2f}"
            )

    if anomaly_row:
        anomaly_score = float(
            anomaly_row.get("anomaly_score") or 0
        )

        model_prediction = anomaly_row.get(
            "model_prediction",
            1,
        )

        unusual_features = anomaly_row.get(
            "unusual_features",
            "",
        )

        if model_prediction == -1:
            evidence.append(
                f"the ML model identified a statistically "
                f"unusual pattern with an anomaly score of "
                f"{anomaly_score:.2f}"
            )

            if unusual_features:
                evidence.append(
                    f"the most unusual features are "
                    f"{unusual_features}"
                )
        else:
            evidence.append(
                "the ML model classified the invoice within "
                "the normal pattern"
            )

    evidence_text = "; ".join(evidence)

    return (
        f"Invoice {invoice_number} has a final risk score of "
        f"{final_score:.2f}/100 and is classified as "
        f"{risk_level}. The assessment is based on the following "
        f"evidence: {evidence_text}. This risk classification "
        f"supports prioritisation and does not by itself confirm "
        f"a billing error."
    )


def create_risk_results(
    parsed_data,
    validation_results,
    reconciliation_results,
    anomaly_results,
):
    """Combine all outputs into the final risk result."""
    validation_lookup = build_validation_lookup(
        validation_results
    )

    reconciliation_lookup = (
        build_reconciliation_lookup(
            reconciliation_results
        )
    )

    anomaly_lookup = build_anomaly_lookup(
        anomaly_results
    )

    rows = []

    for invoice in parsed_data.get("invoices", []):
        invoice_number = str(
            invoice.get(
                "invoice_number",
                "MISSING",
            )
        ).strip()

        validation_summary = validation_lookup.get(
            invoice_number,
            {
                "critical_failures": 0,
                "warnings": 0,
                "failed_rules": [],
            },
        )

        reconciliation_row = (
            reconciliation_lookup.get(invoice_number)
        )

        anomaly_row = anomaly_lookup.get(
            invoice_number
        )

        validation_score = calculate_validation_score(
            validation_summary
        )

        reconciliation_score = (
            calculate_reconciliation_score(
                reconciliation_row
            )
        )

        anomaly_component = calculate_anomaly_score(
            anomaly_row
        )

        final_score = clamp(
            validation_score
            + reconciliation_score
            + anomaly_component
        )

        risk_level = assign_risk_level(final_score)

        anomaly_score = (
            float(
                anomaly_row.get(
                    "anomaly_score",
                    0,
                )
            )
            if anomaly_row
            else 0.0
        )

        model_result = (
            "ANOMALY"
            if anomaly_row
            and anomaly_row.get(
                "model_prediction"
            ) == -1
            else "NORMAL"
        )

        explanation = build_explanation(
            invoice_number,
            validation_summary,
            reconciliation_row,
            anomaly_row,
            final_score,
            risk_level,
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
                "Net Amount": abs(
                    float(
                        invoice.get(
                            "final_net",
                            0,
                        )
                        or 0
                    )
                ),
                "Validation Score": round(
                    validation_score,
                    2,
                ),
                "Reconciliation Score": round(
                    reconciliation_score,
                    2,
                ),
                "Anomaly Component": round(
                    anomaly_component,
                    2,
                ),
                "Anomaly Score": round(
                    anomaly_score,
                    2,
                ),
                "Model Result": model_result,
                "Final Risk Score": round(
                    final_score,
                    2,
                ),
                "Risk Level": risk_level,
                "Unusual Features": (
                    anomaly_row.get(
                        "unusual_features",
                        "",
                    )
                    if anomaly_row
                    else ""
                ),
                "Explanation": explanation,
                "Recommended Action": (
                    recommended_action(risk_level)
                ),
            }
        )

    return rows


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 6: Risk Scoring and Explainable AI")

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

missing_steps = []

if not parsed_data:
    missing_steps.append("Parse & Structure")

if validation_results is None:
    missing_steps.append("Data Validation")

if reconciliation_results is None:
    missing_steps.append("Invoice Reconciliation")

if anomaly_results is None:
    missing_steps.append("Anomaly Detection")

if missing_steps:
    st.warning(
        "The following steps must be completed first: "
        + ", ".join(missing_steps)
    )
    st.stop()


st.info(
    "Final risk score = Validation risk (maximum 35) + "
    "Reconciliation risk (maximum 35) + "
    "ML anomaly risk (maximum 30)."
)


with st.spinner(
    "Calculating invoice risk scores and explanations..."
):
    risk_results = create_risk_results(
        parsed_data,
        validation_results,
        reconciliation_results,
        anomaly_results,
    )

risk_df = pd.DataFrame(risk_results)

if risk_df.empty:
    st.warning("No invoice risk results were created.")
    st.stop()


critical_df = risk_df[
    risk_df["Risk Level"] == "CRITICAL"
]

high_df = risk_df[
    risk_df["Risk Level"] == "HIGH"
]

medium_df = risk_df[
    risk_df["Risk Level"] == "MEDIUM"
]

low_df = risk_df[
    risk_df["Risk Level"] == "LOW"
]


metric1, metric2, metric3, metric4, metric5 = st.columns(5)

metric1.metric(
    "Invoices Scored",
    len(risk_df),
)

metric2.metric(
    "Critical",
    len(critical_df),
)

metric3.metric(
    "High",
    len(high_df),
)

metric4.metric(
    "Medium",
    len(medium_df),
)

metric5.metric(
    "Low",
    len(low_df),
)


if len(critical_df) or len(high_df):
    st.warning(
        f"{len(critical_df) + len(high_df)} invoice(s) "
        "require priority review."
    )
else:
    st.success(
        "No invoices currently have a Critical or High "
        "combined risk score."
    )


st.markdown("---")
st.subheader("Risk Filters")

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
    selected_model_result = st.selectbox(
        "ML Result",
        [
            "ALL",
            "ANOMALY",
            "NORMAL",
        ],
    )

with filter3:
    invoice_options = (
        ["ALL"]
        + sorted(
            risk_df["Invoice Number"]
            .astype(str)
            .unique()
            .tolist()
        )
    )

    selected_invoice_filter = st.selectbox(
        "Invoice Number",
        invoice_options,
    )


filtered_df = risk_df.copy()

if selected_risk != "ALL":
    filtered_df = filtered_df[
        filtered_df["Risk Level"]
        == selected_risk
    ]

if selected_model_result != "ALL":
    filtered_df = filtered_df[
        filtered_df["Model Result"]
        == selected_model_result
    ]

if selected_invoice_filter != "ALL":
    filtered_df = filtered_df[
        filtered_df["Invoice Number"]
        == selected_invoice_filter
    ]


filtered_df = filtered_df.sort_values(
    "Final Risk Score",
    ascending=False,
)


st.markdown("---")
st.subheader("Risk Scoring Results")

summary_columns = [
    "Invoice Number",
    "Invoice Type",
    "Site",
    "Net Amount",
    "Validation Score",
    "Reconciliation Score",
    "Anomaly Component",
    "Anomaly Score",
    "Final Risk Score",
    "Risk Level",
    "Model Result",
    "Unusual Features",
]

summary_df = filtered_df[
    summary_columns
].copy()

summary_df["Net Amount"] = summary_df[
    "Net Amount"
].apply(
    lambda value: f"£{value:,.2f}"
)

st.dataframe(
    summary_df,
    use_container_width=True,
    hide_index=True,
    height=550,
)


st.markdown("---")
st.subheader("Explainable AI Detail")

detail_options = (
    risk_df.sort_values(
        "Final Risk Score",
        ascending=False,
    )["Invoice Number"]
    .astype(str)
    .tolist()
)

selected_invoice = st.selectbox(
    "Select an invoice",
    detail_options,
    key="risk_detail_invoice",
)

selected_row = risk_df[
    risk_df["Invoice Number"]
    == selected_invoice
].iloc[0]


detail1, detail2, detail3, detail4 = st.columns(4)

detail1.metric(
    "Final Risk Score",
    f"{selected_row['Final Risk Score']:.2f}/100",
)

detail2.metric(
    "Risk Level",
    selected_row["Risk Level"],
)

detail3.metric(
    "Anomaly Score",
    f"{selected_row['Anomaly Score']:.2f}",
)

detail4.metric(
    "Net Amount",
    f"£{selected_row['Net Amount']:,.2f}",
)


st.markdown("#### Evidence-based explanation")

st.write(selected_row["Explanation"])

st.markdown("#### Recommended action")

if selected_row["Risk Level"] in [
    "CRITICAL",
    "HIGH",
]:
    st.error(selected_row["Recommended Action"])

elif selected_row["Risk Level"] == "MEDIUM":
    st.warning(selected_row["Recommended Action"])

else:
    st.success(selected_row["Recommended Action"])


st.caption(
    "The explanation is generated only from validation, "
    "reconciliation and anomaly-detection evidence. "
    "Human review is required before making a billing decision."
)


st.markdown("---")
st.subheader("Risk Component Breakdown")

component_df = pd.DataFrame(
    [
        {
            "Component": "Validation Risk",
            "Maximum Score": 35,
            "Invoice Score": selected_row[
                "Validation Score"
            ],
        },
        {
            "Component": "Reconciliation Risk",
            "Maximum Score": 35,
            "Invoice Score": selected_row[
                "Reconciliation Score"
            ],
        },
        {
            "Component": "ML Anomaly Risk",
            "Maximum Score": 30,
            "Invoice Score": selected_row[
                "Anomaly Component"
            ],
        },
    ]
)

st.dataframe(
    component_df,
    use_container_width=True,
    hide_index=True,
)


st.markdown("---")
st.subheader("Priority Review Queue")

priority_df = risk_df[
    risk_df["Risk Level"].isin(
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
    st.dataframe(
        priority_df[
            [
                "Invoice Number",
                "Site",
                "Net Amount",
                "Final Risk Score",
                "Risk Level",
                "Unusual Features",
                "Recommended Action",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


csv_data = risk_df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "Download Risk and Explanation Results",
    data=csv_data,
    file_name="d2021_risk_explanation_results.csv",
    mime="text/csv",
    use_container_width=True,
)


st.session_state.risk_results = (
    risk_df.to_dict(orient="records")
)

st.session_state.risk_summary = {
    "invoices_scored": len(risk_df),
    "critical": len(critical_df),
    "high": len(high_df),
    "medium": len(medium_df),
    "low": len(low_df),
}

latest_result = st.session_state.get(
    "latest_result"
)

if latest_result:
    latest_result["status"] = (
        "RISK_SCORING_COMPLETED"
    )

st.markdown("---")
st.success(
    "Risk scoring and evidence-based explanations are complete."
)
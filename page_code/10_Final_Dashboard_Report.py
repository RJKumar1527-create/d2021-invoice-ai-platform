import io
import json
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from review_database import (
    get_all_reviews,
    get_review_summary,
    initialise_database,
)


def safe_dataframe(data):
    """Convert stored records into a DataFrame."""
    return pd.DataFrame(data or [])


def safe_float(value, default=0.0):
    """Convert a value safely to float."""
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def format_currency(value):
    """Format a value as GBP."""
    return f"£{safe_float(value):,.2f}"


def make_alias_lookup(risk_df, retrieval_results, explanation_results):
    """Create stable masked aliases without exposing invoice numbers."""
    lookup = {}

    for invoice_number, record in (retrieval_results or {}).items():
        alias = record.get("safe_invoice_alias")
        if alias:
            lookup[str(invoice_number)] = alias

    for invoice_number, record in (explanation_results or {}).items():
        alias = record.get("safe_invoice_alias")
        if alias:
            lookup[str(invoice_number)] = alias

    if not risk_df.empty and "Invoice Number" in risk_df.columns:
        for position, invoice_number in enumerate(
            risk_df["Invoice Number"].astype(str).tolist(),
            start=1,
        ):
            lookup.setdefault(
                invoice_number,
                f"INV-{position:05d}",
            )

    return lookup


def build_validation_lookup(validation_df):
    """Summarize validation results per invoice."""
    lookup = {}

    if validation_df.empty or "Invoice Number" not in validation_df.columns:
        return lookup

    for invoice_number, group in validation_df.groupby("Invoice Number"):
        failed = group[group["Result"] == "FAIL"]
        critical = len(failed[failed["Severity"] == "Critical"])
        warnings = len(failed[failed["Severity"] == "Warning"])

        lookup[str(invoice_number)] = {
            "validation_status": "FAILED" if critical else "PASSED",
            "critical_failures": critical,
            "validation_warnings": warnings,
        }

    return lookup


def build_consolidated_report(
    risk_df,
    validation_df,
    reconciliation_df,
    anomaly_df,
    retrieval_results,
    explanation_results,
    reviews,
):
    """Create one portfolio-safe row per invoice."""
    alias_lookup = make_alias_lookup(
        risk_df,
        retrieval_results,
        explanation_results,
    )
    validation_lookup = build_validation_lookup(validation_df)

    reconciliation_lookup = {
        str(row["Invoice Number"]): row
        for _, row in reconciliation_df.iterrows()
    } if not reconciliation_df.empty else {}

    anomaly_lookup = {
        str(row["invoice_number"]): row
        for _, row in anomaly_df.iterrows()
    } if not anomaly_df.empty else {}

    explanation_lookup = {
        str(invoice_number): record
        for invoice_number, record in (explanation_results or {}).items()
    }

    review_lookup = {
        str(review["invoice_number"]): review
        for review in reviews
    }

    rows = []

    for _, risk in risk_df.iterrows():
        invoice_number = str(risk.get("Invoice Number", ""))
        alias = alias_lookup.get(invoice_number, "INV-UNKNOWN")
        validation = validation_lookup.get(invoice_number, {})
        reconciliation = reconciliation_lookup.get(invoice_number, {})
        anomaly = anomaly_lookup.get(invoice_number, {})
        explanation_record = explanation_lookup.get(invoice_number, {})
        explanation = explanation_record.get("explanation", {})
        review = review_lookup.get(invoice_number, {})

        rows.append(
            {
                "Safe Invoice Alias": alias,
                "Invoice Type": risk.get("Invoice Type", ""),
                "Net Amount": safe_float(risk.get("Net Amount")),
                "Validation Status": validation.get(
                    "validation_status",
                    "NOT AVAILABLE",
                ),
                "Critical Failures": validation.get("critical_failures", 0),
                "Validation Warnings": validation.get("validation_warnings", 0),
                "Reconciliation Status": reconciliation.get(
                    "Status",
                    "NOT AVAILABLE",
                ),
                "Reconciliation Variance": safe_float(
                    reconciliation.get("Variance")
                ),
                "Anomaly Score": safe_float(
                    anomaly.get("anomaly_score", risk.get("Anomaly Score"))
                ),
                "ML Result": risk.get("Model Result", ""),
                "System Risk Level": risk.get("Risk Level", ""),
                "Final Risk Score": safe_float(risk.get("Final Risk Score")),
                "Unusual Features": risk.get("Unusual Features", ""),
                "Retrieval Method": explanation_record.get(
                    "retrieval_method",
                    "NOT RUN",
                ),
                "Generation Method": explanation_record.get(
                    "generation_method",
                    "NOT RUN",
                ),
                "Successful Model": explanation_record.get(
                    "successful_model",
                    "NOT RUN",
                ),
                "AI Confidence": safe_float(
                    explanation.get("confidence_score")
                ),
                "AI Explanation Available": "YES" if explanation else "NO",
                "Review Decision": review.get("decision", "NOT REVIEWED"),
                "Review Status": review.get("review_status", "NOT REVIEWED"),
                "Effective Risk": review.get(
                    "effective_risk_level",
                    risk.get("Risk Level", ""),
                ),
                "Assigned Owner": review.get("assigned_owner", ""),
                "Due Date": review.get("due_date", ""),
                "AI Assessment": review.get("ai_assessment", "NOT REVIEWED"),
                "Reviewer": review.get("reviewer_name", ""),
                "Reviewed At": review.get("updated_at", ""),
            }
        )

    return pd.DataFrame(rows)


def create_report_package(
    consolidated_df,
    validation_df,
    reconciliation_df,
    anomaly_df,
    risk_df,
    reviews_df,
    explanation_results,
    review_summary,
):
    """Return an in-memory ZIP containing the full safe report package."""
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as report_zip:
        csv_files = {
            "consolidated_invoice_report.csv": consolidated_df,
            "validation_results.csv": validation_df,
            "reconciliation_results.csv": reconciliation_df,
            "anomaly_results.csv": anomaly_df,
            "risk_results.csv": risk_df,
            "human_review_queue.csv": reviews_df,
        }

        for file_name, dataframe in csv_files.items():
            report_zip.writestr(
                file_name,
                dataframe.to_csv(index=False),
            )

        safe_explanations = []
        for record in (explanation_results or {}).values():
            safe_explanations.append(
                {
                    "safe_invoice_alias": record.get("safe_invoice_alias"),
                    "generation_method": record.get("generation_method"),
                    "successful_model": record.get("successful_model"),
                    "retrieval_method": record.get("retrieval_method"),
                    "explanation": record.get("explanation", {}),
                }
            )

        report_zip.writestr(
            "grounded_ai_explanations.json",
            json.dumps(safe_explanations, ensure_ascii=False, indent=2),
        )
        report_zip.writestr(
            "human_review_summary.json",
            json.dumps(review_summary, ensure_ascii=False, indent=2),
        )

    buffer.seek(0)
    return buffer.getvalue()


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 10: Final Dashboard & Report")

initialise_database()

latest_result = st.session_state.get("latest_result", {})
parsed_data = st.session_state.get("parsed_d2021")
validation_results = st.session_state.get("validation_results")
reconciliation_results = st.session_state.get("reconciliation_results")
anomaly_results = st.session_state.get("anomaly_results")
risk_results = st.session_state.get("risk_results")
retrieval_results = st.session_state.get("rag_retrieval_results", {})
explanation_results = st.session_state.get("grounded_ai_explanations", {})

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
    missing_steps.append("Risk Scoring")

if missing_steps:
    st.warning(
        "Complete these workflow steps first: "
        + ", ".join(missing_steps)
    )
    st.stop()

validation_df = safe_dataframe(validation_results)
reconciliation_df = safe_dataframe(reconciliation_results)
anomaly_df = safe_dataframe(anomaly_results)
risk_df = safe_dataframe(risk_results)
reviews = get_all_reviews()
reviews_df = safe_dataframe(reviews)
review_summary = get_review_summary()

consolidated_df = build_consolidated_report(
    risk_df,
    validation_df,
    reconciliation_df,
    anomaly_df,
    retrieval_results,
    explanation_results,
    reviews,
)

st.caption(
    "Portfolio-safe dashboard: reports use masked aliases. Original invoice "
    "numbers, MPANs, customer names and addresses are excluded from the "
    "consolidated downloads."
)

if latest_result:
    st.info(
        f"File: {latest_result.get('file_name', 'Unknown')} | "
        f"Processing ID: {latest_result.get('processing_id', 'Unknown')}"
    )

st.markdown("### Processing Overview")
overview1, overview2, overview3, overview4 = st.columns(4)
overview1.metric("Invoices", len(consolidated_df))
overview2.metric(
    "MPAN Records",
    sum(len(site.get("mpans", [])) for site in parsed_data.get("sites", [])),
)
overview3.metric(
    "Charge Records",
    sum(
        len(invoice.get("charges", []))
        for invoice in parsed_data.get("invoices", [])
    ),
)
overview4.metric("Parsing Errors", len(parsed_data.get("errors", [])))

st.markdown("---")
st.markdown("### Validation & Reconciliation")
validation1, validation2, validation3, validation4 = st.columns(4)
validation1.metric(
    "Validation Passed",
    int((consolidated_df["Validation Status"] == "PASSED").sum()),
)
validation2.metric(
    "Validation Failed",
    int((consolidated_df["Validation Status"] == "FAILED").sum()),
)
validation3.metric(
    "Reconciliation Matched",
    int((consolidated_df["Reconciliation Status"] == "MATCHED").sum()),
)
validation4.metric(
    "Reconciliation Mismatched",
    int((consolidated_df["Reconciliation Status"] == "MISMATCHED").sum()),
)

st.markdown("---")
st.markdown("### AI Pipeline Coverage")
ai1, ai2, ai3, ai4 = st.columns(4)
ai1.metric(
    "ML Anomalies",
    int((consolidated_df["ML Result"] == "ANOMALY").sum()),
)
ai2.metric("RAG Retrievals", len(retrieval_results))
ai3.metric("AI Explanations", len(explanation_results))
ai4.metric(
    "Average AI Confidence",
    (
        f"{consolidated_df.loc[consolidated_df['AI Explanation Available'] == 'YES', 'AI Confidence'].mean():.0%}"
        if (consolidated_df["AI Explanation Available"] == "YES").any()
        else "N/A"
    ),
)

st.markdown("---")
st.markdown("### Human Review Summary")
review1, review2, review3, review4, review5 = st.columns(5)
review1.metric("Reviews Saved", int(review_summary.get("total_reviews") or 0))
review2.metric("Completed", int(review_summary.get("completed") or 0))
review3.metric(
    "Needs Investigation",
    int(review_summary.get("needs_investigation") or 0),
)
review4.metric(
    "Query Required",
    int(review_summary.get("query_required") or 0),
)
review5.metric(
    "False Positives",
    int(review_summary.get("false_positives") or 0),
)

st.markdown("---")
st.markdown("### Financial & Priority Summary")
total_net = consolidated_df["Net Amount"].sum()
total_variance = consolidated_df["Reconciliation Variance"].abs().sum()
priority_mask = consolidated_df["Effective Risk"].isin(
    ["CRITICAL", "HIGH", "MEDIUM"]
)
priority_value = consolidated_df.loc[priority_mask, "Net Amount"].sum()
unreviewed_priority = int(
    (
        priority_mask
        & (consolidated_df["Review Status"] == "NOT REVIEWED")
    ).sum()
)

finance1, finance2, finance3, finance4 = st.columns(4)
finance1.metric("Total Invoice Net", format_currency(total_net))
finance2.metric("Total Absolute Variance", format_currency(total_variance))
finance3.metric("Priority Review Value", format_currency(priority_value))
finance4.metric("Unreviewed Priority", unreviewed_priority)

st.markdown("---")
st.markdown("### Effective Risk Distribution")
risk_distribution = (
    consolidated_df["Effective Risk"]
    .value_counts()
    .reindex(["CRITICAL", "HIGH", "MEDIUM", "LOW"], fill_value=0)
)
st.bar_chart(risk_distribution)

st.markdown("---")
st.markdown("### Human Review Queue")
if reviews_df.empty:
    st.info("No persistent human reviews have been saved yet.")
else:
    safe_review_columns = [
        "safe_invoice_alias",
        "decision",
        "review_status",
        "original_risk_level",
        "effective_risk_level",
        "reviewer_name",
        "assigned_owner",
        "due_date",
        "ai_assessment",
        "updated_at",
    ]
    safe_reviews_df = reviews_df[safe_review_columns].rename(
        columns={
            "safe_invoice_alias": "Safe Invoice Alias",
            "decision": "Decision",
            "review_status": "Status",
            "original_risk_level": "Original Risk",
            "effective_risk_level": "Effective Risk",
            "reviewer_name": "Reviewer",
            "assigned_owner": "Assigned Owner",
            "due_date": "Due Date",
            "ai_assessment": "AI Assessment",
            "updated_at": "Updated At",
        }
    )
    st.dataframe(
        safe_reviews_df,
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")
st.markdown("### Priority Review Queue")
priority_df = consolidated_df[priority_mask].sort_values(
    "Final Risk Score",
    ascending=False,
)

if priority_df.empty:
    st.success("No invoices currently require priority review.")
else:
    priority_columns = [
        "Safe Invoice Alias",
        "Net Amount",
        "Anomaly Score",
        "Final Risk Score",
        "System Risk Level",
        "Effective Risk",
        "Generation Method",
        "AI Confidence",
        "Review Decision",
        "Review Status",
        "Assigned Owner",
        "Due Date",
    ]
    priority_display = priority_df[priority_columns].copy()
    priority_display["Net Amount"] = priority_display["Net Amount"].map(
        format_currency
    )
    priority_display["AI Confidence"] = priority_display["AI Confidence"].map(
        lambda value: f"{value:.0%}" if value > 0 else "N/A"
    )
    st.dataframe(
        priority_display,
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")
st.markdown("### Consolidated Portfolio-Safe Report")
filter1, filter2, filter3, filter4 = st.columns(4)

with filter1:
    selected_risk = st.selectbox(
        "Effective Risk",
        ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
    )
with filter2:
    selected_review = st.selectbox(
        "Review Status",
        [
            "ALL",
            "NOT REVIEWED",
            "NEW",
            "UNDER REVIEW",
            "AWAITING INFORMATION",
            "QUERY RAISED",
            "RESOLVED",
            "CLOSED",
        ],
    )
with filter3:
    selected_ml = st.selectbox(
        "ML Result",
        ["ALL", "ANOMALY", "NORMAL"],
    )
with filter4:
    selected_ai = st.selectbox(
        "AI Explanation",
        ["ALL", "YES", "NO"],
    )

filtered_df = consolidated_df.copy()
if selected_risk != "ALL":
    filtered_df = filtered_df[
        filtered_df["Effective Risk"] == selected_risk
    ]
if selected_review != "ALL":
    filtered_df = filtered_df[
        filtered_df["Review Status"] == selected_review
    ]
if selected_ml != "ALL":
    filtered_df = filtered_df[
        filtered_df["ML Result"] == selected_ml
    ]
if selected_ai != "ALL":
    filtered_df = filtered_df[
        filtered_df["AI Explanation Available"] == selected_ai
    ]

filtered_df = filtered_df.sort_values(
    "Final Risk Score",
    ascending=False,
)
st.dataframe(
    filtered_df,
    use_container_width=True,
    hide_index=True,
    height=550,
)

st.markdown("---")
st.markdown("### Downloads")
download1, download2 = st.columns(2)

with download1:
    st.download_button(
        "Download Portfolio-Safe Consolidated Report",
        data=consolidated_df.to_csv(index=False).encode("utf-8"),
        file_name="d2021_portfolio_safe_report.csv",
        mime="text/csv",
        use_container_width=True,
    )

with download2:
    report_package = create_report_package(
        consolidated_df,
        validation_df,
        reconciliation_df,
        anomaly_df,
        risk_df,
        reviews_df,
        explanation_results,
        review_summary,
    )
    st.download_button(
        "Download Complete Report Package",
        data=report_package,
        file_name="d2021_complete_report_package.zip",
        mime="application/zip",
        use_container_width=True,
    )

if latest_result:
    latest_result["status"] = "COMPLETED"

st.markdown("---")
st.success(
    "The final dashboard now includes validation, reconciliation, ML "
    "anomalies, RAG coverage, grounded AI explanations, persistent human "
    "reviews and effective post-review risk."
)

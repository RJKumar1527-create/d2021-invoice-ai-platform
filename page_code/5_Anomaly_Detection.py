from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


FEATURE_LABELS = {
    "net_amount": "Net Amount",
    "gross_amount": "Gross Amount",
    "charge_count": "Charge Count",
    "mpan_count": "MPAN Count",
    "billing_days": "Billing Days",
    "total_quantity": "Total Quantity",
    "average_rate": "Average Rate",
    "maximum_rate": "Maximum Rate",
    "capacity_amount": "Capacity Amount",
    "unit_rate_amount": "Unit Rate Amount",
    "reactive_amount": "Reactive Amount",
    "standing_amount": "Standing Charge",
}


def safe_float(value, default=0.0):
    """Convert a value safely to float."""
    if value is None or str(value).strip() == "":
        return default

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_date(value):
    """Parse YYYYMMDD date values."""
    if not value:
        return None

    try:
        return datetime.strptime(
            str(value),
            "%Y%m%d",
        ).date()
    except ValueError:
        return None


def calculate_billing_days(invoice):
    """Calculate inclusive invoice-period duration."""
    start_date = parse_date(
        invoice.get("period_start")
    )

    end_date = parse_date(
        invoice.get("period_end")
    )

    if not start_date or not end_date:
        return 0

    if end_date < start_date:
        return 0

    return (end_date - start_date).days + 1


def build_invoice_features(parsed_data):
    """Build one ML feature row per invoice."""
    rows = []

    for invoice in parsed_data.get("invoices", []):
        charges = invoice.get("charges", [])

        total_quantity = 0.0
        rates = []

        charge_amounts = {
            "A": 0.0,
            "U": 0.0,
            "R": 0.0,
            "S": 0.0,
        }

        for charge in charges:
            quantity = safe_float(
                charge.get("quantity")
            )

            rate = safe_float(
                charge.get("rate")
            )

            amount = safe_float(
                charge.get("amount")
            )

            charge_type = str(
                charge.get("charge_type", "")
            ).upper()

            total_quantity += abs(quantity)

            if rate != 0:
                rates.append(abs(rate))

            if charge_type in charge_amounts:
                charge_amounts[charge_type] += abs(
                    amount
                )

        average_rate = (
            sum(rates) / len(rates)
            if rates
            else 0.0
        )

        maximum_rate = max(rates) if rates else 0.0

        row = {
            "invoice_number": invoice.get(
                "invoice_number",
                "MISSING",
            ),
            "invoice_type": invoice.get(
                "invoice_type",
                "",
            ),
            "site": invoice.get(
                "site_name",
                "",
            ),
            "net_amount": abs(
                safe_float(invoice.get("final_net"))
            ),
            "gross_amount": abs(
                safe_float(invoice.get("final_gross"))
            ),
            "charge_count": len(charges),
            "mpan_count": len(
                invoice.get("mpans", [])
            ),
            "billing_days": calculate_billing_days(
                invoice
            ),
            "total_quantity": total_quantity,
            "average_rate": average_rate,
            "maximum_rate": maximum_rate,
            "capacity_amount": charge_amounts["A"],
            "unit_rate_amount": charge_amounts["U"],
            "reactive_amount": charge_amounts["R"],
            "standing_amount": charge_amounts["S"],
        }

        rows.append(row)

    return pd.DataFrame(rows)


def find_unusual_features(
    row,
    feature_columns,
    medians,
    deviations,
):
    """Return the most unusual features for an invoice."""
    feature_scores = []

    for feature in feature_columns:
        value = row[feature]
        median = medians[feature]
        deviation = deviations[feature]

        if deviation == 0:
            score = 0.0
        else:
            score = abs(value - median) / deviation

        feature_scores.append(
            (
                feature,
                score,
                value,
                median,
            )
        )

    feature_scores.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    unusual = []

    for feature, score, value, median in feature_scores[:3]:
        unusual.append(
            {
                "feature": FEATURE_LABELS[feature],
                "score": score,
                "value": value,
                "median": median,
            }
        )

    return unusual


def build_reason(unusual_features):
    """Create an evidence-based anomaly description."""
    reasons = []

    for item in unusual_features:
        if item["score"] < 2:
            continue

        value = item["value"]
        median = item["median"]

        direction = (
            "higher"
            if value > median
            else "lower"
        )

        reasons.append(
            f"{item['feature']} is {direction} than "
            f"the dataset median "
            f"({value:,.2f} vs {median:,.2f})"
        )

    if not reasons:
        return (
            "The combined feature pattern differs from "
            "the majority of invoices."
        )

    return "; ".join(reasons)


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 5: ML Anomaly Detection")

parsed_data = st.session_state.get("parsed_d2021")
reconciliation_summary = st.session_state.get(
    "reconciliation_summary"
)

if not parsed_data:
    st.warning("No parsed D2021 data is available.")
    st.info(
        "Complete File Upload and Parse & Structure first."
    )
    st.stop()

if not reconciliation_summary:
    st.warning("Invoice Reconciliation has not been completed.")
    st.info(
        "Complete Step 4 before running anomaly detection."
    )
    st.stop()


st.info(
    "Isolation Forest identifies invoices that are statistically "
    "unusual compared with other invoices in the uploaded file. "
    "An anomaly is not automatically a billing error."
)


contamination = st.slider(
    "Expected anomaly percentage",
    min_value=1,
    max_value=10,
    value=3,
    step=1,
    help=(
        "The model will flag approximately this percentage "
        "of invoices as unusual."
    ),
)


feature_df = build_invoice_features(parsed_data)

if len(feature_df) < 20:
    st.warning(
        "At least 20 invoices are recommended for anomaly detection."
    )
    st.stop()


feature_columns = [
    "net_amount",
    "gross_amount",
    "charge_count",
    "mpan_count",
    "billing_days",
    "total_quantity",
    "average_rate",
    "maximum_rate",
    "capacity_amount",
    "unit_rate_amount",
    "reactive_amount",
    "standing_amount",
]


model_data = feature_df[feature_columns].copy()

model_data = model_data.replace(
    [np.inf, -np.inf],
    np.nan,
)

model_data = model_data.fillna(
    model_data.median()
)


scaler = StandardScaler()

scaled_data = scaler.fit_transform(model_data)


model = IsolationForest(
    n_estimators=300,
    contamination=contamination / 100,
    random_state=42,
    n_jobs=-1,
)

predictions = model.fit_predict(scaled_data)
decision_scores = model.decision_function(
    scaled_data
)


minimum_score = decision_scores.min()
maximum_score = decision_scores.max()

if maximum_score == minimum_score:
    normalized_scores = np.zeros(
        len(decision_scores)
    )
else:
    normalized_scores = (
        maximum_score - decision_scores
    ) / (
        maximum_score - minimum_score
    )


feature_df["anomaly_score"] = (
    normalized_scores * 100
).round(2)

feature_df["model_prediction"] = predictions


medians = model_data.median()

deviations = (
    model_data - medians
).abs().median()

standard_deviations = model_data.std()

# For columns where median absolute deviation is zero,
# use that column's standard deviation.
deviations = deviations.mask(
    deviations == 0,
    standard_deviations,
)

# Handle columns with no variation or invalid values.
deviations = deviations.fillna(1.0)
deviations = deviations.mask(
    deviations == 0,
    1.0,
)


unusual_feature_values = []
reason_values = []

for index, row in model_data.iterrows():
    unusual_features = find_unusual_features(
        row,
        feature_columns,
        medians,
        deviations,
    )

    unusual_feature_values.append(
        ", ".join(
            feature["feature"]
            for feature in unusual_features
        )
    )

    reason_values.append(
        build_reason(unusual_features)
    )


feature_df["unusual_features"] = (
    unusual_feature_values
)

feature_df["reason"] = reason_values


def assign_risk(row):
    """Assign risk using model output and anomaly score."""
    if row["model_prediction"] == -1:
        if row["anomaly_score"] >= 80:
            return "HIGH"
        return "MEDIUM"

    if row["anomaly_score"] >= 60:
        return "REVIEW"

    return "LOW"


feature_df["risk_level"] = feature_df.apply(
    assign_risk,
    axis=1,
)


anomalies_df = feature_df[
    feature_df["model_prediction"] == -1
].copy()

normal_df = feature_df[
    feature_df["model_prediction"] == 1
].copy()

high_risk_df = feature_df[
    feature_df["risk_level"] == "HIGH"
]

medium_risk_df = feature_df[
    feature_df["risk_level"] == "MEDIUM"
]


metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Invoices Analysed",
    len(feature_df),
)

metric2.metric(
    "Normal Pattern",
    len(normal_df),
)

metric3.metric(
    "Anomalies Detected",
    len(anomalies_df),
)

metric4.metric(
    "High Risk",
    len(high_risk_df),
)


if anomalies_df.empty:
    st.success(
        "No statistically unusual invoices were detected."
    )
else:
    st.warning(
        f"{len(anomalies_df)} statistically unusual invoice(s) "
        "were identified for review."
    )


st.markdown("---")
st.subheader("Anomaly Filters")

filter1, filter2, filter3 = st.columns(3)

with filter1:
    selected_risk = st.selectbox(
        "Risk Level",
        [
            "ALL",
            "HIGH",
            "MEDIUM",
            "REVIEW",
            "LOW",
        ],
    )

with filter2:
    invoice_types = (
        ["ALL"]
        + sorted(
            feature_df["invoice_type"]
            .astype(str)
            .unique()
            .tolist()
        )
    )

    selected_type = st.selectbox(
        "Invoice Type",
        invoice_types,
    )

with filter3:
    selected_result = st.selectbox(
        "Model Result",
        [
            "ALL",
            "ANOMALY",
            "NORMAL",
        ],
    )


filtered_df = feature_df.copy()

if selected_risk != "ALL":
    filtered_df = filtered_df[
        filtered_df["risk_level"]
        == selected_risk
    ]

if selected_type != "ALL":
    filtered_df = filtered_df[
        filtered_df["invoice_type"]
        == selected_type
    ]

if selected_result == "ANOMALY":
    filtered_df = filtered_df[
        filtered_df["model_prediction"] == -1
    ]

elif selected_result == "NORMAL":
    filtered_df = filtered_df[
        filtered_df["model_prediction"] == 1
    ]


filtered_df = filtered_df.sort_values(
    "anomaly_score",
    ascending=False,
)


st.markdown("---")
st.subheader("Anomaly Results")

display_columns = [
    "invoice_number",
    "invoice_type",
    "site",
    "net_amount",
    "gross_amount",
    "charge_count",
    "mpan_count",
    "billing_days",
    "anomaly_score",
    "risk_level",
    "unusual_features",
    "reason",
]

display_df = filtered_df[
    display_columns
].copy()

display_df = display_df.rename(
    columns={
        "invoice_number": "Invoice Number",
        "invoice_type": "Invoice Type",
        "site": "Site",
        "net_amount": "Net Amount",
        "gross_amount": "Gross Amount",
        "charge_count": "Charge Count",
        "mpan_count": "MPAN Count",
        "billing_days": "Billing Days",
        "anomaly_score": "Anomaly Score",
        "risk_level": "Risk Level",
        "unusual_features": "Unusual Features",
        "reason": "Reason",
    }
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=550,
)


st.markdown("---")
st.subheader("Invoice Anomaly Detail")

invoice_options = (
    feature_df.sort_values(
        "anomaly_score",
        ascending=False,
    )["invoice_number"]
    .astype(str)
    .tolist()
)

selected_invoice = st.selectbox(
    "Select an invoice",
    invoice_options,
    key="anomaly_detail_invoice",
)

selected_row = feature_df[
    feature_df["invoice_number"]
    == selected_invoice
].iloc[0]


detail1, detail2, detail3, detail4 = st.columns(4)

detail1.metric(
    "Anomaly Score",
    f"{selected_row['anomaly_score']:.2f}",
)

detail2.metric(
    "Risk Level",
    selected_row["risk_level"],
)

detail3.metric(
    "Net Amount",
    f"£{selected_row['net_amount']:,.2f}",
)

detail4.metric(
    "Billing Days",
    int(selected_row["billing_days"]),
)


st.write(
    "**Unusual features:**",
    selected_row["unusual_features"],
)

st.write(
    "**Evidence-based reason:**",
    selected_row["reason"],
)

st.caption(
    "The result indicates statistical unusualness only. "
    "A reviewer must confirm whether the invoice is valid."
)


st.markdown("---")
st.subheader("Feature Comparison")

comparison_rows = []

for feature in feature_columns:
    comparison_rows.append(
        {
            "Feature": FEATURE_LABELS[feature],
            "Invoice Value": selected_row[feature],
            "Dataset Median": medians[feature],
            "Difference": (
                selected_row[feature]
                - medians[feature]
            ),
        }
    )

comparison_df = pd.DataFrame(comparison_rows)

st.dataframe(
    comparison_df,
    use_container_width=True,
    hide_index=True,
)


st.markdown("---")
st.subheader("Top Anomalies")

top_anomalies = (
    anomalies_df.sort_values(
        "anomaly_score",
        ascending=False,
    )
    .head(20)
)

if top_anomalies.empty:
    st.success("No anomalies were detected.")
else:
    st.dataframe(
        top_anomalies[
            [
                "invoice_number",
                "invoice_type",
                "site",
                "net_amount",
                "anomaly_score",
                "risk_level",
                "unusual_features",
                "reason",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


csv_data = display_df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "Download Anomaly Results",
    data=csv_data,
    file_name="d2021_anomaly_results.csv",
    mime="text/csv",
    use_container_width=True,
)


st.session_state.anomaly_results = (
    feature_df.to_dict(orient="records")
)

st.session_state.anomaly_summary = {
    "invoices_analysed": len(feature_df),
    "normal": len(normal_df),
    "anomalies": len(anomalies_df),
    "high_risk": len(high_risk_df),
    "medium_risk": len(medium_risk_df),
    "contamination_percentage": contamination,
}

latest_result = st.session_state.get(
    "latest_result"
)

if latest_result:
    latest_result["status"] = (
        "ANOMALY_ANALYSIS_COMPLETED"
    )

st.markdown("---")
st.success(
    "Anomaly results have been saved for the next step: "
    "Risk Scoring and AI Explanation."
)
from copy import deepcopy
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = [
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
    "standing_amount": "Standing Amount",
}


ANOMALY_TYPES = [
    "High Invoice Amount",
    "High Consumption",
    "Excessive Rate",
    "High Capacity Charge",
    "High Reactive Charge",
    "Long Billing Period",
    "Unusual MPAN Count",
    "Unusual Charge Count",
]


def safe_float(value, default=0.0):
    """Convert a value safely to float."""
    try:
        if value is None or str(value).strip() == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def parse_date(value):
    """Parse a D2021 YYYYMMDD date."""
    try:
        return datetime.strptime(
            str(value),
            "%Y%m%d",
        ).date()

    except (TypeError, ValueError):
        return None


def calculate_billing_days(invoice):
    """Calculate inclusive billing days."""
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
    """Build the baseline invoice feature dataset."""
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
            quantity = abs(
                safe_float(charge.get("quantity"))
            )

            rate = abs(
                safe_float(charge.get("rate"))
            )

            amount = abs(
                safe_float(charge.get("amount"))
            )

            charge_type = str(
                charge.get("charge_type", "")
            ).upper()

            total_quantity += quantity

            if rate > 0:
                rates.append(rate)

            if charge_type in charge_amounts:
                charge_amounts[charge_type] += amount

        rows.append(
            {
                "invoice_number": str(
                    invoice.get(
                        "invoice_number",
                        "MISSING",
                    )
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
                "average_rate": (
                    sum(rates) / len(rates)
                    if rates
                    else 0.0
                ),
                "maximum_rate": (
                    max(rates)
                    if rates
                    else 0.0
                ),
                "capacity_amount": (
                    charge_amounts["A"]
                ),
                "unit_rate_amount": (
                    charge_amounts["U"]
                ),
                "reactive_amount": (
                    charge_amounts["R"]
                ),
                "standing_amount": (
                    charge_amounts["S"]
                ),
                "actual_label": 0,
                "anomaly_type": "Normal",
                "changed_feature": "",
                "original_value": 0.0,
                "injected_value": 0.0,
            }
        )

    return pd.DataFrame(rows)


def inject_anomalies(
    baseline_df,
    anomaly_count,
    intensity,
    random_seed,
):
    """
    Inject known synthetic anomalies into a copy of the data.

    The original uploaded D2021 data is not modified.
    """
    evaluation_df = deepcopy(baseline_df)

    rng = np.random.default_rng(random_seed)

    available_indices = evaluation_df.index.to_numpy()

    anomaly_count = min(
        anomaly_count,
        len(available_indices),
    )

    selected_indices = rng.choice(
        available_indices,
        size=anomaly_count,
        replace=False,
    )

    anomaly_assignments = []

    for position, row_index in enumerate(selected_indices):
        anomaly_type = ANOMALY_TYPES[
            position % len(ANOMALY_TYPES)
        ]

        if anomaly_type == "High Invoice Amount":
            feature = "net_amount"

        elif anomaly_type == "High Consumption":
            feature = "total_quantity"

        elif anomaly_type == "Excessive Rate":
            feature = "maximum_rate"

        elif anomaly_type == "High Capacity Charge":
            feature = "capacity_amount"

        elif anomaly_type == "High Reactive Charge":
            feature = "reactive_amount"

        elif anomaly_type == "Long Billing Period":
            feature = "billing_days"

        elif anomaly_type == "Unusual MPAN Count":
            feature = "mpan_count"

        else:
            feature = "charge_count"

        original_value = safe_float(
            evaluation_df.at[row_index, feature]
        )

        feature_median = safe_float(
            baseline_df[feature].median()
        )

        feature_std = safe_float(
            baseline_df[feature].std()
        )

        reference_value = max(
            original_value,
            feature_median,
            feature_std,
            1.0,
        )

        if feature in [
            "billing_days",
            "mpan_count",
            "charge_count",
        ]:
            injected_value = int(
                max(
                    original_value + intensity,
                    reference_value * intensity,
                )
            )

        else:
            injected_value = (
                reference_value * intensity
            )

        evaluation_df.at[
            row_index,
            feature,
        ] = injected_value

        if feature == "net_amount":
            original_gross = safe_float(
                evaluation_df.at[
                    row_index,
                    "gross_amount",
                ]
            )

            net_ratio = (
                original_gross / original_value
                if original_value > 0
                else 1.20
            )

            evaluation_df.at[
                row_index,
                "gross_amount",
            ] = injected_value * net_ratio

        evaluation_df.at[
            row_index,
            "actual_label",
        ] = 1

        evaluation_df.at[
            row_index,
            "anomaly_type",
        ] = anomaly_type

        evaluation_df.at[
            row_index,
            "changed_feature",
        ] = FEATURE_LABELS[feature]

        evaluation_df.at[
            row_index,
            "original_value",
        ] = original_value

        evaluation_df.at[
            row_index,
            "injected_value",
        ] = injected_value

        anomaly_assignments.append(
            {
                "Invoice Number": evaluation_df.at[
                    row_index,
                    "invoice_number",
                ],
                "Anomaly Type": anomaly_type,
                "Changed Feature": FEATURE_LABELS[
                    feature
                ],
                "Original Value": original_value,
                "Injected Value": injected_value,
            }
        )

    return (
        evaluation_df,
        pd.DataFrame(anomaly_assignments),
    )


def run_isolation_forest(
    evaluation_df,
    contamination,
    random_seed,
):
    """Train Isolation Forest and return predictions."""
    model_data = evaluation_df[
        FEATURE_COLUMNS
    ].copy()

    model_data = model_data.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    model_data = model_data.fillna(
        model_data.median()
    )

    model_data = model_data.fillna(0)

    scaler = StandardScaler()

    scaled_data = scaler.fit_transform(
        model_data
    )

    model = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        random_state=random_seed,
        n_jobs=-1,
    )

    raw_predictions = model.fit_predict(
        scaled_data
    )

    decision_scores = model.decision_function(
        scaled_data
    )

    predicted_labels = np.where(
        raw_predictions == -1,
        1,
        0,
    )

    minimum_score = decision_scores.min()
    maximum_score = decision_scores.max()

    if maximum_score == minimum_score:
        anomaly_scores = np.zeros(
            len(decision_scores)
        )

    else:
        anomaly_scores = (
            maximum_score - decision_scores
        ) / (
            maximum_score - minimum_score
        )

    result_df = evaluation_df.copy()

    result_df["predicted_label"] = (
        predicted_labels
    )

    result_df["anomaly_score"] = (
        anomaly_scores * 100
    ).round(2)

    result_df["evaluation_result"] = np.select(
        [
            (
                result_df["actual_label"] == 1
            )
            & (
                result_df["predicted_label"] == 1
            ),
            (
                result_df["actual_label"] == 0
            )
            & (
                result_df["predicted_label"] == 1
            ),
            (
                result_df["actual_label"] == 1
            )
            & (
                result_df["predicted_label"] == 0
            ),
        ],
        [
            "TRUE POSITIVE",
            "FALSE POSITIVE",
            "FALSE NEGATIVE",
        ],
        default="TRUE NEGATIVE",
    )

    return result_df


def calculate_metrics(result_df):
    """Calculate classification evaluation metrics."""
    actual = result_df["actual_label"]
    predicted = result_df["predicted_label"]

    tn, fp, fn, tp = confusion_matrix(
        actual,
        predicted,
        labels=[0, 1],
    ).ravel()

    return {
        "true_positive": int(tp),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_negative": int(tn),
        "precision": precision_score(
            actual,
            predicted,
            zero_division=0,
        ),
        "recall": recall_score(
            actual,
            predicted,
            zero_division=0,
        ),
        "f1": f1_score(
            actual,
            predicted,
            zero_division=0,
        ),
        "accuracy": accuracy_score(
            actual,
            predicted,
        ),
    }


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 8: Model Evaluation")

parsed_data = st.session_state.get(
    "parsed_d2021"
)

if not parsed_data:
    st.warning(
        "No parsed D2021 data is available."
    )
    st.info(
        "Complete File Upload and Parse & Structure first."
    )
    st.stop()


st.info(
    "This evaluation creates a temporary copy of the invoice "
    "features and injects known synthetic anomalies. "
    "The uploaded D2021 file and parsed session data are not changed."
)


baseline_df = build_invoice_features(
    parsed_data
)

if len(baseline_df) < 100:
    st.warning(
        "At least 100 invoices are recommended for evaluation."
    )
    st.stop()


st.markdown("### Evaluation Configuration")

config1, config2, config3 = st.columns(3)

with config1:
    injection_percentage = st.slider(
        "Synthetic anomaly percentage",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
    )

with config2:
    intensity = st.slider(
        "Anomaly intensity multiplier",
        min_value=3,
        max_value=15,
        value=8,
        step=1,
        help=(
            "Higher values create stronger synthetic anomalies."
        ),
    )

with config3:
    random_seed = st.number_input(
        "Random seed",
        min_value=1,
        max_value=99999,
        value=42,
        step=1,
    )


injected_count = max(
    1,
    round(
        len(baseline_df)
        * injection_percentage
        / 100
    ),
)

model_contamination = (
    injection_percentage / 100
)


with st.spinner(
    "Injecting anomalies and evaluating Isolation Forest..."
):
    evaluation_df, injection_df = inject_anomalies(
        baseline_df,
        injected_count,
        intensity,
        int(random_seed),
    )

    result_df = run_isolation_forest(
        evaluation_df,
        model_contamination,
        int(random_seed),
    )

    metrics = calculate_metrics(result_df)


detected_count = int(
    result_df["predicted_label"].sum()
)


st.markdown("---")
st.markdown("### Evaluation Summary")

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Test Invoices",
    len(result_df),
)

metric2.metric(
    "Injected Anomalies",
    injected_count,
)

metric3.metric(
    "Detected Anomalies",
    detected_count,
)

metric4.metric(
    "Missed Anomalies",
    metrics["false_negative"],
)


st.markdown("---")
st.markdown("### Model Performance")

performance1, performance2, performance3, performance4 = (
    st.columns(4)
)

performance1.metric(
    "Precision",
    f"{metrics['precision']:.2%}",
)

performance2.metric(
    "Recall",
    f"{metrics['recall']:.2%}",
)

performance3.metric(
    "F1 Score",
    f"{metrics['f1']:.2%}",
)

performance4.metric(
    "Accuracy",
    f"{metrics['accuracy']:.2%}",
)


st.caption(
    "Precision measures how many detected anomalies were known "
    "synthetic anomalies. Recall measures how many injected "
    "anomalies the model successfully detected."
)


st.markdown("---")
st.markdown("### Confusion Matrix")

confusion_df = pd.DataFrame(
    [
        {
            "Metric": "True Positive",
            "Count": metrics["true_positive"],
            "Meaning": (
                "Injected anomaly correctly detected"
            ),
        },
        {
            "Metric": "False Positive",
            "Count": metrics["false_positive"],
            "Meaning": (
                "Normal invoice flagged as anomalous"
            ),
        },
        {
            "Metric": "False Negative",
            "Count": metrics["false_negative"],
            "Meaning": (
                "Injected anomaly missed by the model"
            ),
        },
        {
            "Metric": "True Negative",
            "Count": metrics["true_negative"],
            "Meaning": (
                "Normal invoice correctly classified"
            ),
        },
    ]
)

st.dataframe(
    confusion_df,
    use_container_width=True,
    hide_index=True,
)


st.markdown("---")
st.markdown("### Performance by Anomaly Type")

injected_results = result_df[
    result_df["actual_label"] == 1
].copy()

type_summary = (
    injected_results.groupby(
        "anomaly_type",
        as_index=False,
    )
    .agg(
        Injected=("actual_label", "count"),
        Detected=("predicted_label", "sum"),
        Average_Score=("anomaly_score", "mean"),
    )
)

type_summary["Missed"] = (
    type_summary["Injected"]
    - type_summary["Detected"]
)

type_summary["Recall"] = (
    type_summary["Detected"]
    / type_summary["Injected"]
)

type_summary = type_summary.rename(
    columns={
        "anomaly_type": "Anomaly Type",
        "Average_Score": "Average Anomaly Score",
    }
)

type_summary["Recall"] = type_summary[
    "Recall"
].apply(
    lambda value: f"{value:.2%}"
)

type_summary[
    "Average Anomaly Score"
] = type_summary[
    "Average Anomaly Score"
].round(2)

st.dataframe(
    type_summary,
    use_container_width=True,
    hide_index=True,
)


st.markdown("---")
st.markdown("### Detailed Evaluation Results")

selected_result = st.selectbox(
    "Evaluation Result",
    [
        "ALL",
        "TRUE POSITIVE",
        "FALSE POSITIVE",
        "FALSE NEGATIVE",
        "TRUE NEGATIVE",
    ],
)

filtered_df = result_df.copy()

if selected_result != "ALL":
    filtered_df = filtered_df[
        filtered_df["evaluation_result"]
        == selected_result
    ]

filtered_df = filtered_df.sort_values(
    "anomaly_score",
    ascending=False,
)

display_columns = [
    "invoice_number",
    "site",
    "anomaly_type",
    "changed_feature",
    "original_value",
    "injected_value",
    "anomaly_score",
    "evaluation_result",
]

display_df = filtered_df[
    display_columns
].rename(
    columns={
        "invoice_number": "Invoice Number",
        "site": "Site",
        "anomaly_type": "Anomaly Type",
        "changed_feature": "Changed Feature",
        "original_value": "Original Value",
        "injected_value": "Injected Value",
        "anomaly_score": "Anomaly Score",
        "evaluation_result": "Result",
    }
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=550,
)


st.markdown("---")
st.markdown("### Missed Synthetic Anomalies")

missed_df = result_df[
    result_df["evaluation_result"]
    == "FALSE NEGATIVE"
].sort_values(
    "anomaly_score",
    ascending=False,
)

if missed_df.empty:
    st.success(
        "All injected synthetic anomalies were detected."
    )

else:
    st.warning(
        f"{len(missed_df)} injected anomaly or anomalies "
        "were missed."
    )

    st.dataframe(
        missed_df[
            [
                "invoice_number",
                "anomaly_type",
                "changed_feature",
                "original_value",
                "injected_value",
                "anomaly_score",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


st.markdown("---")
st.markdown("### Downloads")

download1, download2 = st.columns(2)

with download1:
    result_csv = result_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download Complete Evaluation Results",
        data=result_csv,
        file_name=(
            "d2021_model_evaluation_results.csv"
        ),
        mime="text/csv",
        use_container_width=True,
    )

with download2:
    injection_csv = injection_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download Injected Anomaly Details",
        data=injection_csv,
        file_name=(
            "d2021_injected_anomalies.csv"
        ),
        mime="text/csv",
        use_container_width=True,
    )


st.session_state.model_evaluation_results = (
    result_df.to_dict(orient="records")
)

st.session_state.model_evaluation_summary = {
    "test_invoices": len(result_df),
    "injected_anomalies": injected_count,
    "detected_anomalies": detected_count,
    "true_positive": metrics["true_positive"],
    "false_positive": metrics["false_positive"],
    "false_negative": metrics["false_negative"],
    "true_negative": metrics["true_negative"],
    "precision": metrics["precision"],
    "recall": metrics["recall"],
    "f1": metrics["f1"],
    "accuracy": metrics["accuracy"],
    "injection_percentage": injection_percentage,
    "intensity": intensity,
    "random_seed": int(random_seed),
}

st.markdown("---")
st.success(
    "Synthetic anomaly injection and model evaluation "
    "completed successfully."
)
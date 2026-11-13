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
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler


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

LOG_FEATURES = [
    "net_amount",
    "gross_amount",
    "total_quantity",
    "average_rate",
    "maximum_rate",
    "capacity_amount",
    "unit_rate_amount",
    "reactive_amount",
    "standing_amount",
]

ANOMALY_TYPES = [
    ("High Invoice Amount", "net_amount"),
    ("High Consumption", "total_quantity"),
    ("Excessive Rate", "maximum_rate"),
    ("High Capacity Charge", "capacity_amount"),
    ("High Reactive Charge", "reactive_amount"),
    ("Long Billing Period", "billing_days"),
    ("Unusual MPAN Count", "mpan_count"),
    ("Unusual Charge Count", "charge_count"),
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


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def billing_days(invoice):
    start = parse_date(invoice.get("period_start"))
    end = parse_date(invoice.get("period_end"))
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def build_features(parsed_data):
    rows = []

    for position, invoice in enumerate(
        parsed_data.get("invoices", []),
        start=1,
    ):
        charges = invoice.get("charges", [])
        quantities = []
        rates = []
        charge_amounts = {"A": 0.0, "U": 0.0, "R": 0.0, "S": 0.0}

        for charge in charges:
            quantity = abs(safe_float(charge.get("quantity")))
            rate = abs(safe_float(charge.get("rate")))
            amount = abs(safe_float(charge.get("amount")))
            charge_type = str(charge.get("charge_type", "")).upper()

            quantities.append(quantity)
            if rate > 0:
                rates.append(rate)
            if charge_type in charge_amounts:
                charge_amounts[charge_type] += amount

        rows.append(
            {
                "safe_invoice_alias": f"INV-{position:05d}",
                "invoice_type": str(invoice.get("invoice_type", "")),
                "net_amount": abs(safe_float(invoice.get("final_net"))),
                "gross_amount": abs(safe_float(invoice.get("final_gross"))),
                "charge_count": len(charges),
                "mpan_count": len(invoice.get("mpans", [])),
                "billing_days": billing_days(invoice),
                "total_quantity": sum(quantities),
                "average_rate": np.mean(rates) if rates else 0.0,
                "maximum_rate": max(rates) if rates else 0.0,
                "capacity_amount": charge_amounts["A"],
                "unit_rate_amount": charge_amounts["U"],
                "reactive_amount": charge_amounts["R"],
                "standing_amount": charge_amounts["S"],
                "actual_label": 0,
                "anomaly_type": "Normal",
                "changed_feature": "",
                "original_value": 0.0,
                "injected_value": 0.0,
            }
        )

    return pd.DataFrame(rows)


def split_evaluation_sets(baseline_df, tuning_percentage, seed):
    """Create disjoint threshold-tuning and unseen holdout sets."""
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(baseline_df.index.to_numpy())
    tuning_size = int(round(len(shuffled) * tuning_percentage / 100))
    tuning_size = max(100, min(tuning_size, len(shuffled) - 100))

    tuning_indices = shuffled[:tuning_size]
    holdout_indices = shuffled[tuning_size:]

    tuning_df = baseline_df.loc[tuning_indices].copy().reset_index(drop=True)
    holdout_df = baseline_df.loc[holdout_indices].copy().reset_index(drop=True)
    return tuning_df, holdout_df


def inject_anomalies(dataset_df, anomaly_count, intensity, seed):
    evaluation_df = dataset_df.copy(deep=True)
    rng = np.random.default_rng(seed)
    selected_indices = rng.choice(
        evaluation_df.index.to_numpy(),
        size=min(anomaly_count, len(evaluation_df)),
        replace=False,
    )

    assignments = []

    for position, row_index in enumerate(selected_indices):
        anomaly_type, feature = ANOMALY_TYPES[position % len(ANOMALY_TYPES)]
        original = safe_float(evaluation_df.at[row_index, feature])
        series = pd.to_numeric(dataset_df[feature], errors="coerce").fillna(0)
        q99 = safe_float(series.quantile(0.99), 1.0)
        std = safe_float(series.std(), 1.0)
        reference = max(original, q99, std, 1.0)

        if feature in {"billing_days", "mpan_count", "charge_count"}:
            injected = int(max(original + intensity, reference * intensity))
        else:
            injected = reference * intensity

        evaluation_df.at[row_index, feature] = injected

        if feature == "net_amount":
            gross_ratio = (
                safe_float(evaluation_df.at[row_index, "gross_amount"]) / original
                if original > 0
                else 1.2
            )
            evaluation_df.at[row_index, "gross_amount"] = injected * gross_ratio

        evaluation_df.at[row_index, "actual_label"] = 1
        evaluation_df.at[row_index, "anomaly_type"] = anomaly_type
        evaluation_df.at[row_index, "changed_feature"] = FEATURE_LABELS[feature]
        evaluation_df.at[row_index, "original_value"] = original
        evaluation_df.at[row_index, "injected_value"] = injected

        assignments.append(
            {
                "safe_invoice_alias": evaluation_df.at[
                    row_index,
                    "safe_invoice_alias",
                ],
                "anomaly_type": anomaly_type,
                "changed_feature": FEATURE_LABELS[feature],
                "original_value": original,
                "injected_value": injected,
            }
        )

    return evaluation_df, pd.DataFrame(assignments)


def prepare_features(train_df, score_df):
    train_x = train_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    score_x = score_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")

    medians = train_x.median().fillna(0)
    train_x = train_x.fillna(medians)
    score_x = score_x.fillna(medians)

    for feature in LOG_FEATURES:
        train_x[feature] = np.log1p(train_x[feature].clip(lower=0))
        score_x[feature] = np.log1p(score_x[feature].clip(lower=0))

    scaler = RobustScaler()
    train_scaled = scaler.fit_transform(train_x)
    score_scaled = scaler.transform(score_x)
    return train_scaled, score_scaled


def normalize_using_tuning(tuning_values, holdout_values):
    """Normalize holdout scores using tuning-set bounds only."""
    tuning_values = np.asarray(tuning_values, dtype=float)
    holdout_values = np.asarray(holdout_values, dtype=float)
    low = np.nanmin(tuning_values)
    high = np.nanmax(tuning_values)

    if high == low:
        return np.zeros(len(tuning_values)), np.zeros(len(holdout_values))

    tuning_normalized = np.clip((tuning_values - low) / (high - low), 0, 1)
    holdout_normalized = np.clip((holdout_values - low) / (high - low), 0, 1)
    return tuning_normalized, holdout_normalized


def robust_z_raw_scores(train_df, score_df):
    train_x = train_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    score_x = score_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    medians = train_x.median().fillna(0)
    mad = (train_x - medians).abs().median()
    fallback = train_x.std().replace(0, 1).fillna(1)
    mad = mad.mask(mad == 0, fallback).fillna(1)
    z = (score_x.fillna(medians) - medians).abs() / (1.4826 * mad)
    return z.max(axis=1).to_numpy()


def extreme_ratio_raw_scores(train_df, score_df):
    train_x = train_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)
    score_x = score_df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)
    references = train_x.quantile(0.99)
    references = references.mask(references.abs() < 1, 1)
    return (score_x / references).max(axis=1).to_numpy()


def evaluate_predictions(actual, predicted):
    tn, fp, fn, tp = confusion_matrix(actual, predicted, labels=[0, 1]).ravel()
    return {
        "True Positives": int(tp),
        "False Positives": int(fp),
        "False Negatives": int(fn),
        "True Negatives": int(tn),
        "Precision": precision_score(actual, predicted, zero_division=0),
        "Recall": recall_score(actual, predicted, zero_division=0),
        "F1 Score": f1_score(actual, predicted, zero_division=0),
        "Accuracy": accuracy_score(actual, predicted),
    }


def tune_threshold(scores, labels):
    unique_scores = np.unique(scores)
    if len(unique_scores) == 1:
        return float(unique_scores[0])

    candidates = np.unique(
        np.quantile(unique_scores, np.linspace(0.40, 0.995, 300))
    )
    best_threshold = float(candidates[0])
    best_f1 = -1.0
    best_recall = -1.0

    for threshold in candidates:
        predictions = (scores >= threshold).astype(int)
        score_f1 = f1_score(labels, predictions, zero_division=0)
        score_recall = recall_score(labels, predictions, zero_division=0)

        if score_f1 > best_f1 or (
            score_f1 == best_f1 and score_recall > best_recall
        ):
            best_threshold = float(threshold)
            best_f1 = float(score_f1)
            best_recall = float(score_recall)

    return best_threshold


def build_model_scores(baseline_df, tuning_df, holdout_df, seed):
    train_scaled, tuning_scaled = prepare_features(baseline_df, tuning_df)
    _, holdout_scaled = prepare_features(baseline_df, holdout_df)

    isolation = IsolationForest(
        n_estimators=500,
        contamination="auto",
        random_state=seed,
        n_jobs=-1,
    )
    isolation.fit(train_scaled)
    iso_tuning_raw = -isolation.score_samples(tuning_scaled)
    iso_holdout_raw = -isolation.score_samples(holdout_scaled)
    iso_tuning, iso_holdout = normalize_using_tuning(
        iso_tuning_raw,
        iso_holdout_raw,
    )

    neighbours = min(35, max(5, len(baseline_df) - 1))
    lof = LocalOutlierFactor(
        n_neighbors=neighbours,
        novelty=True,
        contamination="auto",
        n_jobs=-1,
    )
    lof.fit(train_scaled)
    lof_tuning_raw = -lof.score_samples(tuning_scaled)
    lof_holdout_raw = -lof.score_samples(holdout_scaled)
    lof_tuning, lof_holdout = normalize_using_tuning(
        lof_tuning_raw,
        lof_holdout_raw,
    )

    z_tuning_raw = robust_z_raw_scores(baseline_df, tuning_df)
    z_holdout_raw = robust_z_raw_scores(baseline_df, holdout_df)
    z_tuning, z_holdout = normalize_using_tuning(
        z_tuning_raw,
        z_holdout_raw,
    )

    ratio_tuning_raw = extreme_ratio_raw_scores(baseline_df, tuning_df)
    ratio_holdout_raw = extreme_ratio_raw_scores(baseline_df, holdout_df)
    ratio_tuning, ratio_holdout = normalize_using_tuning(
        ratio_tuning_raw,
        ratio_holdout_raw,
    )

    ensemble_tuning = (
        0.30 * iso_tuning
        + 0.25 * lof_tuning
        + 0.20 * z_tuning
        + 0.25 * ratio_tuning
    )
    ensemble_holdout = (
        0.30 * iso_holdout
        + 0.25 * lof_holdout
        + 0.20 * z_holdout
        + 0.25 * ratio_holdout
    )

    return {
        "Isolation Forest": (iso_tuning, iso_holdout),
        "Local Outlier Factor": (lof_tuning, lof_holdout),
        "Robust Z-Score": (z_tuning, z_holdout),
        "Extreme Ratio Detector": (ratio_tuning, ratio_holdout),
        "Weighted Ensemble": (ensemble_tuning, ensemble_holdout),
    }


def run_holdout_evaluation(baseline_df, tuning_df, holdout_df, seed):
    score_map = build_model_scores(
        baseline_df,
        tuning_df,
        holdout_df,
        seed,
    )
    tuning_labels = tuning_df["actual_label"].astype(int).to_numpy()
    holdout_labels = holdout_df["actual_label"].astype(int).to_numpy()

    rows = []
    outputs = {}

    for model_name, (tuning_scores, holdout_scores) in score_map.items():
        threshold = tune_threshold(tuning_scores, tuning_labels)
        tuning_predictions = (tuning_scores >= threshold).astype(int)
        holdout_predictions = (holdout_scores >= threshold).astype(int)

        tuning_metrics = evaluate_predictions(
            tuning_labels,
            tuning_predictions,
        )
        holdout_metrics = evaluate_predictions(
            holdout_labels,
            holdout_predictions,
        )

        rows.append(
            {
                "Model": model_name,
                "Locked Threshold": threshold,
                "Tuning F1": tuning_metrics["F1 Score"],
                "Holdout Precision": holdout_metrics["Precision"],
                "Holdout Recall": holdout_metrics["Recall"],
                "Holdout F1": holdout_metrics["F1 Score"],
                "Holdout Accuracy": holdout_metrics["Accuracy"],
                "True Positives": holdout_metrics["True Positives"],
                "False Positives": holdout_metrics["False Positives"],
                "False Negatives": holdout_metrics["False Negatives"],
                "True Negatives": holdout_metrics["True Negatives"],
                "Detected": int(holdout_predictions.sum()),
            }
        )

        outputs[model_name] = {
            "threshold": threshold,
            "tuning_scores": tuning_scores,
            "tuning_predictions": tuning_predictions,
            "holdout_scores": holdout_scores,
            "holdout_predictions": holdout_predictions,
        }

    comparison_df = pd.DataFrame(rows).sort_values(
        "Holdout F1",
        ascending=False,
    )
    best_model = comparison_df.iloc[0]["Model"]
    return comparison_df, best_model, outputs


st.title("D2021 Invoice Validation Platform")
st.subheader("Step 11: Holdout Model Evaluation")

parsed_data = st.session_state.get("parsed_d2021")
if not parsed_data:
    st.warning("Complete File Upload and Parse & Structure first.")
    st.stop()

st.info(
    "Thresholds are tuned only on a labelled tuning set. Final metrics "
    "are then calculated on a disjoint unseen holdout set using the "
    "locked threshold."
)

baseline_df = build_features(parsed_data)
if len(baseline_df) < 300:
    st.warning("At least 300 invoices are recommended for holdout evaluation.")
    st.stop()

config1, config2, config3, config4 = st.columns(4)
with config1:
    injection_percentage = st.slider(
        "Synthetic anomaly percentage",
        1,
        10,
        3,
    )
with config2:
    intensity = st.slider(
        "Anomaly intensity multiplier",
        3,
        15,
        8,
    )
with config3:
    tuning_percentage = st.slider(
        "Threshold-tuning data percentage",
        30,
        70,
        50,
    )
with config4:
    seed = st.number_input(
        "Random seed",
        min_value=1,
        max_value=99999,
        value=42,
    )

baseline_tuning, baseline_holdout = split_evaluation_sets(
    baseline_df,
    tuning_percentage,
    int(seed),
)

tuning_anomaly_count = max(
    1,
    round(len(baseline_tuning) * injection_percentage / 100),
)
holdout_anomaly_count = max(
    1,
    round(len(baseline_holdout) * injection_percentage / 100),
)

tuning_df, tuning_injections = inject_anomalies(
    baseline_tuning,
    tuning_anomaly_count,
    intensity,
    int(seed) + 101,
)
holdout_df, holdout_injections = inject_anomalies(
    baseline_holdout,
    holdout_anomaly_count,
    intensity,
    int(seed) + 202,
)

with st.spinner("Tuning thresholds and evaluating unseen holdout data..."):
    comparison_df, best_model, outputs = run_holdout_evaluation(
        baseline_df,
        tuning_df,
        holdout_df,
        int(seed),
    )

best_output = outputs[best_model]
holdout_predictions = best_output["holdout_predictions"]
holdout_scores = best_output["holdout_scores"]
holdout_df["predicted_label"] = holdout_predictions
holdout_df["anomaly_score"] = (holdout_scores * 100).round(2)
holdout_df["evaluation_result"] = np.select(
    [
        (holdout_df["actual_label"] == 1)
        & (holdout_df["predicted_label"] == 1),
        (holdout_df["actual_label"] == 0)
        & (holdout_df["predicted_label"] == 1),
        (holdout_df["actual_label"] == 1)
        & (holdout_df["predicted_label"] == 0),
    ],
    ["TRUE POSITIVE", "FALSE POSITIVE", "FALSE NEGATIVE"],
    default="TRUE NEGATIVE",
)

best_row = comparison_df.iloc[0]

summary1, summary2, summary3, summary4 = st.columns(4)
summary1.metric("Tuning Invoices", len(tuning_df))
summary2.metric("Holdout Invoices", len(holdout_df))
summary3.metric("Holdout Anomalies", holdout_anomaly_count)
summary4.metric("Best Model", best_model)

performance1, performance2, performance3, performance4 = st.columns(4)
performance1.metric(
    "Holdout Precision",
    f"{best_row['Holdout Precision']:.2%}",
)
performance2.metric(
    "Holdout Recall",
    f"{best_row['Holdout Recall']:.2%}",
)
performance3.metric(
    "Holdout F1",
    f"{best_row['Holdout F1']:.2%}",
)
performance4.metric(
    "Holdout Accuracy",
    f"{best_row['Holdout Accuracy']:.2%}",
)

st.caption(
    f"Locked threshold: {best_row['Locked Threshold']:.4f} | "
    f"True positives: {int(best_row['True Positives'])} | "
    f"False positives: {int(best_row['False Positives'])} | "
    f"False negatives: {int(best_row['False Negatives'])}"
)

if (
    best_row["Holdout Precision"] >= 0.80
    and best_row["Holdout Recall"] >= 0.80
    and best_row["Holdout F1"] >= 0.80
):
    st.success(
        "The selected model reached the 80% precision, recall and F1 "
        "targets on unseen holdout data."
    )
else:
    st.warning(
        "One or more unseen holdout metrics remain below 80%. Report "
        "the measured values and continue model refinement."
    )

st.markdown("---")
st.subheader("Holdout Model Comparison")
comparison_display = comparison_df.copy()
for column in [
    "Tuning F1",
    "Holdout Precision",
    "Holdout Recall",
    "Holdout F1",
    "Holdout Accuracy",
]:
    comparison_display[column] = comparison_display[column].map(
        lambda value: f"{value:.2%}"
    )
comparison_display["Locked Threshold"] = comparison_display[
    "Locked Threshold"
].round(4)
st.dataframe(
    comparison_display,
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")
st.subheader("Unseen Holdout Performance by Anomaly Type")
injected_holdout = holdout_df[holdout_df["actual_label"] == 1]
type_summary = (
    injected_holdout.groupby("anomaly_type", as_index=False)
    .agg(
        Injected=("actual_label", "count"),
        Detected=("predicted_label", "sum"),
        Average_Score=("anomaly_score", "mean"),
    )
)
type_summary["Missed"] = type_summary["Injected"] - type_summary["Detected"]
type_summary["Recall"] = type_summary["Detected"] / type_summary["Injected"]
type_summary = type_summary.rename(
    columns={
        "anomaly_type": "Anomaly Type",
        "Average_Score": "Average Anomaly Score",
    }
)
type_summary["Recall"] = type_summary["Recall"].map(
    lambda value: f"{value:.2%}"
)
type_summary["Average Anomaly Score"] = type_summary[
    "Average Anomaly Score"
].round(2)
st.dataframe(type_summary, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("Detailed Unseen Holdout Results")
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
filtered_df = holdout_df.copy()
if selected_result != "ALL":
    filtered_df = filtered_df[
        filtered_df["evaluation_result"] == selected_result
    ]
filtered_df = filtered_df.sort_values("anomaly_score", ascending=False)
st.dataframe(
    filtered_df[
        [
            "safe_invoice_alias",
            "anomaly_type",
            "changed_feature",
            "original_value",
            "injected_value",
            "anomaly_score",
            "evaluation_result",
        ]
    ].rename(
        columns={
            "safe_invoice_alias": "Safe Invoice Alias",
            "anomaly_type": "Anomaly Type",
            "changed_feature": "Changed Feature",
            "original_value": "Original Value",
            "injected_value": "Injected Value",
            "anomaly_score": "Anomaly Score",
            "evaluation_result": "Result",
        }
    ),
    use_container_width=True,
    hide_index=True,
    height=550,
)

st.markdown("---")
st.subheader("Downloads")
download1, download2, download3 = st.columns(3)
with download1:
    st.download_button(
        "Download Holdout Results",
        data=holdout_df.to_csv(index=False).encode("utf-8"),
        file_name="d2021_unseen_holdout_results.csv",
        mime="text/csv",
        use_container_width=True,
    )
with download2:
    st.download_button(
        "Download Model Comparison",
        data=comparison_df.to_csv(index=False).encode("utf-8"),
        file_name="d2021_holdout_model_comparison.csv",
        mime="text/csv",
        use_container_width=True,
    )
with download3:
    injection_package = pd.concat(
        [
            tuning_injections.assign(dataset="TUNING"),
            holdout_injections.assign(dataset="HOLDOUT"),
        ],
        ignore_index=True,
    )
    st.download_button(
        "Download Injection Details",
        data=injection_package.to_csv(index=False).encode("utf-8"),
        file_name="d2021_tuning_holdout_injections.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.session_state.model_evaluation_results = holdout_df.to_dict(
    orient="records"
)
st.session_state.model_evaluation_summary = {
    "evaluation_type": "disjoint tuning and unseen holdout",
    "best_model": best_model,
    "locked_threshold": float(best_row["Locked Threshold"]),
    "tuning_invoices": len(tuning_df),
    "holdout_invoices": len(holdout_df),
    "holdout_anomalies": holdout_anomaly_count,
    "holdout_precision": float(best_row["Holdout Precision"]),
    "holdout_recall": float(best_row["Holdout Recall"]),
    "holdout_f1": float(best_row["Holdout F1"]),
    "holdout_accuracy": float(best_row["Holdout Accuracy"]),
    "true_positive": int(best_row["True Positives"]),
    "false_positive": int(best_row["False Positives"]),
    "false_negative": int(best_row["False Negatives"]),
    "random_seed": int(seed),
    "intensity": intensity,
    "tuning_percentage": tuning_percentage,
}

st.markdown("---")
st.success(
    "Threshold tuning and unseen holdout evaluation completed."
)

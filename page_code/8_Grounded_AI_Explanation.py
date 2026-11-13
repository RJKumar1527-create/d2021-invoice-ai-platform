import json

import pandas as pd
import streamlit as st
from groq import Groq
from openai import OpenAI


DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-20b"


EXPLANATION_SCHEMA = {
    "name": "d2021_grounded_explanation",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "observed_evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
            "passed_controls": {
                "type": "array",
                "items": {"type": "string"},
            },
            "potential_causes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recommended_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rule_citations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "human_review_required": {"type": "boolean"},
            "limitations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "summary",
            "observed_evidence",
            "passed_controls",
            "potential_causes",
            "recommended_actions",
            "rule_citations",
            "confidence_score",
            "human_review_required",
            "limitations",
        ],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------
def get_groq_settings():
    """Read Groq configuration from Streamlit secrets."""
    try:
        api_key = st.secrets["GROQ_API_KEY"]
        model_name = st.secrets.get(
            "GROQ_CHAT_MODEL",
            DEFAULT_GROQ_MODEL,
        )
        return api_key, model_name
    except (KeyError, FileNotFoundError):
        return None, DEFAULT_GROQ_MODEL


def get_openrouter_settings():
    """Read OpenRouter configuration from Streamlit secrets."""
    try:
        api_key = st.secrets["OPENROUTER_API_KEY"]
        model_name = st.secrets.get(
            "OPENROUTER_CHAT_MODEL",
            DEFAULT_OPENROUTER_MODEL,
        )
        return api_key, model_name
    except (KeyError, FileNotFoundError):
        return None, DEFAULT_OPENROUTER_MODEL


def get_groq_client(api_key):
    """Create Groq client."""
    return Groq(
        api_key=api_key,
        timeout=45.0,
        max_retries=1,
    )


def get_openrouter_client(api_key):
    """Create OpenRouter client through its OpenAI-compatible API."""
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=60.0,
        max_retries=1,
        default_headers={
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "D2021 Invoice Validation Platform",
        },
    )


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------
def safe_float(value, default=0.0):
    """Convert a value safely to float."""
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def build_numeric_anomaly_evidence(
    selected_invoice,
    anomaly_results,
    reconciliation_results,
):
    """
    Build sanitized numerical evidence for root-cause analysis.

    No original invoice number, MPAN, site, customer or address is
    included in the returned object sent to an external provider.
    """
    anomaly_df = pd.DataFrame(anomaly_results or [])
    reconciliation_df = pd.DataFrame(reconciliation_results or [])

    if anomaly_df.empty:
        return {
            "available": False,
            "reason": "Anomaly results are unavailable.",
            "feature_comparisons": [],
            "reconciliation": {"available": False},
        }

    if "invoice_number" not in anomaly_df.columns:
        return {
            "available": False,
            "reason": "Invoice identifier is missing from anomaly results.",
            "feature_comparisons": [],
            "reconciliation": {"available": False},
        }

    invoice_match = anomaly_df[
        anomaly_df["invoice_number"].astype(str)
        == str(selected_invoice)
    ]

    if invoice_match.empty:
        return {
            "available": False,
            "reason": "The selected invoice was not found in anomaly results.",
            "feature_comparisons": [],
            "reconciliation": {"available": False},
        }

    invoice_row = invoice_match.iloc[0]
    matching_index = invoice_match.index[0]

    feature_columns = {
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

    comparisons = []

    for column, label in feature_columns.items():
        if column not in anomaly_df.columns:
            continue

        numeric_series = pd.to_numeric(
            anomaly_df[column],
            errors="coerce",
        ).dropna()

        if numeric_series.empty:
            continue

        invoice_value = safe_float(invoice_row.get(column))
        median_value = safe_float(numeric_series.median())
        mean_value = safe_float(numeric_series.mean())

        less_than_count = int((numeric_series < invoice_value).sum())
        equal_count = int((numeric_series == invoice_value).sum())
        percentile_value = (
            (less_than_count + 0.5 * equal_count)
            / len(numeric_series)
            * 100
        )

        if median_value == 0:
            percentage_difference = (
                0.0 if invoice_value == 0 else None
            )
        else:
            percentage_difference = (
                (invoice_value - median_value)
                / abs(median_value)
                * 100
            )

        comparisons.append(
            {
                "feature": label,
                "invoice_value": round(invoice_value, 2),
                "dataset_median": round(median_value, 2),
                "dataset_mean": round(mean_value, 2),
                "percentile": round(percentile_value, 2),
                "difference_from_median_percent": (
                    round(percentage_difference, 2)
                    if percentage_difference is not None
                    else None
                ),
            }
        )

    comparisons.sort(
        key=lambda item: (
            abs(item["difference_from_median_percent"])
            if item["difference_from_median_percent"] is not None
            else abs(item["percentile"] - 50)
        ),
        reverse=True,
    )

    unusual_feature_names = {
        feature.strip()
        for feature in str(
            invoice_row.get("unusual_features", "")
        ).split(",")
        if feature.strip()
    }

    unusual_comparisons = [
        comparison
        for comparison in comparisons
        if comparison["feature"] in unusual_feature_names
    ]

    if not unusual_comparisons:
        unusual_comparisons = comparisons[:5]

    reconciliation_evidence = {"available": False}

    if (
        not reconciliation_df.empty
        and "Invoice Number" in reconciliation_df.columns
    ):
        reconciliation_match = reconciliation_df[
            reconciliation_df["Invoice Number"].astype(str)
            == str(selected_invoice)
        ]

        if not reconciliation_match.empty:
            reconciliation_row = reconciliation_match.iloc[0]
            reconciliation_evidence = {
                "available": True,
                "status": str(
                    reconciliation_row.get("Status", "")
                ),
                "bcd_net": safe_float(
                    reconciliation_row.get("BCD Net")
                ),
                "ccd_total": safe_float(
                    reconciliation_row.get("CCD Total")
                ),
                "variance": safe_float(
                    reconciliation_row.get("Variance")
                ),
                "variance_percent": safe_float(
                    reconciliation_row.get("Variance %")
                ),
            }

    return {
        "available": True,
        "anomaly_score": safe_float(
            invoice_row.get("anomaly_score")
        ),
        "model_prediction": (
            "ANOMALY"
            if invoice_row.get("model_prediction") == -1
            else "NORMAL"
        ),
        "feature_comparisons": unusual_comparisons,
        "reconciliation": reconciliation_evidence,
    }


def build_sanitized_evidence(
    risk_row,
    retrieval_record,
    numeric_evidence,
):
    """Build sanitized evidence for external providers."""
    validation_score = safe_float(
        risk_row.get("Validation Score")
    )
    reconciliation_score = safe_float(
        risk_row.get("Reconciliation Score")
    )

    return {
        "safe_invoice_alias": retrieval_record.get(
            "safe_invoice_alias",
            "INV-UNKNOWN",
        ),
        "risk_level": str(risk_row.get("Risk Level", "")),
        "final_risk_score": safe_float(
            risk_row.get("Final Risk Score")
        ),
        "validation_score": validation_score,
        "reconciliation_score": reconciliation_score,
        "anomaly_score": safe_float(
            risk_row.get("Anomaly Score")
        ),
        "anomaly_component": safe_float(
            risk_row.get("Anomaly Component")
        ),
        "model_result": str(
            risk_row.get("Model Result", "")
        ),
        "unusual_features": str(
            risk_row.get("Unusual Features", "")
        ),
        "validation_assessment": (
            "Critical validation passed"
            if validation_score == 0
            else "Validation findings exist"
        ),
        "reconciliation_assessment": (
            "BCD net matches the sum of CCD charges"
            if reconciliation_score == 0
            else "A reconciliation finding exists"
        ),
        "numeric_anomaly_evidence": numeric_evidence,
    }


def build_rule_context(retrieved_rules):
    """Build controlled business-rule context."""
    return [
        {
            "rule_id": rule.get("rule_id", ""),
            "category": rule.get("category", ""),
            "title": rule.get("title", ""),
            "rule_text": rule.get("rule_text", ""),
            "recommended_action": rule.get(
                "recommended_action",
                "",
            ),
            "source": rule.get("source", ""),
            "similarity_score": safe_float(
                rule.get("relevance_score")
            ),
        }
        for rule in retrieved_rules
    ]


def build_explanation_messages(evidence, rules):
    """Create one shared grounded prompt for both providers."""
    system_prompt = """
You are an electricity invoice investigation assistant.

Explain a sanitized D2021 invoice assessment using only the invoice
evidence and business rules supplied by the user.

Mandatory requirements:
1. Do not invent invoice values, MPANs, tariffs, calculations, dates,
   identities, validation failures or business rules.
2. Do not claim that an invoice is invalid, incorrect or fraudulent
   merely because an anomaly-detection model flagged it.
3. Separate observed evidence from potential causes.
4. Potential causes are investigation hypotheses, not confirmed root
   causes, unless deterministic evidence directly proves the cause.
5. Passed validation and reconciliation checks are passed controls.
   Do not present passed controls as exceptions.
6. Cite only rule IDs provided in the retrieved rule context.
7. Cite only rules directly used in the explanation.
8. Recommended actions must be supported by evidence or supplied rules.
9. If evidence is insufficient, describe the limitation and require
   human review.
10. Return only valid JSON matching the requested structure.
11. Use numeric feature comparisons to identify confirmed anomaly
   drivers.
12. For every important anomaly driver, state the invoice value,
   dataset median, percentile and percentage difference when supplied.
13. Rank potential causes from most likely to least likely.
14. A high percentile confirms statistical unusualness but does not
   alone confirm that the billed value is incorrect.
15. If BCD net equals the CCD total, state that arithmetic
   reconciliation passed and do not use it as a possible cause.
16. Do not assign confidence above 0.95 unless deterministic reference
   data directly supports the cause.
17. If tariff, meter, MPAN-effective-date or approved-reference data is
   absent, explain that the output identifies the confirmed anomaly
   driver and likely cause, not a fully proven billing root cause.

Confidence guidance:
0.80 to 0.95: strong numeric anomaly evidence and closely matching rules.
0.60 to 0.79: useful evidence, but the underlying cause is not confirmed.
0.40 to 0.59: incomplete or weakly supporting evidence.
Below 0.40: insufficient evidence for a meaningful explanation.
""".strip()

    user_payload = {
        "task": (
            "Generate a grounded D2021 invoice-risk explanation "
            "using only the supplied sanitized evidence and "
            "retrieved business rules. Identify confirmed anomaly "
            "drivers, rank likely causes, and specify verification "
            "needed for each cause."
        ),
        "sanitized_invoice_evidence": evidence,
        "retrieved_business_rules": rules,
        "required_output": {
            "summary": "string",
            "observed_evidence": [
                (
                    "String containing the feature, invoice value, "
                    "median, percentile and percentage difference "
                    "when supplied."
                )
            ],
            "passed_controls": ["string"],
            "potential_causes": [
                (
                    "Ranked likely cause containing cause, supporting "
                    "evidence and verification required."
                )
            ],
            "recommended_actions": ["string"],
            "rule_citations": ["retrieved rule ID only"],
            "confidence_score": "number from 0 to 1",
            "human_review_required": "boolean",
            "limitations": ["string"],
        },
    }

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                user_payload,
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def extract_json_object(content):
    """Extract JSON, including output wrapped in Markdown fences."""
    if not content:
        raise ValueError("The provider returned an empty response.")

    cleaned_content = content.strip()

    if cleaned_content.startswith("```json"):
        cleaned_content = cleaned_content[7:]
    elif cleaned_content.startswith("```"):
        cleaned_content = cleaned_content[3:]

    if cleaned_content.endswith("```"):
        cleaned_content = cleaned_content[:-3]

    return json.loads(cleaned_content.strip())


# ---------------------------------------------------------
# Provider generation
# ---------------------------------------------------------
def generate_with_groq(client, model_name, evidence, rules):
    """Generate a structured explanation using Groq."""
    messages = build_explanation_messages(evidence, rules)

    try:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=2000,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": EXPLANATION_SCHEMA,
            },
        )
    except Exception:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=2000,
            messages=messages,
            response_format={"type": "json_object"},
        )

    return extract_json_object(
        response.choices[0].message.content
    )


def generate_with_openrouter(client, model_name, evidence, rules):
    """Generate a structured explanation using OpenRouter."""
    messages = build_explanation_messages(evidence, rules)

    try:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=2000,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": EXPLANATION_SCHEMA["name"],
                    "strict": False,
                    "schema": EXPLANATION_SCHEMA["schema"],
                },
            },
        )
    except Exception:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=2000,
            messages=messages,
            response_format={"type": "json_object"},
        )

    return extract_json_object(
        response.choices[0].message.content
    )


# ---------------------------------------------------------
# Response validation
# ---------------------------------------------------------
def normalize_string_list(value):
    """Convert provider output into a clean list of strings."""
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    value_string = str(value).strip()
    return [value_string] if value_string else []


def validate_explanation(explanation, retrieved_rules):
    """Validate output and remove unsupported rule citations."""
    required_fields = [
        "summary",
        "observed_evidence",
        "passed_controls",
        "potential_causes",
        "recommended_actions",
        "rule_citations",
        "confidence_score",
        "human_review_required",
        "limitations",
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in explanation
    ]

    if missing_fields:
        raise ValueError(
            "The provider response is missing required fields: "
            + ", ".join(missing_fields)
        )

    explanation["summary"] = str(
        explanation.get("summary", "")
    ).strip()

    if not explanation["summary"]:
        raise ValueError("The provider returned an empty summary.")

    list_fields = [
        "observed_evidence",
        "passed_controls",
        "potential_causes",
        "recommended_actions",
        "rule_citations",
        "limitations",
    ]

    for field in list_fields:
        explanation[field] = normalize_string_list(
            explanation.get(field)
        )

    valid_rule_ids = {
        str(rule.get("rule_id", "")).strip()
        for rule in retrieved_rules
        if str(rule.get("rule_id", "")).strip()
    }

    returned_citations = explanation.get("rule_citations", [])
    explanation["rule_citations"] = [
        citation
        for citation in returned_citations
        if citation in valid_rule_ids
    ]
    explanation["removed_unsupported_citations"] = [
        citation
        for citation in returned_citations
        if citation not in valid_rule_ids
    ]

    confidence = safe_float(
        explanation.get("confidence_score"),
        0,
    )
    explanation["confidence_score"] = max(
        0.0,
        min(confidence, 0.95),
    )

    human_review_value = explanation.get(
        "human_review_required",
        True,
    )

    if isinstance(human_review_value, bool):
        explanation["human_review_required"] = human_review_value
    else:
        explanation["human_review_required"] = str(
            human_review_value
        ).strip().lower() in {
            "true",
            "yes",
            "1",
            "required",
        }

    return explanation


# ---------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------
def create_fallback_explanation(evidence, retrieved_rules):
    """Create a numerical evidence-based fallback explanation."""
    rule_ids = [
        rule.get("rule_id", "")
        for rule in retrieved_rules[:3]
        if rule.get("rule_id")
    ]
    actions = [
        rule.get("recommended_action", "")
        for rule in retrieved_rules[:3]
        if rule.get("recommended_action")
    ]

    numeric_evidence = evidence.get(
        "numeric_anomaly_evidence",
        {},
    )
    comparisons = numeric_evidence.get(
        "feature_comparisons",
        [],
    )

    observed_evidence = [
        f"Risk level: {evidence['risk_level']}.",
        (
            "Final risk score: "
            f"{evidence['final_risk_score']:.2f}/100."
        ),
        (
            "Anomaly score: "
            f"{evidence['anomaly_score']:.2f}/100."
        ),
    ]

    for comparison in comparisons:
        difference = comparison.get(
            "difference_from_median_percent"
        )
        difference_text = (
            f"{difference:,.2f}%"
            if difference is not None
            else "not calculable because the median is zero"
        )
        observed_evidence.append(
            f"{comparison['feature']}: invoice value "
            f"{comparison['invoice_value']:,.2f}, dataset median "
            f"{comparison['dataset_median']:,.2f}, percentile "
            f"{comparison['percentile']:,.2f}, difference from "
            f"median {difference_text}."
        )

    top_feature = (
        comparisons[0]["feature"]
        if comparisons
        else evidence.get("unusual_features", "the supplied features")
    )

    return {
        "summary": (
            f"{evidence['safe_invoice_alias']} was prioritized "
            f"because {top_feature} and the other listed features "
            "differ materially from the comparison population. "
            "The arithmetic controls passed, so the finding is a "
            "charge-pattern anomaly rather than a BCD-to-CCD "
            "total mismatch."
        ),
        "observed_evidence": observed_evidence,
        "passed_controls": [
            evidence["validation_assessment"],
            evidence["reconciliation_assessment"],
        ],
        "potential_causes": [
            (
                "1. The source quantity, consumption, capacity or "
                "reactive value may be unusually high. Verify the "
                "source meter and billing data."
            ),
            (
                "2. The effective charge rate or tariff mapping may "
                "differ from the expected value. Verify the approved "
                "tariff and its effective dates."
            ),
            (
                "3. The values may be legitimate for this site and "
                "period. Compare with prior invoices and operational "
                "evidence before concluding that an error exists."
            ),
        ],
        "recommended_actions": actions or [
            "Compare the unusual feature values with approved reference data.",
            "Verify source meter, consumption, capacity and tariff records.",
        ],
        "rule_citations": rule_ids,
        "confidence_score": 0.72 if comparisons else 0.55,
        "human_review_required": True,
        "limitations": [
            (
                "External LLM providers were unavailable, so the "
                "deterministic fallback generated this explanation."
            ),
            (
                "Without approved tariff, source meter and effective-"
                "dated MPAN reference data, the platform identifies "
                "the anomaly driver and likely causes but cannot fully "
                "prove the billing root cause."
            ),
        ],
        "removed_unsupported_citations": [],
    }


# ---------------------------------------------------------
# Display helpers
# ---------------------------------------------------------
def render_string_list(title, values):
    """Display a string list."""
    st.markdown(f"#### {title}")

    if not values:
        st.write("None identified from the supplied evidence.")
        return

    for value in values:
        st.markdown(f"- {value}")


# ---------------------------------------------------------
# Page
# ---------------------------------------------------------
st.title("D2021 Invoice Validation Platform")
st.subheader("Step 8: Grounded AI Explanation")

risk_results = st.session_state.get("risk_results")
retrieval_results = st.session_state.get(
    "rag_retrieval_results",
    {},
)
anomaly_results = st.session_state.get(
    "anomaly_results",
    [],
)
reconciliation_results = st.session_state.get(
    "reconciliation_results",
    [],
)

if risk_results is None:
    st.warning("Risk scoring has not been completed.")
    st.info("Complete Step 6: Risk Scoring first.")
    st.stop()

if not retrieval_results:
    st.warning("No Gemini retrieval results are available.")
    st.info(
        "Open Step 7, select an invoice and run semantic "
        "retrieval first."
    )
    st.stop()


groq_api_key, groq_model = get_groq_settings()
openrouter_api_key, openrouter_model = get_openrouter_settings()

groq_client = (
    get_groq_client(groq_api_key)
    if groq_api_key
    else None
)
openrouter_client = (
    get_openrouter_client(openrouter_api_key)
    if openrouter_api_key
    else None
)

provider1, provider2, provider3 = st.columns(3)
provider1.metric(
    "Groq",
    "Configured" if groq_client else "Unavailable",
)
provider2.metric(
    "OpenRouter",
    "Configured" if openrouter_client else "Unavailable",
)
provider3.metric("Final Fallback", "Deterministic")

st.info(
    "Provider order: Groq, then OpenRouter, then deterministic "
    "fallback."
)
st.caption(
    "Only sanitized invoice evidence, numerical feature comparisons "
    "and Gemini-retrieved rules are sent externally. Original invoice "
    "numbers, MPANs, customer names, addresses and raw D2021 records "
    "are not transmitted."
)

risk_df = pd.DataFrame(risk_results)
available_invoices = list(retrieval_results.keys())
selected_invoice = st.selectbox(
    "Select an invoice with completed rule retrieval",
    available_invoices,
)

retrieval_record = retrieval_results[selected_invoice]
risk_match = risk_df[
    risk_df["Invoice Number"].astype(str)
    == str(selected_invoice)
]

if risk_match.empty:
    st.error("The corresponding risk result could not be found.")
    st.stop()

risk_row = risk_match.iloc[0]
retrieved_rules = retrieval_record.get("retrieved_rules", [])

if not retrieved_rules:
    st.warning(
        "No retrieved business rules are available for the selected "
        "invoice."
    )
    st.info("Return to Step 7 and run semantic retrieval.")
    st.stop()

numeric_evidence = build_numeric_anomaly_evidence(
    selected_invoice,
    anomaly_results,
    reconciliation_results,
)
evidence = build_sanitized_evidence(
    risk_row,
    retrieval_record,
    numeric_evidence,
)
rule_context = build_rule_context(retrieved_rules)

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Safe Invoice Alias", evidence["safe_invoice_alias"])
metric2.metric("Risk Level", evidence["risk_level"])
metric3.metric(
    "Risk Score",
    f"{evidence['final_risk_score']:.2f}",
)
metric4.metric("Retrieved Rules", len(rule_context))

with st.expander("View sanitized evidence sent to the provider"):
    st.json(evidence)

with st.expander("View numerical anomaly evidence"):
    st.json(numeric_evidence)

with st.expander("View retrieved rule context sent to the provider"):
    st.json(rule_context)

generate_button = st.button(
    "Generate Enhanced Root-Cause Explanation",
    type="primary",
    use_container_width=True,
)

if generate_button:
    generation_method = None
    successful_model = None
    provider_errors = []
    explanation = None

    if groq_client:
        try:
            with st.spinner(
                f"Trying Groq with {groq_model}..."
            ):
                explanation = generate_with_groq(
                    groq_client,
                    groq_model,
                    evidence,
                    rule_context,
                )
                explanation = validate_explanation(
                    explanation,
                    retrieved_rules,
                )
                generation_method = "Groq LLM"
                successful_model = groq_model
        except Exception as error:
            provider_errors.append(
                {
                    "provider": "Groq",
                    "model": groq_model,
                    "error": str(error),
                }
            )
            explanation = None

    if explanation is None and openrouter_client:
        try:
            with st.spinner(
                "Groq unavailable. Trying OpenRouter with "
                f"{openrouter_model}..."
            ):
                explanation = generate_with_openrouter(
                    openrouter_client,
                    openrouter_model,
                    evidence,
                    rule_context,
                )
                explanation = validate_explanation(
                    explanation,
                    retrieved_rules,
                )
                generation_method = "OpenRouter LLM"
                successful_model = openrouter_model
        except Exception as error:
            provider_errors.append(
                {
                    "provider": "OpenRouter",
                    "model": openrouter_model,
                    "error": str(error),
                }
            )
            explanation = None

    if explanation is None:
        explanation = create_fallback_explanation(
            evidence,
            retrieved_rules,
        )
        generation_method = "Deterministic Fallback"
        successful_model = "No external model"

    if "grounded_ai_explanations" not in st.session_state:
        st.session_state.grounded_ai_explanations = {}

    st.session_state.grounded_ai_explanations[
        selected_invoice
    ] = {
        "safe_invoice_alias": evidence["safe_invoice_alias"],
        "generation_method": generation_method,
        "successful_model": successful_model,
        "groq_model": groq_model,
        "openrouter_model": openrouter_model,
        "retrieval_method": retrieval_record.get(
            "retrieval_method",
            "",
        ),
        "numeric_anomaly_evidence": numeric_evidence,
        "explanation": explanation,
        "provider_errors": provider_errors,
    }

stored_result = st.session_state.get(
    "grounded_ai_explanations",
    {},
).get(selected_invoice)

if stored_result:
    explanation = stored_result["explanation"]

    st.markdown("---")
    st.subheader("Enhanced Root-Cause Explanation")

    info1, info2, info3 = st.columns(3)
    info1.metric(
        "Generation Method",
        stored_result.get("generation_method", "Unknown"),
    )
    info2.metric(
        "Successful Model",
        stored_result.get("successful_model", "Unknown"),
    )
    info3.metric(
        "Estimated Confidence",
        f"{explanation['confidence_score']:.0%}",
    )

    provider_errors = stored_result.get("provider_errors", [])
    if provider_errors:
        with st.expander("View provider failover details"):
            for provider_error in provider_errors:
                st.warning(
                    f"{provider_error['provider']} "
                    f"({provider_error['model']}): "
                    f"{provider_error['error']}"
                )

    if (
        stored_result.get("generation_method")
        == "Deterministic Fallback"
    ):
        st.warning(
            "Both external providers were unavailable. A deterministic "
            "numerical evidence-based explanation was generated."
        )

    st.markdown("#### Summary")
    st.write(explanation["summary"])

    render_string_list(
        "Confirmed Anomaly Evidence",
        explanation["observed_evidence"],
    )
    render_string_list(
        "Passed Controls",
        explanation["passed_controls"],
    )
    render_string_list(
        "Ranked Likely Causes and Required Verification",
        explanation["potential_causes"],
    )
    render_string_list(
        "Recommended Actions",
        explanation["recommended_actions"],
    )
    render_string_list(
        "Rule Citations",
        explanation["rule_citations"],
    )
    render_string_list(
        "Limitations",
        explanation["limitations"],
    )

    if explanation["human_review_required"]:
        st.warning(
            "Human review is required before a final invoice-processing "
            "decision is recorded."
        )
    else:
        st.info(
            "The model did not mark human review as mandatory. Existing "
            "business controls must still be followed."
        )

    removed_citations = explanation.get(
        "removed_unsupported_citations",
        [],
    )
    if removed_citations:
        st.warning(
            "Unsupported citations removed: "
            + ", ".join(removed_citations)
        )

    explanation_json = json.dumps(
        stored_result,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    st.download_button(
        "Download Enhanced Root-Cause Explanation",
        data=explanation_json,
        file_name=(
            f"{evidence['safe_invoice_alias']}"
            "_enhanced_root_cause_explanation.json"
        ),
        mime="application/json",
        use_container_width=True,
    )

    st.success(
        "The enhanced explanation has been stored for Step 9: "
        "Human Review."
    )

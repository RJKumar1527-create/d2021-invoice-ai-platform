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
            "summary": {
                "type": "string"
            },
            "observed_evidence": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "passed_controls": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "potential_causes": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "recommended_actions": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "rule_citations": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "confidence_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "human_review_required": {
                "type": "boolean"
            },
            "limitations": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            }
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
            "limitations"
        ],
        "additionalProperties": False
    }
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


def build_sanitized_evidence(
    risk_row,
    retrieval_record,
):
    """
    Build sanitized evidence for external providers.

    Original invoice number, MPAN, customer name, site name,
    address and raw D2021 records are excluded.
    """
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
        "risk_level": str(
            risk_row.get("Risk Level", "")
        ),
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
    }


def build_rule_context(retrieved_rules):
    """Build controlled business-rule context."""
    rule_context = []

    for rule in retrieved_rules:
        rule_context.append(
            {
                "rule_id": rule.get(
                    "rule_id",
                    "",
                ),
                "category": rule.get(
                    "category",
                    "",
                ),
                "title": rule.get(
                    "title",
                    "",
                ),
                "rule_text": rule.get(
                    "rule_text",
                    "",
                ),
                "recommended_action": rule.get(
                    "recommended_action",
                    "",
                ),
                "source": rule.get(
                    "source",
                    "",
                ),
                "similarity_score": safe_float(
                    rule.get("relevance_score")
                ),
            }
        )

    return rule_context


def build_explanation_messages(
    evidence,
    rules,
):
    """Create one shared grounded prompt for both providers."""

    system_prompt = """
You are an electricity invoice investigation assistant.

Explain a sanitized D2021 invoice assessment using only the invoice
evidence and business rules supplied by the user.

Mandatory requirements:

1. Do not invent invoice values, MPANs, tariffs, calculations,
   dates, identities, validation failures or business rules.

2. Do not claim that an invoice is invalid, incorrect or fraudulent
   merely because an anomaly-detection model flagged it.

3. Separate observed evidence from potential causes.

4. Potential causes must be described as investigation areas.
   They must not be described as confirmed root causes.

5. Passed validation and reconciliation checks must be listed as
   passed controls. They must not be presented as exceptions.

6. Cite only rule IDs provided in the retrieved rule context.

7. Do not cite every retrieved rule automatically. Cite only rules
   directly used in the explanation.

8. Recommended actions must be practical investigation activities
   supported by supplied evidence or retrieved rules.

9. If evidence is insufficient, clearly describe the limitation and
   require human review.

10. Return only valid JSON matching the requested structure.

Confidence guidance:

0.80 to 1.00:
Strong direct evidence exists and retrieved rules closely match.

0.60 to 0.79:
Useful evidence exists, but the underlying cause is not confirmed.

0.40 to 0.59:
Evidence is incomplete or only weakly supports possible causes.

Below 0.40:
Evidence is insufficient for a meaningful technical explanation.
""".strip()

    user_payload = {
        "task": (
            "Generate a grounded D2021 invoice-risk explanation "
            "using only the supplied sanitized evidence and "
            "retrieved business rules."
        ),
        "sanitized_invoice_evidence": evidence,
        "retrieved_business_rules": rules,
        "required_output": {
            "summary": "string",
            "observed_evidence": [
                "string"
            ],
            "passed_controls": [
                "string"
            ],
            "potential_causes": [
                "string"
            ],
            "recommended_actions": [
                "string"
            ],
            "rule_citations": [
                "retrieved rule ID only"
            ],
            "confidence_score": (
                "number from 0 to 1"
            ),
            "human_review_required": "boolean",
            "limitations": [
                "string"
            ],
        },
    }

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
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
    """
    Extract JSON from a provider response.

    This also handles responses accidentally wrapped in
    Markdown code fences.
    """
    if not content:
        raise ValueError(
            "The provider returned an empty response."
        )

    cleaned_content = content.strip()

    if cleaned_content.startswith("```json"):
        cleaned_content = cleaned_content[7:]

    elif cleaned_content.startswith("```"):
        cleaned_content = cleaned_content[3:]

    if cleaned_content.endswith("```"):
        cleaned_content = cleaned_content[:-3]

    cleaned_content = cleaned_content.strip()

    return json.loads(cleaned_content)


# ---------------------------------------------------------
# Groq generation
# ---------------------------------------------------------
def generate_with_groq(
    client,
    model_name,
    evidence,
    rules,
):
    """Generate structured explanation using Groq."""
    messages = build_explanation_messages(
        evidence,
        rules,
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=1600,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": EXPLANATION_SCHEMA,
            },
        )

    except Exception:
        # Some Groq models may not support json_schema.
        # Retry using general JSON-object mode.
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=1600,
            messages=messages,
            response_format={
                "type": "json_object"
            },
        )

    content = response.choices[0].message.content

    return extract_json_object(content)


# ---------------------------------------------------------
# OpenRouter generation
# ---------------------------------------------------------
def generate_with_openrouter(
    client,
    model_name,
    evidence,
    rules,
):
    """Generate structured explanation using OpenRouter."""
    messages = build_explanation_messages(
        evidence,
        rules,
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=1600,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": EXPLANATION_SCHEMA[
                        "name"
                    ],
                    "strict": False,
                    "schema": EXPLANATION_SCHEMA[
                        "schema"
                    ],
                },
            },
        )

    except Exception:
        # The selected OpenRouter endpoint may not support
        # JSON-schema mode. Retry with ordinary JSON mode.
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.1,
            max_tokens=1600,
            messages=messages,
            response_format={
                "type": "json_object"
            },
        )

    content = response.choices[0].message.content

    return extract_json_object(content)


# ---------------------------------------------------------
# Response validation
# ---------------------------------------------------------
def normalize_string_list(value):
    """Convert a provider value into a clean list of strings."""
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    value_string = str(value).strip()

    if not value_string:
        return []

    return [value_string]


def validate_explanation(
    explanation,
    retrieved_rules,
):
    """
    Validate generated output locally.

    Unsupported rule citations are removed.
    """
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
        raise ValueError(
            "The provider returned an empty summary."
        )

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

    returned_citations = explanation.get(
        "rule_citations",
        [],
    )

    valid_citations = [
        citation
        for citation in returned_citations
        if citation in valid_rule_ids
    ]

    removed_citations = [
        citation
        for citation in returned_citations
        if citation not in valid_rule_ids
    ]

    explanation["rule_citations"] = (
        valid_citations
    )

    confidence = safe_float(
        explanation.get("confidence_score"),
        0,
    )

    explanation["confidence_score"] = max(
        0.0,
        min(confidence, 1.0),
    )

    human_review_value = explanation.get(
        "human_review_required",
        True,
    )

    if isinstance(human_review_value, bool):
        explanation[
            "human_review_required"
        ] = human_review_value

    else:
        explanation[
            "human_review_required"
        ] = str(
            human_review_value
        ).strip().lower() in {
            "true",
            "yes",
            "1",
            "required",
        }

    explanation[
        "removed_unsupported_citations"
    ] = removed_citations

    return explanation


# ---------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------
def create_fallback_explanation(
    evidence,
    retrieved_rules,
):
    """Create safe fallback when both API providers fail."""
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

    unusual_features = evidence.get(
        "unusual_features",
        "",
    )

    unusual_feature_description = (
        unusual_features
        or "the supplied invoice features"
    )

    return {
        "summary": (
            f"{evidence['safe_invoice_alias']} was prioritized "
            "because the anomaly-detection model identified an "
            f"unusual pattern involving "
            f"{unusual_feature_description}. "
            "The risk assessment does not confirm a billing error."
        ),
        "observed_evidence": [
            (
                "Risk level: "
                f"{evidence['risk_level']}."
            ),
            (
                "Final risk score: "
                f"{evidence['final_risk_score']:.2f}/100."
            ),
            (
                "Anomaly score: "
                f"{evidence['anomaly_score']:.2f}/100."
            ),
            (
                "Model result: "
                f"{evidence['model_result']}."
            ),
            (
                "Unusual features: "
                f"{unusual_features or 'not supplied'}."
            ),
        ],
        "passed_controls": [
            evidence["validation_assessment"],
            evidence["reconciliation_assessment"],
        ],
        "potential_causes": [
            (
                "The unusual invoice characteristics may require "
                "comparison with source consumption, capacity, "
                "reactive-power and tariff evidence."
            )
        ],
        "recommended_actions": actions or [
            (
                "Perform manual review of the invoice and compare "
                "the unusual features with supporting source data."
            )
        ],
        "rule_citations": rule_ids,
        "confidence_score": 0.55,
        "human_review_required": True,
        "limitations": [
            (
                "Both external LLM providers were unavailable, "
                "so deterministic fallback logic was used."
            ),
            (
                "The supplied anomaly evidence does not confirm "
                "the underlying cause."
            ),
        ],
        "removed_unsupported_citations": [],
    }


# ---------------------------------------------------------
# Display helpers
# ---------------------------------------------------------
def render_string_list(title, values):
    """Display a list cleanly."""
    st.markdown(f"#### {title}")

    if not values:
        st.write(
            "None identified from the supplied evidence."
        )
        return

    for value in values:
        st.markdown(f"- {value}")


# ---------------------------------------------------------
# Page
# ---------------------------------------------------------
st.title("D2021 Invoice Validation Platform")
st.subheader(
    "Step 8: Grounded AI Explanation"
)

risk_results = st.session_state.get(
    "risk_results"
)

retrieval_results = st.session_state.get(
    "rag_retrieval_results",
    {},
)

if risk_results is None:
    st.warning(
        "Risk scoring has not been completed."
    )
    st.info(
        "Complete Step 6: Risk Scoring first."
    )
    st.stop()

if not retrieval_results:
    st.warning(
        "No Gemini retrieval results are available."
    )
    st.info(
        "Open Step 7, select an invoice and run "
        "semantic retrieval first."
    )
    st.stop()


# ---------------------------------------------------------
# Initialize provider chain
# ---------------------------------------------------------
groq_api_key, groq_model = (
    get_groq_settings()
)

openrouter_api_key, openrouter_model = (
    get_openrouter_settings()
)

groq_client = (
    get_groq_client(groq_api_key)
    if groq_api_key
    else None
)

openrouter_client = (
    get_openrouter_client(
        openrouter_api_key
    )
    if openrouter_api_key
    else None
)


provider1, provider2, provider3 = st.columns(3)

provider1.metric(
    "Groq",
    "Configured"
    if groq_client
    else "Unavailable",
)

provider2.metric(
    "OpenRouter",
    "Configured"
    if openrouter_client
    else "Unavailable",
)

provider3.metric(
    "Final Fallback",
    "Deterministic",
)

st.info(
    "Provider order: Groq, then OpenRouter, "
    "then deterministic fallback."
)

st.caption(
    "Only sanitized invoice evidence and Gemini-retrieved "
    "business rules are sent to external providers. Original "
    "invoice numbers, MPANs, customer names, site names, "
    "addresses and raw D2021 records are not transmitted."
)


# ---------------------------------------------------------
# Select invoice
# ---------------------------------------------------------
risk_df = pd.DataFrame(
    risk_results
)

available_invoices = list(
    retrieval_results.keys()
)

selected_invoice = st.selectbox(
    "Select an invoice with completed rule retrieval",
    available_invoices,
)

retrieval_record = retrieval_results[
    selected_invoice
]

risk_match = risk_df[
    risk_df["Invoice Number"].astype(str)
    == str(selected_invoice)
]

if risk_match.empty:
    st.error(
        "The corresponding risk result could not be found."
    )
    st.stop()

risk_row = risk_match.iloc[0]

retrieved_rules = retrieval_record.get(
    "retrieved_rules",
    [],
)

if not retrieved_rules:
    st.warning(
        "No retrieved business rules are available for "
        "the selected invoice."
    )
    st.info(
        "Return to Step 7 and run semantic retrieval."
    )
    st.stop()

evidence = build_sanitized_evidence(
    risk_row,
    retrieval_record,
)

rule_context = build_rule_context(
    retrieved_rules
)


metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Safe Invoice Alias",
    evidence["safe_invoice_alias"],
)

metric2.metric(
    "Risk Level",
    evidence["risk_level"],
)

metric3.metric(
    "Risk Score",
    f"{evidence['final_risk_score']:.2f}",
)

metric4.metric(
    "Retrieved Rules",
    len(rule_context),
)


with st.expander(
    "View sanitized evidence sent to the provider"
):
    st.json(evidence)


with st.expander(
    "View retrieved rule context sent to the provider"
):
    st.json(rule_context)


generate_button = st.button(
    "Generate Grounded Explanation",
    type="primary",
    use_container_width=True,
)


# ---------------------------------------------------------
# Provider failover
# ---------------------------------------------------------
if generate_button:
    generation_method = None
    successful_model = None
    provider_errors = []
    explanation = None

    # Provider 1: Groq
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

    # Provider 2: OpenRouter
    if (
        explanation is None
        and openrouter_client
    ):
        try:
            with st.spinner(
                "Groq unavailable. Trying OpenRouter "
                f"with {openrouter_model}..."
            ):
                explanation = (
                    generate_with_openrouter(
                        openrouter_client,
                        openrouter_model,
                        evidence,
                        rule_context,
                    )
                )

                explanation = validate_explanation(
                    explanation,
                    retrieved_rules,
                )

                generation_method = (
                    "OpenRouter LLM"
                )

                successful_model = (
                    openrouter_model
                )

        except Exception as error:
            provider_errors.append(
                {
                    "provider": "OpenRouter",
                    "model": openrouter_model,
                    "error": str(error),
                }
            )

            explanation = None

    # Provider 3: deterministic fallback
    if explanation is None:
        explanation = create_fallback_explanation(
            evidence,
            retrieved_rules,
        )

        generation_method = (
            "Deterministic Fallback"
        )

        successful_model = (
            "No external model"
        )

    if (
        "grounded_ai_explanations"
        not in st.session_state
    ):
        st.session_state[
            "grounded_ai_explanations"
        ] = {}

    st.session_state[
        "grounded_ai_explanations"
    ][selected_invoice] = {
        "safe_invoice_alias": evidence[
            "safe_invoice_alias"
        ],
        "generation_method": generation_method,
        "successful_model": successful_model,
        "groq_model": groq_model,
        "openrouter_model": openrouter_model,
        "retrieval_method": retrieval_record.get(
            "retrieval_method",
            "",
        ),
        "explanation": explanation,
        "provider_errors": provider_errors,
    }


# ---------------------------------------------------------
# Display stored result
# ---------------------------------------------------------
stored_result = st.session_state.get(
    "grounded_ai_explanations",
    {},
).get(selected_invoice)


if stored_result:
    explanation = stored_result[
        "explanation"
    ]

    st.markdown("---")
    st.subheader(
        "Grounded AI Explanation"
    )

    info1, info2, info3 = st.columns(3)

    info1.metric(
        "Generation Method",
        stored_result.get(
            "generation_method",
            "Unknown",
        ),
    )

    info2.metric(
        "Successful Model",
        stored_result.get(
            "successful_model",
            "Unknown",
        ),
    )

    info3.metric(
        "Confidence",
        (
            f"{explanation['confidence_score']:.0%}"
        ),
    )

    provider_errors = stored_result.get(
        "provider_errors",
        [],
    )

    if provider_errors:
        with st.expander(
            "View provider failover details"
        ):
            for provider_error in provider_errors:
                st.warning(
                    f"{provider_error['provider']} "
                    f"({provider_error['model']}): "
                    f"{provider_error['error']}"
                )

    if (
        stored_result.get(
            "generation_method"
        )
        == "Deterministic Fallback"
    ):
        st.warning(
            "Both external providers were unavailable. "
            "A deterministic evidence-based explanation "
            "was generated."
        )

    st.markdown("#### Summary")
    st.write(
        explanation["summary"]
    )

    render_string_list(
        "Observed Evidence",
        explanation["observed_evidence"],
    )

    render_string_list(
        "Passed Controls",
        explanation["passed_controls"],
    )

    render_string_list(
        "Potential Causes to Investigate",
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

    if explanation[
        "human_review_required"
    ]:
        st.warning(
            "Human review is required before a final "
            "invoice-processing decision is recorded."
        )

    else:
        st.info(
            "The model did not mark human review as mandatory. "
            "Existing business controls must still be followed."
        )

    removed_citations = explanation.get(
        "removed_unsupported_citations",
        [],
    )

    if removed_citations:
        st.warning(
            "Unsupported citations removed: "
            + ", ".join(
                removed_citations
            )
        )

    explanation_json = json.dumps(
        stored_result,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    st.download_button(
        "Download Grounded Explanation",
        data=explanation_json,
        file_name=(
            f"{evidence['safe_invoice_alias']}"
            "_grounded_explanation.json"
        ),
        mime="application/json",
        use_container_width=True,
    )

    st.success(
        "The grounded explanation has been stored "
        "for Step 9: Human Review."
    )
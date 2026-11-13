import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from review_database import (
    get_all_reviews,
    get_audit_history,
    get_review,
    initialise_database,
    save_review,
)

DECISIONS = [
    "NEEDS INVESTIGATION",
    "QUERY REQUIRED",
    "APPROVED",
    "FALSE POSITIVE",
    "REJECTED",
]

REVIEW_STATUSES = [
    "NEW",
    "UNDER REVIEW",
    "AWAITING INFORMATION",
    "QUERY RAISED",
    "RESOLVED",
    "CLOSED",
]

RISK_LEVELS = [
    "NO OVERRIDE",
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

AI_ASSESSMENTS = [
    "ACCEPTED",
    "PARTIALLY ACCEPTED",
    "REJECTED",
    "NOT REVIEWED",
]


def current_timestamp():
    """Return a readable audit timestamp."""
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def safe_float(value, default=0.0):
    """Convert a value safely to float."""
    try:
        return float(value or default)

    except (TypeError, ValueError):
        return default


def initialise_review_state():
    """Create review storage in Streamlit session state."""
    if "human_reviews" not in st.session_state:
        st.session_state.human_reviews = {}

    if "human_review_audit_history" not in st.session_state:
        st.session_state.human_review_audit_history = []


def get_explanation_record(
    selected_invoice,
    explanation_results,
):
    """Return the stored grounded explanation."""
    return explanation_results.get(
        selected_invoice,
        {},
    )


def get_existing_review(selected_invoice):
    return st.session_state.human_reviews.get(
        selected_invoice,
        {},
    )


def determine_effective_risk(
    original_risk,
    risk_override,
):
    """Return original or overridden risk level."""
    if risk_override == "NO OVERRIDE":
        return original_risk

    return risk_override


def validate_review(
    decision,
    reviewer_name,
    assigned_owner,
    reviewer_comments,
    resolution_notes,
    false_positive_reason,
):
    """Validate mandatory human-review fields."""
    errors = []

    if not reviewer_name.strip():
        errors.append(
            "Reviewer name is mandatory."
        )

    if not assigned_owner.strip():
        errors.append(
            "Assigned owner is mandatory."
        )

    if not reviewer_comments.strip():
        errors.append(
            "Reviewer comments are mandatory."
        )

    if (
        decision in [
            "APPROVED",
            "FALSE POSITIVE",
            "REJECTED",
        ]
        and not resolution_notes.strip()
    ):
        errors.append(
            "Resolution notes are required for "
            "Approved, False Positive or Rejected decisions."
        )

    if (
        decision == "FALSE POSITIVE"
        and not false_positive_reason.strip()
    ):
        errors.append(
            "A false-positive reason is mandatory."
        )

    return errors


def build_review_record(
    selected_invoice,
    safe_invoice_alias,
    reviewer_name,
    assigned_owner,
    decision,
    review_status,
    due_date,
    ai_assessment,
    original_risk,
    risk_override,
    reviewer_comments,
    false_positive_reason,
    resolution_notes,
    supporting_evidence,
    rule_citations,
    existing_review,
):
    """Build the final review record."""
    effective_risk = determine_effective_risk(
        original_risk,
        risk_override,
    )

    created_at = existing_review.get(
        "created_at",
        current_timestamp(),
    )

    return {
        "invoice_number": selected_invoice,
        "safe_invoice_alias": safe_invoice_alias,
        "reviewer_name": reviewer_name.strip(),
        "assigned_owner": assigned_owner.strip(),
        "decision": decision,
        "review_status": review_status,
        "due_date": str(due_date),
        "ai_assessment": ai_assessment,
        "original_risk_level": original_risk,
        "risk_override": risk_override,
        "effective_risk_level": effective_risk,
        "reviewer_comments": reviewer_comments.strip(),
        "false_positive_reason": (
            false_positive_reason.strip()
        ),
        "resolution_notes": resolution_notes.strip(),
        "supporting_evidence": (
            supporting_evidence.strip()
        ),
        "rule_citations": rule_citations,
        "created_at": created_at,
        "updated_at": current_timestamp(),
    }


def create_audit_entry(
    review_record,
    previous_review,
):
    """Create an immutable audit-history entry."""
    changed_fields = []

    if previous_review:
        audited_fields = [
            "reviewer_name",
            "assigned_owner",
            "decision",
            "review_status",
            "due_date",
            "ai_assessment",
            "risk_override",
            "effective_risk_level",
            "reviewer_comments",
            "false_positive_reason",
            "resolution_notes",
            "supporting_evidence",
        ]

        for field in audited_fields:
            previous_value = previous_review.get(
                field
            )

            new_value = review_record.get(
                field
            )

            if previous_value != new_value:
                changed_fields.append(
                    {
                        "field": field,
                        "previous_value": previous_value,
                        "new_value": new_value,
                    }
                )

    else:
        changed_fields.append(
            {
                "field": "review",
                "previous_value": None,
                "new_value": "Review created",
            }
        )

    return {
        "audit_timestamp": current_timestamp(),
        "invoice_number": review_record[
            "invoice_number"
        ],
        "safe_invoice_alias": review_record[
            "safe_invoice_alias"
        ],
        "reviewer_name": review_record[
            "reviewer_name"
        ],
        "decision": review_record["decision"],
        "review_status": review_record[
            "review_status"
        ],
        "effective_risk_level": review_record[
            "effective_risk_level"
        ],
        "changed_fields": changed_fields,
    }


def render_string_list(title, values):
    """Display supplied values as a bulleted list."""
    st.markdown(f"#### {title}")

    if not values:
        st.write(
            "No information is available."
        )
        return

    for value in values:
        st.markdown(f"- {value}")


def format_changes(changed_fields):
    """Format audit changes for table display."""
    descriptions = []

    for change in changed_fields:
        field = change.get(
            "field",
            "",
        )

        old_value = change.get(
            "previous_value"
        )

        new_value = change.get(
            "new_value"
        )

        if field == "review":
            descriptions.append(
                "Review created"
            )

        else:
            descriptions.append(
                f"{field}: "
                f"{old_value} → {new_value}"
            )

    return "; ".join(descriptions)


# ---------------------------------------------------------
# Page setup
# ---------------------------------------------------------
st.title("D2021 Invoice Validation Platform")
st.subheader("Step 9: Human Review")

initialise_database()

initialise_review_state()

risk_results = st.session_state.get(
    "risk_results"
)

explanation_results = st.session_state.get(
    "grounded_ai_explanations",
    {},
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

if not explanation_results:
    st.warning(
        "No grounded AI explanation is available."
    )
    st.info(
        "Complete Step 8: Grounded AI Explanation first."
    )
    st.stop()


risk_df = pd.DataFrame(
    risk_results
)

available_invoices = list(
    explanation_results.keys()
)

selected_invoice = st.selectbox(
    "Select an invoice for human review",
    available_invoices,
)

explanation_record = get_explanation_record(
    selected_invoice,
    explanation_results,
)

explanation = explanation_record.get(
    "explanation",
    {},
)

risk_match = risk_df[
    risk_df["Invoice Number"].astype(str)
    == str(selected_invoice)
]

if risk_match.empty:
    st.error(
        "The risk result for the selected invoice "
        "could not be found."
    )
    st.stop()

risk_row = risk_match.iloc[0]

safe_invoice_alias = explanation_record.get(
    "safe_invoice_alias",
    "INV-UNKNOWN",
)

original_risk = str(
    risk_row.get(
        "Risk Level",
        "UNKNOWN",
    )
)

final_risk_score = safe_float(
    risk_row.get(
        "Final Risk Score"
    )
)

anomaly_score = safe_float(
    risk_row.get(
        "Anomaly Score"
    )
)

confidence_score = safe_float(
    explanation.get(
        "confidence_score"
    )
)

generation_method = explanation_record.get(
    "generation_method",
    "Unknown",
)

successful_model = explanation_record.get(
    "successful_model",
    "Unknown",
)

existing_review = get_existing_review(
    selected_invoice
)


# ---------------------------------------------------------
# Review summary
# ---------------------------------------------------------
metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "Safe Invoice Alias",
    safe_invoice_alias,
)

metric2.metric(
    "Original Risk",
    original_risk,
)

metric3.metric(
    "Risk Score",
    f"{final_risk_score:.2f}",
)

metric4.metric(
    "AI Confidence",
    f"{confidence_score:.0%}",
)

summary1, summary2, summary3 = st.columns(3)

summary1.metric(
    "Anomaly Score",
    f"{anomaly_score:.2f}",
)

summary2.metric(
    "Generation Method",
    generation_method,
)

summary3.metric(
    "Successful Model",
    successful_model,
)


# ---------------------------------------------------------
# AI explanation
# ---------------------------------------------------------
st.markdown("---")
st.subheader("AI Investigation Summary")

st.markdown("#### Summary")

st.write(
    explanation.get(
        "summary",
        "No explanation summary is available.",
    )
)

render_string_list(
    "Confirmed Anomaly Evidence",
    explanation.get(
        "observed_evidence",
        [],
    ),
)

render_string_list(
    "Passed Controls",
    explanation.get(
        "passed_controls",
        [],
    ),
)

render_string_list(
    "Ranked Likely Causes",
    explanation.get(
        "potential_causes",
        [],
    ),
)

render_string_list(
    "Recommended Actions",
    explanation.get(
        "recommended_actions",
        [],
    ),
)

rule_citations = explanation.get(
    "rule_citations",
    [],
)

render_string_list(
    "Rule Citations",
    rule_citations,
)


# ---------------------------------------------------------
# Human-review form
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Reviewer Decision")

decision_default = existing_review.get(
    "decision",
    "NEEDS INVESTIGATION",
)

review_status_default = existing_review.get(
    "review_status",
    "NEW",
)

ai_assessment_default = existing_review.get(
    "ai_assessment",
    "NOT REVIEWED",
)

risk_override_default = existing_review.get(
    "risk_override",
    "NO OVERRIDE",
)

decision_index = DECISIONS.index(
    decision_default
) if decision_default in DECISIONS else 0

status_index = REVIEW_STATUSES.index(
    review_status_default
) if review_status_default in REVIEW_STATUSES else 0

ai_index = AI_ASSESSMENTS.index(
    ai_assessment_default
) if ai_assessment_default in AI_ASSESSMENTS else 3

risk_override_index = RISK_LEVELS.index(
    risk_override_default
) if risk_override_default in RISK_LEVELS else 0


existing_due_date = existing_review.get(
    "due_date"
)

try:
    default_due_date = (
        datetime.strptime(
            existing_due_date,
            "%Y-%m-%d",
        ).date()
        if existing_due_date
        else date.today() + timedelta(days=3)
    )

except ValueError:
    default_due_date = (
        date.today() + timedelta(days=3)
    )


with st.form(
    key=f"human_review_form_{selected_invoice}"
):
    form1, form2 = st.columns(2)

    with form1:
        reviewer_name = st.text_input(
            "Reviewer Name *",
            value=existing_review.get(
                "reviewer_name",
                "",
            ),
            placeholder="Enter reviewer name",
        )

        assigned_owner = st.text_input(
            "Assigned Owner *",
            value=existing_review.get(
                "assigned_owner",
                "",
            ),
            placeholder="Enter investigation owner",
        )

        decision = st.selectbox(
            "Review Decision *",
            DECISIONS,
            index=decision_index,
        )

        review_status = st.selectbox(
            "Review Status *",
            REVIEW_STATUSES,
            index=status_index,
        )

    with form2:
        due_date = st.date_input(
            "Due Date",
            value=default_due_date,
            min_value=date.today(),
        )

        ai_assessment = st.selectbox(
            "AI Explanation Assessment",
            AI_ASSESSMENTS,
            index=ai_index,
        )

        risk_override = st.selectbox(
            "Risk-Level Override",
            RISK_LEVELS,
            index=risk_override_index,
            help=(
                "Select No Override to retain the "
                "system-generated risk level."
            ),
        )

        effective_risk_preview = (
            determine_effective_risk(
                original_risk,
                risk_override,
            )
        )

        st.info(
            "Effective risk after review: "
            f"{effective_risk_preview}"
        )

    reviewer_comments = st.text_area(
        "Reviewer Comments *",
        value=existing_review.get(
            "reviewer_comments",
            "",
        ),
        height=130,
        placeholder=(
            "Record whether the numerical evidence and "
            "likely causes are accepted."
        ),
    )

    false_positive_reason = st.text_area(
        "False-Positive Reason",
        value=existing_review.get(
            "false_positive_reason",
            "",
        ),
        height=90,
        placeholder=(
            "Required when the decision is FALSE POSITIVE."
        ),
    )

    resolution_notes = st.text_area(
        "Resolution Notes",
        value=existing_review.get(
            "resolution_notes",
            "",
        ),
        height=120,
        placeholder=(
            "Describe the final outcome, correction or "
            "business justification."
        ),
    )

    supporting_evidence = st.text_area(
        "Supporting Evidence",
        value=existing_review.get(
            "supporting_evidence",
            "",
        ),
        height=100,
        placeholder=(
            "Example: tariff reference checked, meter data "
            "verified, historical invoice compared."
        ),
    )

    acknowledgement = st.checkbox(
        "I confirm that the decision is based on human review "
        "and not solely on the AI recommendation."
    )

    save_review = st.form_submit_button(
        "Save Human Review",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------
# Save review
# ---------------------------------------------------------
if save_review:
    validation_errors = validate_review(
        decision,
        reviewer_name,
        assigned_owner,
        reviewer_comments,
        resolution_notes,
        false_positive_reason,
    )

    if not acknowledgement:
        validation_errors.append(
            "Reviewer acknowledgement is required."
        )

    if validation_errors:
        for validation_error in validation_errors:
            st.error(validation_error)

    else:
        review_record = build_review_record(
            selected_invoice,
            safe_invoice_alias,
            reviewer_name,
            assigned_owner,
            decision,
            review_status,
            due_date,
            ai_assessment,
            original_risk,
            risk_override,
            reviewer_comments,
            false_positive_reason,
            resolution_notes,
            supporting_evidence,
            rule_citations,
            existing_review,
        )

        audit_entry = create_audit_entry(
            review_record,
            existing_review,
        )

        save_review(
            review_record,
            audit_entry,
        )

        st.success(
            "Human review saved successfully."
        )

        st.rerun()


# ---------------------------------------------------------
# Saved review
# ---------------------------------------------------------
saved_review = get_existing_review(
    selected_invoice
)

if saved_review:
    st.markdown("---")
    st.subheader("Saved Human-Review Result")

    result1, result2, result3, result4 = st.columns(4)

    result1.metric(
        "Decision",
        saved_review["decision"],
    )

    result2.metric(
        "Status",
        saved_review["review_status"],
    )

    result3.metric(
        "Effective Risk",
        saved_review[
            "effective_risk_level"
        ],
    )

    result4.metric(
        "Assigned Owner",
        saved_review["assigned_owner"],
    )

    st.write(
        "**Reviewer:**",
        saved_review["reviewer_name"],
    )

    st.write(
        "**Due date:**",
        saved_review["due_date"],
    )

    st.write(
        "**AI explanation assessment:**",
        saved_review["ai_assessment"],
    )

    st.write(
        "**Reviewer comments:**",
        saved_review["reviewer_comments"],
    )

    if saved_review["false_positive_reason"]:
        st.write(
            "**False-positive reason:**",
            saved_review[
                "false_positive_reason"
            ],
        )

    if saved_review["resolution_notes"]:
        st.write(
            "**Resolution notes:**",
            saved_review[
                "resolution_notes"
            ],
        )

    if saved_review["supporting_evidence"]:
        st.write(
            "**Supporting evidence:**",
            saved_review[
                "supporting_evidence"
            ],
        )

    st.caption(
        "Created: "
        f"{saved_review['created_at']} | "
        "Last updated: "
        f"{saved_review['updated_at']}"
    )

    review_json = json.dumps(
        saved_review,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    st.download_button(
        "Download Human-Review Record",
        data=review_json,
        file_name=(
            f"{safe_invoice_alias}"
            "_human_review.json"
        ),
        mime="application/json",
        use_container_width=True,
    )


# ---------------------------------------------------------
# Audit history
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Review Audit History")

invoice_audit_history = get_audit_history(
    selected_invoice
)

if not invoice_audit_history:
    st.info(
        "No human-review audit entries exist "
        "for this invoice."
    )

else:
    audit_rows = []

    for audit_entry in invoice_audit_history:
        audit_rows.append(
            {
                "Timestamp": audit_entry[
                    "audit_timestamp"
                ],
                "Reviewer": audit_entry[
                    "reviewer_name"
                ],
                "Decision": audit_entry[
                    "decision"
                ],
                "Status": audit_entry[
                    "review_status"
                ],
                "Effective Risk": audit_entry[
                    "effective_risk_level"
                ],
                "Changes": format_changes(
                    audit_entry[
                        "changed_fields"
                    ]
                ),
            }
        )

    audit_df = pd.DataFrame(
        audit_rows
    )

    st.dataframe(
        audit_df,
        use_container_width=True,
        hide_index=True,
    )

    audit_json = json.dumps(
        invoice_audit_history,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    st.download_button(
        "Download Review Audit History",
        data=audit_json,
        file_name=(
            f"{safe_invoice_alias}"
            "_review_audit_history.json"
        ),
        mime="application/json",
        use_container_width=True,
    )


# ---------------------------------------------------------
# Review queue
# ---------------------------------------------------------
st.markdown("---")
st.subheader("Human-Review Queue")

review_queue_rows = []

all_saved_reviews = get_all_reviews()

for review in all_saved_reviews:
    invoice_number = review["invoice_number"]
    review_queue_rows.append(
        {
            "Safe Invoice Alias": review.get(
                "safe_invoice_alias"
            ),
            "Decision": review.get(
                "decision"
            ),
            "Status": review.get(
                "review_status"
            ),
            "Original Risk": review.get(
                "original_risk_level"
            ),
            "Effective Risk": review.get(
                "effective_risk_level"
            ),
            "Reviewer": review.get(
                "reviewer_name"
            ),
            "Owner": review.get(
                "assigned_owner"
            ),
            "Due Date": review.get(
                "due_date"
            ),
            "AI Assessment": review.get(
                "ai_assessment"
            ),
            "Updated At": review.get(
                "updated_at"
            ),
        }
    )

if review_queue_rows:
    review_queue_df = pd.DataFrame(
        review_queue_rows
    )

    st.dataframe(
        review_queue_df,
        use_container_width=True,
        hide_index=True,
    )

    review_queue_csv = review_queue_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download Human-Review Queue",
        data=review_queue_csv,
        file_name="d2021_human_review_queue.csv",
        mime="text/csv",
        use_container_width=True,
    )

else:
    st.info(
        "No human reviews have been saved."
    )


if saved_review:
    latest_result = st.session_state.get(
        "latest_result"
    )

    if latest_result:
        latest_result["status"] = (
            "HUMAN_REVIEW_COMPLETED"
        )

    st.markdown("---")
    st.success(
        "The human-review decision is available "
        "for the Final Dashboard and Report."
    )
import json
from datetime import date, datetime, timezone
from typing import Any

from assurance.repository import (
    get_connection,
    get_invoice_result,
    utc_timestamp,
)


ACTIVE_QUERY_STATUSES = {
    "OPEN",
    "AWAITING RESPONSE",
    "RESPONSE RECEIVED",
    "CLARIFICATION REQUIRED",
    "RESPONSE REJECTED",
}

ALLOWED_QUERY_STATUSES = {
    *ACTIVE_QUERY_STATUSES,
    "RESPONSE ACCEPTED",
    "RESOLVED",
    "CLOSED",
}


def parse_date(
    value: str | None,
) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(
            str(value)[:10]
        )

    except ValueError:
        return None


def calculate_ageing(
    created_at: str,
    due_date: str,
    query_status: str,
) -> dict[str, Any]:
    today = datetime.now(
        timezone.utc
    ).date()

    created = parse_date(created_at)

    due = parse_date(due_date)

    age_days = (
        max(
            (today - created).days,
            0,
        )
        if created
        else 0
    )

    closed_status = query_status in {
        "RESPONSE ACCEPTED",
        "RESOLVED",
        "CLOSED",
    }

    overdue_days = (
        max(
            (today - due).days,
            0,
        )
        if due and not closed_status
        else 0
    )

    return {
        "age_days": age_days,
        "overdue": overdue_days > 0,
        "overdue_days": overdue_days,
    }


def deserialize_query(
    row,
) -> dict[str, Any] | None:
    if row is None:
        return None

    result = dict(row)

    result["evidence"] = json.loads(
        result.pop(
            "evidence_json"
        )
        or "{}"
    )

    result.update(
        calculate_ageing(
            created_at=result[
                "created_at"
            ],
            due_date=result[
                "due_date"
            ],
            query_status=result[
                "query_status"
            ],
        )
    )

    return result


def get_query(
    query_id: int,
) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM supplier_queries
            WHERE query_id = ?
            """,
            (query_id,),
        ).fetchone()

    return deserialize_query(row)


def get_active_query_for_invoice(
    run_id: str,
    invoice_number: str,
) -> dict[str, Any] | None:
    placeholders = ", ".join(
        "?"
        for _ in ACTIVE_QUERY_STATUSES
    )

    parameters = [
        run_id,
        invoice_number,
        *sorted(
            ACTIVE_QUERY_STATUSES
        ),
    ]

    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT *
            FROM supplier_queries
            WHERE
                run_id = ?
                AND invoice_number = ?
                AND query_status IN (
                    {placeholders}
                )
            ORDER BY query_id DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()

    return deserialize_query(row)


def create_query(
    run_id: str,
    invoice_number: str,
    owner: str,
    due_date: str,
) -> dict[str, Any]:
    invoice = get_invoice_result(
        run_id,
        invoice_number,
    )

    if invoice is None:
        raise ValueError(
            "Invoice assurance result was not found."
        )

    if not invoice[
        "requires_supplier_query"
    ]:
        raise ValueError(
            "The selected invoice does not require "
            "a supplier query."
        )

    existing_query = (
        get_active_query_for_invoice(
            run_id,
            invoice_number,
        )
    )

    if existing_query is not None:
        raise ValueError(
            "An active supplier query already exists "
            f"for this invoice: "
            f"{existing_query['query_reference']}."
        )

    parsed_due_date = parse_date(
        due_date
    )

    if parsed_due_date is None:
        raise ValueError(
            "A valid supplier-query due date "
            "is required."
        )

    today = datetime.now(
        timezone.utc
    ).date()

    if parsed_due_date < today:
        raise ValueError(
            "The supplier-query due date "
            "cannot be in the past."
        )

    timestamp = utc_timestamp()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO supplier_queries (
                query_reference,
                run_id,
                invoice_number,
                safe_invoice_alias,
                disputed_amount,
                issue_summary,
                evidence_json,
                requested_action,
                owner,
                due_date,
                query_status,
                supplier_response,
                final_resolution,
                recovered_value,
                created_at,
                updated_at
            )
            VALUES (
                NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'OPEN', '', '', 0, ?, ?
            )
            """,
            (
                run_id,
                invoice_number,
                invoice[
                    "safe_invoice_alias"
                ],
                float(
                    invoice[
                        "estimated_exposure"
                    ]
                    or 0
                ),
                invoice[
                    "decision_reason"
                ],
                json.dumps(
                    {
                        "risk_level": (
                            invoice[
                                "risk_level"
                            ]
                        ),
                        "risk_score": (
                            invoice[
                                "risk_score"
                            ]
                        ),
                        "anomaly_score": (
                            invoice[
                                "anomaly_score"
                            ]
                        ),
                        "reconciliation_status": (
                            invoice[
                                "reconciliation_status"
                            ]
                        ),
                        "reconciliation_variance": (
                            invoice[
                                "reconciliation_variance"
                            ]
                        ),
                        "unusual_features": (
                            invoice[
                                "unusual_features"
                            ]
                        ),
                        "validation_findings": (
                            invoice[
                                "validation_findings"
                            ]
                        ),
                        "rule_citations": (
                            invoice[
                                "rule_citations"
                            ]
                        ),
                    }
                ),
                (
                    "Provide the source billing values, "
                    "effective tariff or rate, charge "
                    "calculation, and supporting evidence "
                    "for the disputed amount."
                ),
                owner.strip()
                or "Supplier Query Team",
                parsed_due_date.isoformat(),
                timestamp,
                timestamp,
            ),
        )

        query_id = cursor.lastrowid

        query_reference = (
            f"SQ-{today.year}-"
            f"{query_id:05d}"
        )

        connection.execute(
            """
            UPDATE supplier_queries
            SET query_reference = ?
            WHERE query_id = ?
            """,
            (
                query_reference,
                query_id,
            ),
        )

        connection.execute(
            """
            UPDATE invoice_assurance_results
            SET
                workflow_status =
                    'AWAITING SUPPLIER',
                owner = ?,
                due_date = ?,
                updated_at = ?
            WHERE
                run_id = ?
                AND invoice_number = ?
            """,
            (
                owner.strip()
                or "Supplier Query Team",
                parsed_due_date.isoformat(),
                timestamp,
                run_id,
                invoice_number,
            ),
        )

        connection.execute(
            """
            INSERT INTO assurance_audit_history (
                run_id,
                invoice_number,
                event_type,
                event_payload_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                invoice_number,
                "SUPPLIER_QUERY_CREATED",
                json.dumps(
                    {
                        "query_reference": (
                            query_reference
                        ),
                        "due_date": (
                            parsed_due_date
                            .isoformat()
                        ),
                        "disputed_amount": (
                            invoice[
                                "estimated_exposure"
                            ]
                        ),
                    }
                ),
                timestamp,
            ),
        )

    return get_query(query_id)


def list_queries() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM supplier_queries
            ORDER BY
                CASE query_status
                    WHEN 'OPEN' THEN 1
                    WHEN 'AWAITING RESPONSE'
                        THEN 2
                    WHEN 'RESPONSE RECEIVED'
                        THEN 3
                    WHEN 'CLARIFICATION REQUIRED'
                        THEN 4
                    WHEN 'RESPONSE REJECTED'
                        THEN 5
                    WHEN 'RESPONSE ACCEPTED'
                        THEN 6
                    WHEN 'RESOLVED' THEN 7
                    WHEN 'CLOSED' THEN 8
                    ELSE 9
                END,
                due_date,
                created_at DESC
            """
        ).fetchall()

    return [
        deserialize_query(row)
        for row in rows
    ]


def update_query(
    query_id: int,
    query_status: str,
    supplier_response: str,
    final_resolution: str,
    recovered_value: float,
) -> dict[str, Any]:
    normalized_status = str(
        query_status
    ).strip().upper()

    if (
        normalized_status
        not in ALLOWED_QUERY_STATUSES
    ):
        raise ValueError(
            "Invalid supplier-query status."
        )

    existing = get_query(query_id)

    if existing is None:
        raise ValueError(
            "Supplier query was not found."
        )

    response_required_statuses = {
        "RESPONSE RECEIVED",
        "CLARIFICATION REQUIRED",
        "RESPONSE ACCEPTED",
        "RESPONSE REJECTED",
        "RESOLVED",
        "CLOSED",
    }

    if (
        normalized_status
        in response_required_statuses
        and not supplier_response.strip()
    ):
        raise ValueError(
            "Supplier response is required "
            "for the selected status."
        )

    resolution_required_statuses = {
        "RESPONSE ACCEPTED",
        "RESOLVED",
        "CLOSED",
    }

    if (
        normalized_status
        in resolution_required_statuses
        and not final_resolution.strip()
    ):
        raise ValueError(
            "Final resolution is required "
            "for the selected status."
        )

    disputed_amount = max(
        float(
            existing[
                "disputed_amount"
            ]
            or 0
        ),
        0.0,
    )

    recovered = max(
        float(
            recovered_value
            or 0
        ),
        0.0,
    )

    if recovered > disputed_amount:
        raise ValueError(
            "Recovered value cannot exceed "
            "the disputed amount."
        )

    timestamp = utc_timestamp()

    if normalized_status in {
        "RESPONSE ACCEPTED",
        "RESOLVED",
    }:
        invoice_workflow_status = (
            "RESOLVED"
        )

    elif normalized_status == "CLOSED":
        invoice_workflow_status = (
            "CLOSED"
        )

    elif normalized_status in {
        "CLARIFICATION REQUIRED",
        "RESPONSE REJECTED",
        "AWAITING RESPONSE",
        "OPEN",
    }:
        invoice_workflow_status = (
            "AWAITING SUPPLIER"
        )

    else:
        invoice_workflow_status = (
            "IN REVIEW"
        )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE supplier_queries
            SET
                query_status = ?,
                supplier_response = ?,
                final_resolution = ?,
                recovered_value = ?,
                updated_at = ?
            WHERE query_id = ?
            """,
            (
                normalized_status,
                supplier_response.strip(),
                final_resolution.strip(),
                recovered,
                timestamp,
                query_id,
            ),
        )

        connection.execute(
            """
            UPDATE invoice_assurance_results
            SET
                workflow_status = ?,
                confirmed_root_cause =
                    CASE
                        WHEN ? != ''
                        THEN ?
                        ELSE confirmed_root_cause
                    END,
                resolution_notes =
                    CASE
                        WHEN ? != ''
                        THEN ?
                        ELSE resolution_notes
                    END,
                updated_at = ?
            WHERE
                run_id = ?
                AND invoice_number = ?
            """,
            (
                invoice_workflow_status,
                final_resolution.strip(),
                final_resolution.strip(),
                final_resolution.strip(),
                (
                    "Supplier query "
                    f"{existing['query_reference']}: "
                    f"{final_resolution.strip()}"
                ),
                timestamp,
                existing["run_id"],
                existing[
                    "invoice_number"
                ],
            ),
        )

        connection.execute(
            """
            INSERT INTO assurance_audit_history (
                run_id,
                invoice_number,
                event_type,
                event_payload_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                existing["run_id"],
                existing[
                    "invoice_number"
                ],
                "SUPPLIER_QUERY_UPDATED",
                json.dumps(
                    {
                        "query_reference": (
                            existing[
                                "query_reference"
                            ]
                        ),
                        "query_status": (
                            normalized_status
                        ),
                        "recovered_value": (
                            recovered
                        ),
                        "invoice_workflow_status": (
                            invoice_workflow_status
                        ),
                    }
                ),
                timestamp,
            ),
        )

    return get_query(query_id)


def get_query_summary() -> dict[str, Any]:
    queries = list_queries()

    open_queries = [
        query
        for query in queries
        if query["query_status"]
        in ACTIVE_QUERY_STATUSES
    ]

    return {
        "total_queries": len(queries),
        "open_queries": len(
            open_queries
        ),
        "overdue_queries": sum(
            query["overdue"]
            for query in open_queries
        ),
        "total_disputed_amount": round(
            sum(
                float(
                    query[
                        "disputed_amount"
                    ]
                    or 0
                )
                for query in open_queries
            ),
            2,
        ),
        "total_recovered_value": round(
            sum(
                float(
                    query[
                        "recovered_value"
                    ]
                    or 0
                )
                for query in queries
            ),
            2,
        ),
    }
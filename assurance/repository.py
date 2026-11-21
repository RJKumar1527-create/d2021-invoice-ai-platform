import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from assurance.models import DailyProcessingRun


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "billing_finance_ops.db"
)


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_connection():
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def initialise_repository():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS processing_runs (
                run_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                status TEXT NOT NULL,
                source_files_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                total_invoices INTEGER NOT NULL,
                total_invoice_value REAL NOT NULL,
                safe_to_progress INTEGER NOT NULL,
                exceptions INTEGER NOT NULL,
                held_invoice_value REAL NOT NULL,
                estimated_exposure REAL NOT NULL,
                supplier_queries INTEGER NOT NULL,
                critical_exceptions INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invoice_assurance_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                safe_invoice_alias TEXT NOT NULL,
                source_file TEXT NOT NULL,
                invoice_type TEXT,
                billing_period_start TEXT,
                billing_period_end TEXT,
                invoice_value REAL NOT NULL,
                risk_score REAL NOT NULL,
                risk_level TEXT NOT NULL,
                anomaly_score REAL NOT NULL,
                reconciliation_status TEXT,
                reconciliation_variance REAL NOT NULL,
                estimated_exposure REAL NOT NULL,
                exposure_percentage REAL NOT NULL,
                exposure_basis TEXT,
                exposure_confidence TEXT,
                decision TEXT NOT NULL,
                decision_reason TEXT NOT NULL,
                exception_category TEXT,
                priority TEXT,
                requires_supplier_query INTEGER NOT NULL,
                blocks_approval INTEGER NOT NULL,
                assurance_status TEXT NOT NULL,
                recommended_actions_json TEXT NOT NULL,
                unusual_features_json TEXT NOT NULL,
                validation_findings_json TEXT NOT NULL,
                rule_citations_json TEXT NOT NULL,
                workflow_status TEXT NOT NULL,
                owner TEXT,
                due_date TEXT,
                confirmed_root_cause TEXT,
                resolution_notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (
                    run_id,
                    invoice_number
                ),
                FOREIGN KEY(run_id)
                    REFERENCES processing_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS supplier_queries (
                query_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_reference TEXT UNIQUE,
                run_id TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                safe_invoice_alias TEXT NOT NULL,
                disputed_amount REAL NOT NULL,
                issue_summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                requested_action TEXT NOT NULL,
                owner TEXT,
                due_date TEXT,
                query_status TEXT NOT NULL,
                supplier_response TEXT,
                final_resolution TEXT,
                recovered_value REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assurance_audit_history (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                invoice_number TEXT,
                event_type TEXT NOT NULL,
                event_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_assurance_run
            ON invoice_assurance_results(run_id);

            CREATE INDEX IF NOT EXISTS idx_assurance_decision
            ON invoice_assurance_results(decision);

            CREATE INDEX IF NOT EXISTS idx_assurance_workflow
            ON invoice_assurance_results(workflow_status);

            CREATE INDEX IF NOT EXISTS idx_assurance_priority
            ON invoice_assurance_results(priority);
            """
        )


def save_processing_run(
    run: DailyProcessingRun,
    summary: dict[str, Any],
):
    timestamp = utc_timestamp()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO processing_runs (
                run_id,
                run_date,
                status,
                source_files_json,
                started_at,
                completed_at,
                total_invoices,
                total_invoice_value,
                safe_to_progress,
                exceptions,
                held_invoice_value,
                estimated_exposure,
                supplier_queries,
                critical_exceptions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.run_date,
                run.status,
                json.dumps(
                    run.source_files
                ),
                run.started_at,
                run.completed_at,
                summary["total_invoices"],
                summary["total_invoice_value"],
                summary["safe_to_progress"],
                summary["exceptions"],
                summary["held_invoice_value"],
                summary[
                    "estimated_financial_exposure"
                ],
                summary[
                    "supplier_queries_required"
                ],
                summary["critical_exceptions"],
            ),
        )

        for item in run.invoices:
            invoice = item.invoice
            exposure = item.exposure
            decision = item.decision

            workflow_status = (
                "CLEARED"
                if item.assurance_status
                == "CLEARED"
                else "NEW"
            )

            connection.execute(
                """
                INSERT OR REPLACE INTO invoice_assurance_results (
                    run_id,
                    invoice_number,
                    safe_invoice_alias,
                    source_file,
                    invoice_type,
                    billing_period_start,
                    billing_period_end,
                    invoice_value,
                    risk_score,
                    risk_level,
                    anomaly_score,
                    reconciliation_status,
                    reconciliation_variance,
                    estimated_exposure,
                    exposure_percentage,
                    exposure_basis,
                    exposure_confidence,
                    decision,
                    decision_reason,
                    exception_category,
                    priority,
                    requires_supplier_query,
                    blocks_approval,
                    assurance_status,
                    recommended_actions_json,
                    unusual_features_json,
                    validation_findings_json,
                    rule_citations_json,
                    workflow_status,
                    owner,
                    due_date,
                    confirmed_root_cause,
                    resolution_notes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    run.run_id,
                    invoice.invoice_number,
                    invoice.safe_invoice_alias,
                    invoice.source_file,
                    invoice.invoice_type,
                    invoice.billing_period_start,
                    invoice.billing_period_end,
                    invoice.invoice_net_amount,
                    invoice.risk_score,
                    invoice.risk_level,
                    invoice.anomaly_score,
                    invoice.reconciliation_status,
                    invoice.reconciliation_variance,
                    exposure.estimated_exposure,
                    exposure.exposure_percentage,
                    exposure.exposure_basis,
                    exposure.exposure_confidence,
                    decision.decision,
                    decision.decision_reason,
                    decision.exception_category,
                    decision.priority,
                    int(
                        decision
                        .requires_supplier_query
                    ),
                    int(
                        decision.blocks_approval
                    ),
                    item.assurance_status,
                    json.dumps(
                        decision.recommended_actions
                    ),
                    json.dumps(
                        invoice.unusual_features
                    ),
                    json.dumps(
                        invoice.validation_findings
                    ),
                    json.dumps(
                        invoice.rule_citations
                    ),
                    workflow_status,
                    "",
                    "",
                    "",
                    "",
                    item.created_at,
                    timestamp,
                ),
            )

        persisted_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM invoice_assurance_results
            WHERE run_id = ?
            """,
            (
                run.run_id,
            ),
        ).fetchone()[0]

        expected_count = len(
            run.invoices
        )

        if persisted_count != expected_count:
            raise RuntimeError(
                "Processing-run persistence "
                "validation failed: expected "
                f"{expected_count} invoice results "
                f"but found {persisted_count}."
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
            VALUES (?, NULL, ?, ?, ?)
            """,
            (
                run.run_id,
                "PROCESSING_RUN_COMPLETED",
                json.dumps(summary),
                timestamp,
            ),
        )


def list_processing_runs(
    limit: int = 30,
) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM processing_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    output = []

    for row in rows:
        item = dict(row)

        item["source_files"] = json.loads(
            item.pop(
                "source_files_json"
            )
        )

        output.append(item)

    return output


def latest_run_summary():
    runs = list_processing_runs(
        limit=1
    )

    return runs[0] if runs else None


def list_invoice_results(
    run_id: str | None = None,
    exceptions_only: bool = False,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM invoice_assurance_results
        WHERE 1 = 1
    """

    parameters: list[Any] = []

    if run_id:
        sql += " AND run_id = ?"
        parameters.append(run_id)

    if exceptions_only:
        sql += """
            AND assurance_status = 'EXCEPTION'
        """

    sql += """
        ORDER BY
            CASE priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 4
            END,
            estimated_exposure DESC,
            risk_score DESC
    """

    with get_connection() as connection:
        rows = connection.execute(
            sql,
            parameters,
        ).fetchall()

    output = []

    for row in rows:
        item = dict(row)

        for field in [
            "recommended_actions_json",
            "unusual_features_json",
            "validation_findings_json",
            "rule_citations_json",
        ]:
            item[
                field.replace(
                    "_json",
                    "",
                )
            ] = json.loads(
                item.pop(field)
                or "[]"
            )

        item[
            "requires_supplier_query"
        ] = bool(
            item[
                "requires_supplier_query"
            ]
        )

        item["blocks_approval"] = bool(
            item["blocks_approval"]
        )

        output.append(item)

    return output


def get_invoice_result(
    run_id: str,
    invoice_number: str,
):
    results = list_invoice_results(
        run_id=run_id
    )

    for result in results:
        if (
            result["invoice_number"]
            == invoice_number
        ):
            return result

    return None


def update_invoice_resolution(
    run_id: str,
    invoice_number: str,
    workflow_status: str,
    owner: str,
    confirmed_root_cause: str,
    resolution_notes: str,
):
    allowed_statuses = {
        "NEW",
        "IN REVIEW",
        "AWAITING SUPPLIER",
        "CORRECTION REQUIRED",
        "RESOLVED",
        "CLOSED",
        "CLEARED",
    }

    if workflow_status not in (
        allowed_statuses
    ):
        raise ValueError(
            "Invalid workflow status."
        )

    if (
        workflow_status
        in {"RESOLVED", "CLOSED"}
        and not confirmed_root_cause.strip()
    ):
        raise ValueError(
            "Confirmed root cause is required."
        )

    if (
        workflow_status
        in {"RESOLVED", "CLOSED"}
        and not resolution_notes.strip()
    ):
        raise ValueError(
            "Resolution notes are required."
        )

    timestamp = utc_timestamp()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE invoice_assurance_results
            SET
                workflow_status = ?,
                owner = ?,
                confirmed_root_cause = ?,
                resolution_notes = ?,
                updated_at = ?
            WHERE
                run_id = ?
                AND invoice_number = ?
            """,
            (
                workflow_status,
                owner.strip(),
                confirmed_root_cause.strip(),
                resolution_notes.strip(),
                timestamp,
                run_id,
                invoice_number,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "Invoice assurance result "
                "was not found."
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
                "INVOICE_RESOLUTION_UPDATED",
                json.dumps(
                    {
                        "workflow_status": (
                            workflow_status
                        ),
                        "owner": owner,
                        "confirmed_root_cause": (
                            confirmed_root_cause
                        ),
                        "resolution_notes": (
                            resolution_notes
                        ),
                    }
                ),
                timestamp,
            ),
        )

    return get_invoice_result(
        run_id,
        invoice_number,
    )


initialise_repository()

def create_supplier_query(
    run_id: str,
    invoice_number: str,
    owner: str,
    due_date: str,
):
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
                invoice[
                    "estimated_exposure"
                ],
                invoice[
                    "decision_reason"
                ],
                json.dumps(
                    {
                        "risk_level": invoice[
                            "risk_level"
                        ],
                        "reconciliation_status": (
                            invoice[
                                "reconciliation_status"
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
                    "Provide the source values, "
                    "effective tariff, charge calculation, "
                    "and supporting evidence for the "
                    "identified billing difference."
                ),
                owner.strip(),
                due_date.strip(),
                timestamp,
                timestamp,
            ),
        )

        query_id = cursor.lastrowid

        query_reference = (
            f"SQ-{datetime.now().year}-"
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
                workflow_status = 'AWAITING SUPPLIER',
                owner = ?,
                due_date = ?,
                updated_at = ?
            WHERE
                run_id = ?
                AND invoice_number = ?
            """,
            (
                owner.strip(),
                due_date.strip(),
                timestamp,
                run_id,
                invoice_number,
            ),
        )

    return get_supplier_query(
        query_id
    )


def get_supplier_query(
    query_id: int,
):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM supplier_queries
            WHERE query_id = ?
            """,
            (query_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["evidence"] = json.loads(
        result.pop("evidence_json")
        or "{}"
    )

    return result


def list_supplier_queries():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM supplier_queries
            ORDER BY
                CASE query_status
                    WHEN 'OPEN' THEN 1
                    WHEN 'AWAITING RESPONSE' THEN 2
                    WHEN 'RESPONSE RECEIVED' THEN 3
                    WHEN 'RESOLVED' THEN 4
                    ELSE 5
                END,
                due_date,
                created_at DESC
            """
        ).fetchall()

    output = []

    for row in rows:
        result = dict(row)

        result["evidence"] = json.loads(
            result.pop("evidence_json")
            or "{}"
        )

        output.append(result)

    return output


def update_supplier_query(
    query_id: int,
    query_status: str,
    supplier_response: str,
    final_resolution: str,
    recovered_value: float,
):
    allowed_statuses = {
        "OPEN",
        "AWAITING RESPONSE",
        "RESPONSE RECEIVED",
        "RESOLVED",
        "CLOSED",
    }

    if query_status not in allowed_statuses:
        raise ValueError(
            "Invalid supplier-query status."
        )

    if (
        query_status in {
            "RESOLVED",
            "CLOSED",
        }
        and not final_resolution.strip()
    ):
        raise ValueError(
            "Final resolution is required before "
            "resolving the supplier query."
        )

    with get_connection() as connection:
        cursor = connection.execute(
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
                query_status,
                supplier_response.strip(),
                final_resolution.strip(),
                max(
                    float(
                        recovered_value or 0
                    ),
                    0.0,
                ),
                utc_timestamp(),
                query_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "Supplier query was not found."
            )

    return get_supplier_query(
        query_id
    )


def get_report_summary():
    with get_connection() as connection:
        invoice_row = connection.execute(
            """
            SELECT
                COUNT(*) AS invoice_count,
                COALESCE(
                    SUM(invoice_value),
                    0
                ) AS total_invoice_value,
                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status = 'CLEARED'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS cleared_count,
                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status = 'EXCEPTION'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS exception_count,
                COALESCE(
                    SUM(
                        CASE
                            WHEN blocks_approval = 1
                            THEN estimated_exposure
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_exposure
            FROM invoice_assurance_results
            """
        ).fetchone()

        query_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_queries,
                COALESCE(
                    SUM(
                        CASE
                            WHEN query_status NOT IN (
                                'RESOLVED',
                                'CLOSED'
                            )
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS open_queries,
                COALESCE(
                    SUM(recovered_value),
                    0
                ) AS recovered_value
            FROM supplier_queries
            """
        ).fetchone()

    return {
        **dict(invoice_row),
        **dict(query_row),
    }


ACTIVE_EXCEPTION_STATUSES = {
    "NEW",
    "IN REVIEW",
    "AWAITING SUPPLIER",
    "CORRECTION REQUIRED",
}


def list_active_exceptions(
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return unresolved invoices requiring business action.

    Resolved, closed, and cleared invoices are excluded from
    the active Exception Workbench.
    """
    results = list_invoice_results(
        run_id=run_id,
        exceptions_only=True,
    )

    return [
        result
        for result in results
        if result.get(
            "workflow_status"
        )
        in ACTIVE_EXCEPTION_STATUSES
    ]


def list_resolved_exceptions(
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Return resolved and closed assurance exceptions.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM invoice_assurance_results
            WHERE
                assurance_status = 'EXCEPTION'
                AND workflow_status IN (
                    'RESOLVED',
                    'CLOSED'
                )
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    output = []

    for row in rows:
        item = dict(row)

        for field in [
            "recommended_actions_json",
            "unusual_features_json",
            "validation_findings_json",
            "rule_citations_json",
        ]:
            output_name = field.replace(
                "_json",
                "",
            )

            item[output_name] = json.loads(
                item.pop(field)
                or "[]"
            )

        item[
            "requires_supplier_query"
        ] = bool(
            item[
                "requires_supplier_query"
            ]
        )

        item["blocks_approval"] = bool(
            item["blocks_approval"]
        )

        output.append(item)

    return output


def get_invoice_supplier_query(
    run_id: str,
    invoice_number: str,
) -> dict[str, Any] | None:
    """
    Return the latest supplier query for an invoice.
    """
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM supplier_queries
            WHERE
                run_id = ?
                AND invoice_number = ?
            ORDER BY query_id DESC
            LIMIT 1
            """,
            (
                run_id,
                invoice_number,
            ),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    result["evidence"] = json.loads(
        result.pop(
            "evidence_json"
        )
        or "{}"
    )

    return result


def get_ageing_band(
    created_at: str,
    workflow_status: str,
) -> str:
    """
    Group open exceptions into business ageing bands.
    """
    if workflow_status in {
        "RESOLVED",
        "CLOSED",
        "CLEARED",
    }:
        return "Resolved"

    try:
        created_date = datetime.fromisoformat(
            created_at
        ).date()

        age_days = (
            datetime.now(
                timezone.utc
            ).date()
            - created_date
        ).days

    except (
        TypeError,
        ValueError,
    ):
        age_days = 0

    age_days = max(
        age_days,
        0,
    )

    if age_days <= 2:
        return "0-2 days"

    if age_days <= 5:
        return "3-5 days"

    if age_days <= 10:
        return "6-10 days"

    return "More than 10 days"


def get_exception_ageing_summary():
    active_exceptions = (
        list_active_exceptions()
    )

    bands = {
        "0-2 days": 0,
        "3-5 days": 0,
        "6-10 days": 0,
        "More than 10 days": 0,
    }

    for item in active_exceptions:
        band = get_ageing_band(
            item.get(
                "created_at",
                "",
            ),
            item.get(
                "workflow_status",
                "NEW",
            ),
        )

        if band in bands:
            bands[band] += 1

    return {
        "total_active_exceptions": len(
            active_exceptions
        ),
        "ageing_bands": bands,
    }


def get_financial_control_summary():
    """
    Return cumulative assurance, exposure, and recovery figures.
    """
    with get_connection() as connection:
        invoice_row = connection.execute(
            """
            SELECT
                COUNT(*) AS invoices_assured,

                COALESCE(
                    SUM(invoice_value),
                    0
                ) AS total_billed_value,

                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status =
                                'CLEARED'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS cleared_invoices,

                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status =
                                'EXCEPTION'
                                AND workflow_status
                                NOT IN (
                                    'RESOLVED',
                                    'CLOSED'
                                )
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS active_exceptions,

                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status =
                                'EXCEPTION'
                                AND workflow_status
                                IN (
                                    'RESOLVED',
                                    'CLOSED'
                                )
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS resolved_exceptions,

                COALESCE(
                    SUM(
                        CASE
                            WHEN assurance_status =
                                'EXCEPTION'
                                AND workflow_status
                                NOT IN (
                                    'RESOLVED',
                                    'CLOSED'
                                )
                            THEN estimated_exposure
                            ELSE 0
                        END
                    ),
                    0
                ) AS open_exposure,

                COALESCE(
                    SUM(
                        CASE
                            WHEN blocks_approval = 1
                            THEN invoice_value
                            ELSE 0
                        END
                    ),
                    0
                ) AS held_invoice_value

            FROM invoice_assurance_results
            """
        ).fetchone()

        query_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_supplier_queries,

                COALESCE(
                    SUM(
                        CASE
                            WHEN query_status
                            NOT IN (
                                'RESPONSE ACCEPTED',
                                'RESOLVED',
                                'CLOSED'
                            )
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS open_supplier_queries,

                COALESCE(
                    SUM(recovered_value),
                    0
                ) AS recovered_value,

                COALESCE(
                    SUM(
                        CASE
                            WHEN query_status
                            IN (
                                'RESPONSE ACCEPTED',
                                'RESOLVED',
                                'CLOSED'
                            )
                            THEN disputed_amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS resolved_disputed_value

            FROM supplier_queries
            """
        ).fetchone()

    result = {
        **dict(invoice_row),
        **dict(query_row),
    }

    resolved_disputed_value = float(
        result.get(
            "resolved_disputed_value",
            0,
        )
        or 0
    )

    recovered_value = float(
        result.get(
            "recovered_value",
            0,
        )
        or 0
    )

    result["recovery_rate"] = round(
        (
            recovered_value
            / resolved_disputed_value
            * 100
        )
        if resolved_disputed_value > 0
        else 0.0,
        2,
    )

    return result


def list_daily_run_trend(
    limit: int = 30,
) -> list[dict[str, Any]]:
    """
    Return recent daily-run metrics for trend reporting.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                run_id,
                run_date,
                total_invoices,
                total_invoice_value,
                safe_to_progress,
                exceptions,
                held_invoice_value,
                estimated_exposure,
                supplier_queries,
                critical_exceptions
            FROM processing_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in reversed(rows)
    ]


def list_latest_active_exceptions(
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return the latest unresolved assurance result for each
    invoice number.

    Older occurrences remain stored for audit and reporting,
    but do not appear repeatedly in the operational queue.
    """
    sql = """
        WITH ranked_exceptions AS (
            SELECT
                result_id,
                ROW_NUMBER() OVER (
                    PARTITION BY invoice_number
                    ORDER BY
                        created_at DESC,
                        result_id DESC
                ) AS result_rank
            FROM invoice_assurance_results
            WHERE
                assurance_status = 'EXCEPTION'
                AND workflow_status IN (
                    'NEW',
                    'IN REVIEW',
                    'AWAITING SUPPLIER',
                    'CORRECTION REQUIRED'
                )
    """

    parameters: list[Any] = []

    if run_id:
        sql += """
                AND run_id = ?
        """

        parameters.append(
            run_id
        )

    sql += """
        )
        SELECT results.*
        FROM invoice_assurance_results AS results
        INNER JOIN ranked_exceptions AS ranked
            ON ranked.result_id = results.result_id
        WHERE ranked.result_rank = 1
        ORDER BY
            CASE results.priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 5
            END,
            results.estimated_exposure DESC,
            results.risk_score DESC,
            results.created_at DESC
    """

    with get_connection() as connection:
        rows = connection.execute(
            sql,
            parameters,
        ).fetchall()

    output = []

    for row in rows:
        item = dict(row)

        for field in [
            "recommended_actions_json",
            "unusual_features_json",
            "validation_findings_json",
            "rule_citations_json",
        ]:
            output_name = field.replace(
                "_json",
                "",
            )

            item[output_name] = json.loads(
                item.pop(field)
                or "[]"
            )

        item[
            "requires_supplier_query"
        ] = bool(
            item[
                "requires_supplier_query"
            ]
        )

        item["blocks_approval"] = bool(
            item["blocks_approval"]
        )

        output.append(item)

    return output

import json
import sqlite3
from pathlib import Path


DATABASE_PATH = Path("data/d2021_reviews.db")


def get_connection():
    """Create the database directory and return a SQLite connection."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialise_database():
    """Create persistent review and audit tables."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS human_reviews (
                invoice_number TEXT PRIMARY KEY,
                safe_invoice_alias TEXT NOT NULL,
                reviewer_name TEXT NOT NULL,
                assigned_owner TEXT NOT NULL,
                decision TEXT NOT NULL,
                review_status TEXT NOT NULL,
                due_date TEXT,
                ai_assessment TEXT NOT NULL,
                original_risk_level TEXT NOT NULL,
                risk_override TEXT NOT NULL,
                effective_risk_level TEXT NOT NULL,
                reviewer_comments TEXT NOT NULL,
                false_positive_reason TEXT,
                resolution_notes TEXT,
                supporting_evidence TEXT,
                rule_citations_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS human_review_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL,
                safe_invoice_alias TEXT NOT NULL,
                audit_timestamp TEXT NOT NULL,
                reviewer_name TEXT NOT NULL,
                decision TEXT NOT NULL,
                review_status TEXT NOT NULL,
                effective_risk_level TEXT NOT NULL,
                changed_fields_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_review_status
            ON human_reviews(review_status);

            CREATE INDEX IF NOT EXISTS idx_review_owner
            ON human_reviews(assigned_owner);

            CREATE INDEX IF NOT EXISTS idx_audit_invoice
            ON human_review_audit(invoice_number);
            """
        )


def save_review(review_record, audit_entry):
    """Insert or update a review and append its immutable audit entry."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO human_reviews (
                invoice_number,
                safe_invoice_alias,
                reviewer_name,
                assigned_owner,
                decision,
                review_status,
                due_date,
                ai_assessment,
                original_risk_level,
                risk_override,
                effective_risk_level,
                reviewer_comments,
                false_positive_reason,
                resolution_notes,
                supporting_evidence,
                rule_citations_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(invoice_number) DO UPDATE SET
                safe_invoice_alias = excluded.safe_invoice_alias,
                reviewer_name = excluded.reviewer_name,
                assigned_owner = excluded.assigned_owner,
                decision = excluded.decision,
                review_status = excluded.review_status,
                due_date = excluded.due_date,
                ai_assessment = excluded.ai_assessment,
                original_risk_level = excluded.original_risk_level,
                risk_override = excluded.risk_override,
                effective_risk_level = excluded.effective_risk_level,
                reviewer_comments = excluded.reviewer_comments,
                false_positive_reason = excluded.false_positive_reason,
                resolution_notes = excluded.resolution_notes,
                supporting_evidence = excluded.supporting_evidence,
                rule_citations_json = excluded.rule_citations_json,
                updated_at = excluded.updated_at
            """,
            (
                review_record["invoice_number"],
                review_record["safe_invoice_alias"],
                review_record["reviewer_name"],
                review_record["assigned_owner"],
                review_record["decision"],
                review_record["review_status"],
                review_record["due_date"],
                review_record["ai_assessment"],
                review_record["original_risk_level"],
                review_record["risk_override"],
                review_record["effective_risk_level"],
                review_record["reviewer_comments"],
                review_record.get("false_positive_reason", ""),
                review_record.get("resolution_notes", ""),
                review_record.get("supporting_evidence", ""),
                json.dumps(review_record.get("rule_citations", [])),
                review_record["created_at"],
                review_record["updated_at"],
            ),
        )

        connection.execute(
            """
            INSERT INTO human_review_audit (
                invoice_number,
                safe_invoice_alias,
                audit_timestamp,
                reviewer_name,
                decision,
                review_status,
                effective_risk_level,
                changed_fields_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_entry["invoice_number"],
                audit_entry["safe_invoice_alias"],
                audit_entry["audit_timestamp"],
                audit_entry["reviewer_name"],
                audit_entry["decision"],
                audit_entry["review_status"],
                audit_entry["effective_risk_level"],
                json.dumps(audit_entry.get("changed_fields", [])),
            ),
        )


def _review_row_to_dict(row):
    if row is None:
        return {}

    result = dict(row)
    result["rule_citations"] = json.loads(
        result.pop("rule_citations_json") or "[]"
    )
    return result


def get_review(invoice_number):
    """Return one saved review."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM human_reviews
            WHERE invoice_number = ?
            """,
            (str(invoice_number),),
        ).fetchone()

    return _review_row_to_dict(row)


def get_all_reviews():
    """Return the complete review queue."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM human_reviews
            ORDER BY updated_at DESC
            """
        ).fetchall()

    return [_review_row_to_dict(row) for row in rows]


def get_audit_history(invoice_number):
    """Return immutable audit history for one invoice."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM human_review_audit
            WHERE invoice_number = ?
            ORDER BY audit_id ASC
            """,
            (str(invoice_number),),
        ).fetchall()

    history = []

    for row in rows:
        result = dict(row)
        result["changed_fields"] = json.loads(
            result.pop("changed_fields_json") or "[]"
        )
        history.append(result)

    return history


def get_review_summary():
    """Return aggregate counts for the final dashboard."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_reviews,
                SUM(CASE WHEN decision = 'APPROVED' THEN 1 ELSE 0 END)
                    AS approved,
                SUM(CASE WHEN decision = 'FALSE POSITIVE' THEN 1 ELSE 0 END)
                    AS false_positives,
                SUM(CASE WHEN decision = 'QUERY REQUIRED' THEN 1 ELSE 0 END)
                    AS query_required,
                SUM(CASE WHEN decision = 'NEEDS INVESTIGATION' THEN 1 ELSE 0 END)
                    AS needs_investigation,
                SUM(CASE WHEN decision = 'REJECTED' THEN 1 ELSE 0 END)
                    AS rejected,
                SUM(CASE WHEN review_status IN ('RESOLVED', 'CLOSED')
                    THEN 1 ELSE 0 END) AS completed
            FROM human_reviews
            """
        ).fetchone()

    return dict(row) if row else {}

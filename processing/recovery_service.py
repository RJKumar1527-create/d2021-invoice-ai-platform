from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

from processing.daily_file_service import (
    get_registry_connection,
    initialise_registry,
    utc_timestamp,
)


STALE_PROCESSING_MINUTES = 30

PROCESSING_STAGES = {
    "REGISTERED",
    "DECODING",
    "FILE VALIDATION",
    "PARSING",
    "INVOICE VALIDATION",
    "RECONCILIATION",
    "PATTERN ANALYSIS",
    "RISK SCORING",
    "ASSURANCE",
    "PERSISTENCE",
    "COMPLETED",
    "FAILED",
    "RECOVERY REQUIRED",
}

FAILURE_CODES = {
    "FILE_VALIDATION_FAILED",
    "PARSING_FAILED",
    "INVOICE_VALIDATION_FAILED",
    "RECONCILIATION_FAILED",
    "PATTERN_ANALYSIS_FAILED",
    "RISK_SCORING_FAILED",
    "ASSURANCE_FAILED",
    "PERSISTENCE_FAILED",
    "UNEXPECTED_PROCESSING_FAILURE",
    "STALE_PROCESSING",
}


def get_registry_columns(
    connection,
) -> set[str]:
    rows = connection.execute(
        "PRAGMA table_info(file_registry)"
    ).fetchall()

    return {
        str(row["name"])
        for row in rows
    }


def initialise_recovery_schema():
    """
    Create the base file registry when necessary, then add
    recovery columns without deleting existing records.
    """
    initialise_registry()

    with get_registry_connection() as connection:
        columns = get_registry_columns(
            connection
        )

        migrations = [
            (
                "processing_stage",
                """
                ALTER TABLE file_registry
                ADD COLUMN processing_stage TEXT
                NOT NULL DEFAULT 'REGISTERED'
                """,
            ),
            (
                "failure_code",
                """
                ALTER TABLE file_registry
                ADD COLUMN failure_code TEXT
                NOT NULL DEFAULT ''
                """,
            ),
            (
                "last_activity_at",
                """
                ALTER TABLE file_registry
                ADD COLUMN last_activity_at TEXT
                NOT NULL DEFAULT ''
                """,
            ),
            (
                "retry_count",
                """
                ALTER TABLE file_registry
                ADD COLUMN retry_count INTEGER
                NOT NULL DEFAULT 0
                """,
            ),
            (
                "recovery_required",
                """
                ALTER TABLE file_registry
                ADD COLUMN recovery_required INTEGER
                NOT NULL DEFAULT 0
                """,
            ),
            (
                "recovered_at",
                """
                ALTER TABLE file_registry
                ADD COLUMN recovered_at TEXT
                """,
            ),
        ]

        for column_name, sql in migrations:
            if column_name not in columns:
                connection.execute(sql)

        connection.execute(
            """
            UPDATE file_registry
            SET
                processing_stage =
                    CASE processing_status
                        WHEN 'COMPLETED'
                            THEN 'COMPLETED'
                        WHEN 'FAILED'
                            THEN 'FAILED'
                        ELSE processing_stage
                    END,

                last_activity_at =
                    CASE
                        WHEN last_activity_at = ''
                        THEN COALESCE(
                            completed_at,
                            received_at
                        )
                        ELSE last_activity_at
                    END
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_file_registry_recovery
            ON file_registry(
                processing_status,
                recovery_required,
                last_activity_at
            )
            """
        )


def validate_stage(
    stage: str,
) -> str:
    normalized = str(
        stage
    ).strip().upper()

    if normalized not in PROCESSING_STAGES:
        raise ValueError(
            f"Invalid processing stage: {stage}."
        )

    return normalized


def validate_failure_code(
    failure_code: str,
) -> str:
    normalized = str(
        failure_code
    ).strip().upper()

    if normalized not in FAILURE_CODES:
        raise ValueError(
            f"Invalid failure code: "
            f"{failure_code}."
        )

    return normalized


def update_processing_stage(
    registry_id: int,
    stage: str,
):
    normalized_stage = validate_stage(
        stage
    )

    with get_registry_connection() as connection:
        result = connection.execute(
            """
            UPDATE file_registry
            SET
                processing_stage = ?,
                last_activity_at = ?
            WHERE
                registry_id = ?
                AND processing_status =
                    'PROCESSING'
            """,
            (
                normalized_stage,
                utc_timestamp(),
                registry_id,
            ),
        )

        if result.rowcount != 1:
            raise ValueError(
                "The processing registry record "
                "is unavailable or is no longer "
                "in PROCESSING status."
            )


def record_processing_failure(
    registry_id: int,
    stage: str,
    failure_code: str,
    reason: str,
):
    normalized_stage = validate_stage(
        stage
    )

    normalized_code = (
        validate_failure_code(
            failure_code
        )
    )

    timestamp = utc_timestamp()

    with get_registry_connection() as connection:
        connection.execute(
            """
            UPDATE file_registry
            SET
                processing_status = 'FAILED',
                processing_stage = ?,
                failure_code = ?,
                failure_reason = ?,
                last_activity_at = ?,
                completed_at = ?,
                recovery_required = 0
            WHERE registry_id = ?
            """,
            (
                normalized_stage,
                normalized_code,
                str(reason),
                timestamp,
                timestamp,
                registry_id,
            ),
        )


def stale_cutoff(
    stale_minutes: int,
) -> str:
    if stale_minutes < 1:
        raise ValueError(
            "The stale threshold must be "
            "at least one minute."
        )

    return (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            minutes=stale_minutes
        )
    ).isoformat()


def mark_stale_processing_records(
    stale_minutes: int = (
        STALE_PROCESSING_MINUTES
    ),
) -> int:
    cutoff = stale_cutoff(
        stale_minutes
    )

    timestamp = utc_timestamp()

    with get_registry_connection() as connection:
        result = connection.execute(
            """
            UPDATE file_registry
            SET
                processing_status =
                    'RECOVERY REQUIRED',
                processing_stage =
                    'RECOVERY REQUIRED',
                failure_code =
                    'STALE_PROCESSING',
                failure_reason =
                    'Processing activity exceeded the configured stale threshold.',
                recovery_required = 1,
                last_activity_at = ?,
                completed_at = ?
            WHERE
                processing_status =
                    'PROCESSING'
                AND COALESCE(
                    NULLIF(
                        last_activity_at,
                        ''
                    ),
                    received_at
                ) < ?
            """,
            (
                timestamp,
                timestamp,
                cutoff,
            ),
        )

        return int(
            result.rowcount
        )


def list_recovery_records(
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_registry_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE
                processing_status IN (
                    'FAILED',
                    'RECOVERY REQUIRED'
                )
                OR recovery_required = 1
            ORDER BY
                received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def authorize_retry(
    registry_id: int,
) -> dict[str, Any]:
    """
    Mark a failed or stale record as retry-authorized.

    The file must still be selected again by the user.
    Raw billing content is not retained in the registry.
    """
    timestamp = utc_timestamp()

    with get_registry_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE registry_id = ?
            """,
            (registry_id,),
        ).fetchone()

        if row is None:
            raise ValueError(
                "The file registry record "
                "was not found."
            )

        record = dict(row)

        if record["processing_status"] not in {
            "FAILED",
            "RECOVERY REQUIRED",
        }:
            raise ValueError(
                "Only failed or stale processing "
                "records can be authorized "
                "for retry."
            )

        connection.execute(
            """
            UPDATE file_registry
            SET
                processing_status = 'FAILED',
                processing_stage = 'FAILED',
                failure_code = '',
                failure_reason =
                    'Retry authorized. Select the source file again.',
                recovery_required = 0,
                retry_count =
                    retry_count + 1,
                recovered_at = ?,
                last_activity_at = ?
            WHERE registry_id = ?
            """,
            (
                timestamp,
                timestamp,
                registry_id,
            ),
        )

        updated = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE registry_id = ?
            """,
            (registry_id,),
        ).fetchone()

    return dict(updated)


initialise_recovery_schema()
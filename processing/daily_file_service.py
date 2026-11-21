from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from assurance.service import run_daily_assurance
from processing.legacy_loader import (
    load_processing_modules,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "billing_file_registry.db"
)

MAX_FILE_SIZE_MB = 25

ALLOWED_EXTENSIONS = {
    ".uff",
    ".txt",
}


class DailyFileProcessingError(ValueError):
    """Raised when a billing file cannot be processed."""


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_registry_connection():
    REGISTRY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        REGISTRY_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialise_registry():
    with get_registry_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS file_registry (
                registry_id INTEGER
                    PRIMARY KEY AUTOINCREMENT,

                file_name TEXT NOT NULL,
                file_checksum TEXT NOT NULL UNIQUE,
                file_size_bytes INTEGER NOT NULL,
                detected_encoding TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                invoice_count INTEGER NOT NULL,

                processing_status TEXT NOT NULL,
                processing_run_id TEXT,
                failure_reason TEXT,

                received_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS
            idx_file_registry_received
            ON file_registry(received_at);

            CREATE INDEX IF NOT EXISTS
            idx_file_registry_status
            ON file_registry(processing_status);
            """
        )


def calculate_checksum(
    file_bytes: bytes,
) -> str:
    return hashlib.sha256(
        file_bytes
    ).hexdigest()


def decode_file(
    file_bytes: bytes,
) -> tuple[str, str]:
    encodings = [
        "utf-8-sig",
        "utf-8",
        "windows-1252",
    ]

    for encoding in encodings:
        try:
            text = file_bytes.decode(
                encoding
            )

            return text, encoding

        except UnicodeDecodeError:
            continue

    raise DailyFileProcessingError(
        "The file could not be decoded as "
        "UTF-8 or Windows-1252 text."
    )


def get_non_empty_lines(
    file_text: str,
) -> list[str]:
    return [
        line.strip()
        for line in file_text.splitlines()
        if line.strip()
    ]


def get_record_type(
    line: str,
) -> str:
    if "|" not in line:
        return "INVALID"

    return (
        line.split(
            "|",
            1,
        )[0]
        .strip()
        .upper()
    )


def validate_runtime_file(
    file_name: str,
    file_bytes: bytes,
    lines: list[str],
) -> list[dict[str, Any]]:
    extension = Path(
        file_name
    ).suffix.lower()

    return [
        {
            "check": "File extension",
            "passed": (
                extension
                in ALLOWED_EXTENSIONS
            ),
            "message": (
                "Supported runtime file extension."
                if extension
                in ALLOWED_EXTENSIONS
                else (
                    "Billing files must use "
                    ".uff or .txt."
                )
            ),
        },
        {
            "check": "File content",
            "passed": (
                bool(file_bytes)
                and bool(lines)
            ),
            "message": (
                "File contains readable records."
                if file_bytes and lines
                else "The file is empty."
            ),
        },
        {
            "check": "File size",
            "passed": (
                len(file_bytes)
                <= MAX_FILE_SIZE_MB
                * 1024
                * 1024
            ),
            "message": (
                f"Maximum supported file size is "
                f"{MAX_FILE_SIZE_MB} MB."
            ),
        },
        {
            "check": "Pipe-delimited records",
            "passed": (
                bool(lines)
                and all(
                    "|" in line
                    for line in lines
                )
            ),
            "message": (
                "Every non-empty record must "
                "be pipe-delimited."
            ),
        },
        {
            "check": "ZHV header",
            "passed": (
                bool(lines)
                and get_record_type(
                    lines[0]
                )
                == "ZHV"
            ),
            "message": (
                "The first record must be ZHV."
            ),
        },
        {
            "check": "ZPT trailer",
            "passed": (
                bool(lines)
                and get_record_type(
                    lines[-1]
                )
                == "ZPT"
            ),
            "message": (
                "The final record must be ZPT."
            ),
        },
    ]


def ensure_file_is_valid(
    checks: list[dict[str, Any]],
):
    failures = [
        check["message"]
        for check in checks
        if not check["passed"]
    ]

    if failures:
        raise DailyFileProcessingError(
            "File validation failed: "
            + " ".join(failures)
        )


def find_registry_record(
    checksum: str,
) -> dict[str, Any] | None:
    with get_registry_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE file_checksum = ?
            """,
            (checksum,),
        ).fetchone()

    return dict(row) if row else None


def register_file(
    file_name: str,
    checksum: str,
    file_size_bytes: int,
    encoding: str,
    record_count: int,
) -> int:
    with get_registry_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO file_registry (
                file_name,
                file_checksum,
                file_size_bytes,
                detected_encoding,
                record_count,
                invoice_count,
                processing_status,
                processing_run_id,
                failure_reason,
                received_at,
                completed_at
            )
            VALUES (
                ?, ?, ?, ?, ?, 0,
                'PROCESSING',
                NULL,
                '',
                ?,
                NULL
            )
            """,
            (
                file_name,
                checksum,
                file_size_bytes,
                encoding,
                record_count,
                utc_timestamp(),
            ),
        )

        return int(
            cursor.lastrowid
        )


def complete_registry_record(
    registry_id: int,
    invoice_count: int,
    processing_run_id: str,
):
    with get_registry_connection() as connection:
        connection.execute(
            """
            UPDATE file_registry
            SET
                invoice_count = ?,
                processing_status = 'COMPLETED',
                processing_run_id = ?,
                failure_reason = '',
                processing_stage = 'COMPLETED',
                failure_code = '',
                recovery_required = 0,
                last_activity_at = ?,
                completed_at = ?
            WHERE registry_id = ?
            """,
            (
                invoice_count,
                processing_run_id,
                utc_timestamp(),
                utc_timestamp(),
                registry_id,
            ),
        )


def fail_registry_record(
    registry_id: int,
    reason: str,
):
    with get_registry_connection() as connection:
        connection.execute(
            """
            UPDATE file_registry
            SET
                processing_status = 'FAILED',
                failure_reason = ?,
                completed_at = ?
            WHERE registry_id = ?
            """,
            (
                str(reason),
                utc_timestamp(),
                registry_id,
            ),
        )


def records_from_result(
    value: Any,
    candidate_keys: list[str],
) -> list[dict[str, Any]]:
    """
    Normalize lists, dictionaries, DataFrames, and tuples
    returned by the existing processing modules.
    """
    if value is None:
        return []

    if isinstance(
        value,
        pd.DataFrame,
    ):
        return value.to_dict(
            orient="records"
        )

    if isinstance(value, tuple):
        for item in value:
            rows = records_from_result(
                item,
                candidate_keys,
            )

            if rows:
                return rows

        return []

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    if isinstance(value, dict):
        for key in candidate_keys:
            nested = value.get(key)

            if nested is not None:
                rows = records_from_result(
                    nested,
                    candidate_keys,
                )

                if rows:
                    return rows

        return [value]

    return []


def normalize_validation_results(
    value: Any,
) -> list[dict[str, Any]]:
    return records_from_result(
        value,
        [
            "results",
            "invoices",
            "validation_results",
            "invoice_results",
            "summaries",
        ],
    )


def normalize_reconciliation_results(
    value: Any,
) -> list[dict[str, Any]]:
    return records_from_result(
        value,
        [
            "results",
            "invoices",
            "reconciliation_results",
            "invoice_results",
            "summary",
        ],
    )


def build_anomaly_results(
    parsed_data: dict[str, Any],
    anomaly_module,
) -> list[dict[str, Any]]:
    feature_df = (
        anomaly_module
        .build_invoice_features(
            parsed_data
        )
    )

    if feature_df is None:
        return []

    if not isinstance(
        feature_df,
        pd.DataFrame,
    ):
        feature_df = pd.DataFrame(
            feature_df
        )

    if feature_df.empty:
        return []

    feature_columns = [
        column
        for column in feature_df.columns
        if column
        not in {
            "invoice_number",
            "invoice_type",
            "site_name",
        }
        and pd.api.types.is_numeric_dtype(
            feature_df[column]
        )
    ]

    if not feature_columns:
        return feature_df.to_dict(
            orient="records"
        )

    model_data = (
        feature_df[
            feature_columns
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .fillna(0.0)
        .astype(float)
    )

    sample_count = len(
        model_data
    )

    if sample_count >= 20:
        contamination = min(
            max(
                2 / sample_count,
                0.01,
            ),
            0.10,
        )

        scaler = StandardScaler()

        scaled_data = (
            scaler.fit_transform(
                model_data
            )
        )

        model = IsolationForest(
            n_estimators=300,
            contamination=(
                contamination
            ),
            random_state=42,
            n_jobs=-1,
        )

        predictions = model.fit_predict(
            scaled_data
        )

        decision_scores = (
            model.decision_function(
                scaled_data
            )
        )

        minimum_score = float(
            decision_scores.min()
        )

        maximum_score = float(
            decision_scores.max()
        )

        if maximum_score == minimum_score:
            anomaly_scores = np.zeros(
                sample_count
            )

        else:
            anomaly_scores = (
                (
                    maximum_score
                    - decision_scores
                )
                / (
                    maximum_score
                    - minimum_score
                )
                * 100
            )

    else:
        medians = model_data.median()

        deviations = (
            model_data
            - medians
        ).abs()

        robust_scale = (
            deviations.median()
            .replace(0, 1.0)
        )

        standardized = (
            deviations
            / robust_scale
        )

        raw_scores = standardized.max(
            axis=1
        )

        maximum_score = float(
            raw_scores.max()
        )

        if maximum_score > 0:
            anomaly_scores = (
                raw_scores
                / maximum_score
                * 100
            ).to_numpy()

        else:
            anomaly_scores = np.zeros(
                sample_count
            )

        predictions = np.where(
            anomaly_scores >= 80,
            -1,
            1,
        )

    feature_df = feature_df.copy()

    feature_df[
        "anomaly_score"
    ] = np.round(
        anomaly_scores,
        2,
    )

    feature_df[
        "model_prediction"
    ] = predictions

    medians = model_data.median()

    deviations = (
        model_data
        - medians
    ).abs().median()

    deviations = deviations.replace(
        0,
        1.0,
    )

    unusual_features = []

    reasons = []

    for _, row in model_data.iterrows():
        values = (
            anomaly_module
            .find_unusual_features(
                row,
                feature_columns,
                medians,
                deviations,
            )
        )

        if isinstance(values, str):
            value_list = [
                part.strip()
                for part in values.split(",")
                if part.strip()
            ]

        elif isinstance(
            values,
            (
                list,
                tuple,
                set,
            ),
        ):
            value_list = [
                str(value)
                for value in values
            ]

        else:
            value_list = []

        unusual_features.append(
            value_list
        )

        reasons.append(
            ", ".join(value_list)
        )

    feature_df[
        "unusual_features"
    ] = unusual_features

    feature_df["reason"] = reasons

    feature_df["risk_level"] = (
        feature_df.apply(
            anomaly_module.assign_risk,
            axis=1,
        )
    )

    return feature_df.to_dict(
        orient="records"
    )


def normalize_risk_results(
    value: Any,
) -> list[dict[str, Any]]:
    """
    Convert legacy risk results into the field names
    expected by the assurance adapter.
    """
    rows = records_from_result(
        value,
        [
            "results",
            "risk_results",
            "invoices",
        ],
    )

    normalized = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        invoice_number = (
            row.get("Invoice Number")
            or row.get("invoice_number")
            or row.get("invoice_reference")
            or row.get("Invoice")
            or ""
        )

        risk_score = float(
            row.get(
                "Final Risk Score",
                row.get(
                    "risk_score",
                    row.get(
                        "score",
                        0,
                    ),
                ),
            )
            or 0
        )

        risk_level = str(
            row.get("Risk Level")
            or row.get("risk_level")
            or row.get("level")
            or "LOW"
        ).upper()

        anomaly_score = float(
            row.get(
                "Anomaly Score",
                row.get(
                    "anomaly_score",
                    0,
                ),
            )
            or 0
        )

        model_result = str(
            row.get("Model Result")
            or row.get("model_result")
            or row.get("classification")
            or "NORMAL"
        ).upper()

        unusual_features = (
            row.get("Unusual Features")
            or row.get("unusual_features")
            or []
        )

        if isinstance(
            unusual_features,
            str,
        ):
            unusual_features = [
                item.strip()
                for item in unusual_features.split(",")
                if item.strip()
            ]

        normalized.append(
            {
                "invoice_number": str(
                    invoice_number
                ).strip(),
                "invoice_type": (
                    row.get("Invoice Type")
                    or row.get("invoice_type")
                    or ""
                ),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "anomaly_score": anomaly_score,
                "model_result": model_result,
                "unusual_features": (
                    unusual_features
                ),
                "explanation": (
                    row.get("Explanation")
                    or row.get("explanation")
                    or ""
                ),
                "recommended_action": (
                    row.get(
                        "Recommended Action"
                    )
                    or row.get(
                        "recommended_action"
                    )
                    or ""
                ),
            }
        )

    return normalized


def process_runtime_file(
    file_name: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    if not file_name:
        raise DailyFileProcessingError(
            "A file name is required."
        )

    if not file_bytes:
        raise DailyFileProcessingError(
            "The uploaded billing file is empty."
        )

    checksum = calculate_checksum(
        file_bytes
    )

    existing = find_registry_record(
        checksum
    )

    if existing is not None:
        existing_status = str(
            existing.get(
                "processing_status",
                "",
            )
        ).upper()

        if existing_status == "FAILED":
            with get_registry_connection() as connection:
                connection.execute(
                    """
                    DELETE FROM file_registry
                    WHERE
                        registry_id = ?
                        AND processing_status = 'FAILED'
                    """,
                    (
                        existing["registry_id"],
                    ),
                )

        else:
            raise DailyFileProcessingError(
                "This billing file has already been "
                "registered. "
                f"Status: "
                f"{existing_status}; "
                f"run: "
                f"{existing['processing_run_id'] or 'not available'}."
            )

    file_text, encoding = decode_file(
        file_bytes
    )

    lines = get_non_empty_lines(
        file_text
    )

    validation_checks = (
        validate_runtime_file(
            file_name=file_name,
            file_bytes=file_bytes,
            lines=lines,
        )
    )

    ensure_file_is_valid(
        validation_checks
    )

    from processing.recovery_service import (
        initialise_recovery_schema,
    )

    initialise_recovery_schema()

    registry_id = register_file(
        file_name=file_name,
        checksum=checksum,
        file_size_bytes=len(
            file_bytes
        ),
        encoding=encoding,
        record_count=len(lines),
    )

    from processing.recovery_service import (
        record_processing_failure,
        update_processing_stage,
    )

    current_stage = "REGISTERED"

    failure_codes = {
        "REGISTERED": (
            "UNEXPECTED_PROCESSING_FAILURE"
        ),
        "PARSING": "PARSING_FAILED",
        "INVOICE VALIDATION": (
            "INVOICE_VALIDATION_FAILED"
        ),
        "RECONCILIATION": (
            "RECONCILIATION_FAILED"
        ),
        "PATTERN ANALYSIS": (
            "PATTERN_ANALYSIS_FAILED"
        ),
        "RISK SCORING": (
            "RISK_SCORING_FAILED"
        ),
        "ASSURANCE": "ASSURANCE_FAILED",
        "PERSISTENCE": (
            "PERSISTENCE_FAILED"
        ),
    }

    def enter_stage(
        stage,
    ):
        nonlocal current_stage

        current_stage = stage

        update_processing_stage(
            registry_id=registry_id,
            stage=stage,
        )

    try:
        modules = (
            load_processing_modules()
        )

        enter_stage(
            "PARSING"
        )

        parsed_data = (
            modules["parser"]
            .parse_d2021(lines)
        )

        if not isinstance(
            parsed_data,
            dict,
        ):
            raise DailyFileProcessingError(
                "The parser did not return "
                "structured invoice data."
            )

        invoices = parsed_data.get(
            "invoices",
            [],
        )

        if not invoices:
            raise DailyFileProcessingError(
                "No invoices were identified "
                "in the billing file."
            )

        enter_stage(
            "INVOICE VALIDATION"
        )

        raw_validation = (
            modules["validation"]
            .validate_invoices(
                parsed_data
            )
        )

        enter_stage(
            "RECONCILIATION"
        )

        raw_reconciliation = (
            modules[
                "reconciliation"
            ]
            .reconcile_invoices(
                parsed_data
            )
        )

        validation_rows = (
            normalize_validation_results(
                raw_validation
            )
        )

        reconciliation_rows = (
            normalize_reconciliation_results(
                raw_reconciliation
            )
        )

        enter_stage(
            "PATTERN ANALYSIS"
        )

        anomaly_rows = (
            build_anomaly_results(
                parsed_data,
                modules["anomaly"],
            )
        )

        enter_stage(
            "RISK SCORING"
        )

        raw_risk = (
            modules["risk"]
            .create_risk_results(
                parsed_data,
                validation_rows,
                reconciliation_rows,
                anomaly_rows,
            )
        )

        risk_rows = (
            normalize_risk_results(
                raw_risk
            )
        )

        enter_stage(
            "ASSURANCE"
        )

        assurance_result = (
            run_daily_assurance(
                parsed_data=parsed_data,
                validation_results=(
                    validation_rows
                ),
                reconciliation_results=(
                    reconciliation_rows
                ),
                anomaly_results=(
                    anomaly_rows
                ),
                risk_results=risk_rows,
                source_files=[
                    file_name
                ],
            )
        )

        enter_stage(
            "PERSISTENCE"
        )

        processing_run_id = (
            assurance_result[
                "summary"
            ][
                "run_id"
            ]
        )

        complete_registry_record(
            registry_id=registry_id,
            invoice_count=len(
                invoices
            ),
            processing_run_id=(
                processing_run_id
            ),
        )

        return {
            "file": {
                "file_name": file_name,
                "checksum": checksum,
                "file_size_bytes": len(
                    file_bytes
                ),
                "detected_encoding": (
                    encoding
                ),
                "record_count": len(
                    lines
                ),
                "invoice_count": len(
                    invoices
                ),
                "validation_checks": (
                    validation_checks
                ),
            },
            "pipeline": {
                "validation_results": (
                    len(validation_rows)
                ),
                "reconciliation_results": (
                    len(
                        reconciliation_rows
                    )
                ),
                "anomaly_results": len(
                    anomaly_rows
                ),
                "risk_results": len(
                    risk_rows
                ),
            },
            **assurance_result,
        }

    except Exception as error:
        failure_code = failure_codes.get(
            current_stage,
            (
                "UNEXPECTED_PROCESSING_FAILURE"
            ),
        )

        try:
            record_processing_failure(
                registry_id=registry_id,
                stage=current_stage,
                failure_code=failure_code,
                reason=str(error),
            )

        except Exception:
            fail_registry_record(
                registry_id=registry_id,
                reason=str(error),
            )

        raise


def list_registered_files(
    limit: int = 50,
) -> list[dict[str, Any]]:
    with get_registry_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM file_registry
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


initialise_registry()

def get_daily_intake_summary(
    run_date: str | None = None,
) -> dict[str, Any]:
    """
    Return file-intake metrics for one UTC processing date.
    """
    selected_date = (
        run_date
        or datetime.now(
            timezone.utc
        ).date().isoformat()
    )

    with get_registry_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS files_received,

                COALESCE(
                    SUM(
                        CASE
                            WHEN processing_status =
                                'COMPLETED'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS files_completed,

                COALESCE(
                    SUM(
                        CASE
                            WHEN processing_status =
                                'FAILED'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS files_failed,

                COALESCE(
                    SUM(
                        CASE
                            WHEN processing_status =
                                'PROCESSING'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS files_processing,

                COALESCE(
                    SUM(invoice_count),
                    0
                ) AS invoices_registered,

                COALESCE(
                    SUM(record_count),
                    0
                ) AS records_received,

                COALESCE(
                    SUM(file_size_bytes),
                    0
                ) AS total_file_bytes

            FROM file_registry
            WHERE substr(
                received_at,
                1,
                10
            ) = ?
            """,
            (selected_date,),
        ).fetchone()

    summary = dict(row)

    summary["run_date"] = (
        selected_date
    )

    summary["total_file_size_mb"] = round(
        float(
            summary[
                "total_file_bytes"
            ]
            or 0
        )
        / 1024
        / 1024,
        3,
    )

    return summary


def get_failed_files(
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_registry_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE processing_status = 'FAILED'
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid

from datetime import (
    datetime,
    timezone,
)

import assurance.repository as repository
import processing.daily_file_service as file_service

from starlette.middleware.base import (
    BaseHTTPMiddleware,
)


APPLICATION_NAME = "Billing / Finance Ops"

APPLICATION_VERSION = os.getenv(
    "APP_VERSION",
    "1.0.0",
).strip()

STARTED_AT = datetime.now(
    timezone.utc
)

PROCESS_STARTED = time.perf_counter()

logger = logging.getLogger(
    "billing_finance_ops"
)

if not logger.handlers:
    handler = logging.StreamHandler()

    handler.setFormatter(
        logging.Formatter(
            "%(message)s"
        )
    )

    logger.addHandler(
        handler
    )

logger.setLevel(
    logging.INFO
)

_metrics_lock = threading.Lock()

_request_metrics = {
    "requests_total": 0,
    "responses_2xx": 0,
    "responses_4xx": 0,
    "responses_5xx": 0,
    "request_failures": 0,
    "total_duration_ms": 0.0,
}


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def write_json_log(
    event_type: str,
    **fields,
):
    payload = {
        "timestamp": utc_timestamp(),
        "application": APPLICATION_NAME,
        "version": APPLICATION_VERSION,
        "event_type": event_type,
        **fields,
    }

    logger.info(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )
    )


def record_request(
    status_code: int,
    duration_ms: float,
    failed: bool = False,
):
    with _metrics_lock:
        _request_metrics[
            "requests_total"
        ] += 1

        _request_metrics[
            "total_duration_ms"
        ] += duration_ms

        if 200 <= status_code < 300:
            _request_metrics[
                "responses_2xx"
            ] += 1

        elif 400 <= status_code < 500:
            _request_metrics[
                "responses_4xx"
            ] += 1

        elif status_code >= 500:
            _request_metrics[
                "responses_5xx"
            ] += 1

        if failed:
            _request_metrics[
                "request_failures"
            ] += 1


def request_metric_snapshot() -> dict:
    with _metrics_lock:
        snapshot = dict(
            _request_metrics
        )

    request_count = snapshot[
        "requests_total"
    ]

    snapshot[
        "average_duration_ms"
    ] = round(
        (
            snapshot[
                "total_duration_ms"
            ]
            / request_count
        )
        if request_count
        else 0,
        3,
    )

    snapshot[
        "total_duration_ms"
    ] = round(
        snapshot[
            "total_duration_ms"
        ],
        3,
    )

    return snapshot


def check_sqlite_connection(
    connection_factory,
    database_name: str,
) -> dict:
    started = time.perf_counter()

    try:
        with connection_factory() as connection:
            query_result = connection.execute(
                "SELECT 1"
            ).fetchone()

            integrity_result = (
                connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()
            )

            foreign_keys_result = (
                connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()
            )

        query_value = (
            query_result[0]
            if query_result
            else None
        )

        integrity_value = (
            integrity_result[0]
            if integrity_result
            else ""
        )

        foreign_keys_value = (
            foreign_keys_result[0]
            if foreign_keys_result
            else 0
        )

        healthy = (
            query_value == 1
            and str(
                integrity_value
            ).lower()
            == "ok"
        )

        return {
            "database": database_name,
            "status": (
                "UP"
                if healthy
                else "DOWN"
            ),
            "query_check": (
                query_value == 1
            ),
            "integrity_check": (
                integrity_value
            ),
            "foreign_keys": bool(
                foreign_keys_value
            ),
            "duration_ms": round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                3,
            ),
        }

    except Exception as error:
        return {
            "database": database_name,
            "status": "DOWN",
            "query_check": False,
            "integrity_check": (
                "unavailable"
            ),
            "foreign_keys": False,
            "duration_ms": round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                3,
            ),
            "error": str(error),
        }


def database_health() -> dict:
    assurance = check_sqlite_connection(
        repository.get_connection,
        "assurance",
    )

    registry = check_sqlite_connection(
        file_service
        .get_registry_connection,
        "file_registry",
    )

    ready = (
        assurance["status"] == "UP"
        and registry["status"] == "UP"
    )

    return {
        "status": (
            "UP"
            if ready
            else "DOWN"
        ),
        "databases": {
            "assurance": assurance,
            "file_registry": registry,
        },
    }


def operational_counts() -> dict:
    with repository.get_connection() as connection:
        assurance_row = connection.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM processing_runs
                ) AS processing_runs,

                (
                    SELECT COUNT(*)
                    FROM invoice_assurance_results
                ) AS invoice_results,

                (
                    SELECT COUNT(*)
                    FROM invoice_assurance_results
                    WHERE
                        assurance_status =
                            'EXCEPTION'
                        AND workflow_status IN (
                            'NEW',
                            'IN REVIEW',
                            'AWAITING SUPPLIER',
                            'CORRECTION REQUIRED'
                        )
                ) AS active_exceptions,

                (
                    SELECT COUNT(*)
                    FROM supplier_queries
                ) AS supplier_queries,

                (
                    SELECT COUNT(*)
                    FROM supplier_queries
                    WHERE query_status NOT IN (
                        'RESPONSE ACCEPTED',
                        'RESOLVED',
                        'CLOSED'
                    )
                ) AS open_supplier_queries
            """
        ).fetchone()

    with (
        file_service
        .get_registry_connection()
    ) as connection:
        registry_row = connection.execute(
            """
            SELECT
                COUNT(*) AS registered_files,

                SUM(
                    CASE
                        WHEN processing_status =
                            'COMPLETED'
                        THEN 1
                        ELSE 0
                    END
                ) AS completed_files,

                SUM(
                    CASE
                        WHEN processing_status =
                            'FAILED'
                        THEN 1
                        ELSE 0
                    END
                ) AS failed_files,

                SUM(
                    CASE
                        WHEN processing_status =
                            'PROCESSING'
                        THEN 1
                        ELSE 0
                    END
                ) AS processing_files,

                SUM(
                    CASE
                        WHEN processing_status =
                            'RECOVERY REQUIRED'
                        THEN 1
                        ELSE 0
                    END
                ) AS recovery_required
            FROM file_registry
            """
        ).fetchone()

    assurance_counts = dict(
        assurance_row
    )

    registry_counts = dict(
        registry_row
    )

    return {
        **{
            key: int(value or 0)
            for key, value
            in assurance_counts.items()
        },
        **{
            key: int(value or 0)
            for key, value
            in registry_counts.items()
        },
    }


def monitoring_snapshot() -> dict:
    database = database_health()

    snapshot = {
        "application": APPLICATION_NAME,
        "version": APPLICATION_VERSION,
        "status": database["status"],
        "started_at": (
            STARTED_AT.isoformat()
        ),
        "uptime_seconds": round(
            (
                time.perf_counter()
                - PROCESS_STARTED
            ),
            3,
        ),
        "database": database,
        "requests": (
            request_metric_snapshot()
        ),
    }

    try:
        snapshot[
            "operations"
        ] = operational_counts()

    except Exception as error:
        snapshot["status"] = "DEGRADED"

        snapshot["operations"] = {
            "available": False,
            "error": str(error),
        }

    return snapshot


class CorrelationLoggingMiddleware(
    BaseHTTPMiddleware
):
    async def dispatch(
        self,
        request,
        call_next,
    ):
        supplied_id = request.headers.get(
            "X-Correlation-ID",
            "",
        ).strip()

        correlation_id = (
            supplied_id[:128]
            if supplied_id
            else str(
                uuid.uuid4()
            )
        )

        request.state.correlation_id = (
            correlation_id
        )

        started = time.perf_counter()
        status_code = 500
        failed = False
        response = None

        try:
            response = await call_next(
                request
            )

            status_code = (
                response.status_code
            )

            response.headers[
                "X-Correlation-ID"
            ] = correlation_id

            return response

        except Exception:
            failed = True

            write_json_log(
                "REQUEST_FAILED",
                correlation_id=(
                    correlation_id
                ),
                method=request.method,
                path=request.url.path,
            )

            raise

        finally:
            duration_ms = (
                time.perf_counter()
                - started
            ) * 1000

            record_request(
                status_code=status_code,
                duration_ms=duration_ms,
                failed=failed,
            )

            write_json_log(
                "REQUEST_COMPLETED",
                correlation_id=(
                    correlation_id
                ),
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=round(
                    duration_ms,
                    3,
                ),
            )
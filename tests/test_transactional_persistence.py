import sqlite3

import pytest

import assurance.repository as repository

from assurance.service import run_synthetic_demo


class FailureInjectingConnection:
    """
    Proxy a real SQLite connection and raise an error at a
    selected persistence point.

    The underlying connection context manager performs the
    rollback when the injected exception leaves the block.
    """

    def __init__(
        self,
        connection,
        failure_target,
        invoice_failure_number=None,
    ):
        self.connection = connection

        self.failure_target = (
            failure_target
        )

        self.invoice_failure_number = (
            invoice_failure_number
        )

        self.invoice_insert_count = 0

    def __enter__(self):
        self.connection.__enter__()

        return self

    def __exit__(
        self,
        exception_type,
        exception_value,
        traceback,
    ):
        return self.connection.__exit__(
            exception_type,
            exception_value,
            traceback,
        )

    def execute(
        self,
        sql,
        parameters=(),
    ):
        normalized_sql = " ".join(
            str(sql).split()
        ).upper()

        if (
            self.failure_target
            == "RUN INSERT"
            and (
                "INSERT OR REPLACE INTO "
                "PROCESSING_RUNS"
            )
            in normalized_sql
        ):
            raise RuntimeError(
                "Injected run insert failure"
            )

        if (
            "INSERT OR REPLACE INTO "
            "INVOICE_ASSURANCE_RESULTS"
        ) in normalized_sql:
            self.invoice_insert_count += 1

            if (
                self.failure_target
                == "INVOICE INSERT"
                and self.invoice_insert_count
                == self.invoice_failure_number
            ):
                raise RuntimeError(
                    "Injected invoice insert "
                    f"failure at invoice "
                    f"{self.invoice_insert_count}"
                )

        if (
            self.failure_target
            == "AUDIT INSERT"
            and (
                "INSERT INTO "
                "ASSURANCE_AUDIT_HISTORY"
            )
            in normalized_sql
        ):
            raise RuntimeError(
                "Injected audit insert failure"
            )

        return self.connection.execute(
            sql,
            parameters,
        )

    def __getattr__(
        self,
        name,
    ):
        return getattr(
            self.connection,
            name,
        )


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "transactional_persistence.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()

    return database_path


def open_raw_connection(
    database_path,
):
    connection = sqlite3.connect(
        database_path
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def database_counts(
    database_path,
):
    with open_raw_connection(
        database_path
    ) as connection:
        return {
            "runs": connection.execute(
                """
                SELECT COUNT(*)
                FROM processing_runs
                """
            ).fetchone()[0],

            "invoices": connection.execute(
                """
                SELECT COUNT(*)
                FROM invoice_assurance_results
                """
            ).fetchone()[0],

            "audits": connection.execute(
                """
                SELECT COUNT(*)
                FROM assurance_audit_history
                """
            ).fetchone()[0],

            "queries": connection.execute(
                """
                SELECT COUNT(*)
                FROM supplier_queries
                """
            ).fetchone()[0],
        }


def install_failure(
    monkeypatch,
    failure_target,
    invoice_failure_number=None,
):
    original_get_connection = (
        repository.get_connection
    )

    def failing_get_connection():
        return FailureInjectingConnection(
            connection=(
                original_get_connection()
            ),
            failure_target=failure_target,
            invoice_failure_number=(
                invoice_failure_number
            ),
        )

    monkeypatch.setattr(
        repository,
        "get_connection",
        failing_get_connection,
    )


def assert_empty_transaction(
    database_path,
):
    assert database_counts(
        database_path
    ) == {
        "runs": 0,
        "invoices": 0,
        "audits": 0,
        "queries": 0,
    }


def test_run_insert_failure_rolls_back(
    tmp_path,
    monkeypatch,
):
    database_path = configure_database(
        tmp_path,
        monkeypatch,
    )

    install_failure(
        monkeypatch,
        failure_target="RUN INSERT",
    )

    with pytest.raises(
        RuntimeError,
        match="Injected run insert failure",
    ):
        run_synthetic_demo()

    assert_empty_transaction(
        database_path
    )


@pytest.mark.parametrize(
    "invoice_number",
    [
        1,
        2,
        3,
    ],
)
def test_invoice_insert_failure_rolls_back(
    tmp_path,
    monkeypatch,
    invoice_number,
):
    database_path = configure_database(
        tmp_path,
        monkeypatch,
    )

    install_failure(
        monkeypatch,
        failure_target="INVOICE INSERT",
        invoice_failure_number=(
            invoice_number
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Injected invoice insert failure",
    ):
        run_synthetic_demo()

    assert_empty_transaction(
        database_path
    )


def test_audit_insert_failure_rolls_back(
    tmp_path,
    monkeypatch,
):
    database_path = configure_database(
        tmp_path,
        monkeypatch,
    )

    install_failure(
        monkeypatch,
        failure_target="AUDIT INSERT",
    )

    with pytest.raises(
        RuntimeError,
        match="Injected audit insert failure",
    ):
        run_synthetic_demo()

    assert_empty_transaction(
        database_path
    )


def test_successful_persistence_is_complete(
    tmp_path,
    monkeypatch,
):
    database_path = configure_database(
        tmp_path,
        monkeypatch,
    )

    result = run_synthetic_demo()

    counts = database_counts(
        database_path
    )

    assert counts == {
        "runs": 1,
        "invoices": 3,
        "audits": 1,
        "queries": 0,
    }

    with open_raw_connection(
        database_path
    ) as connection:
        run_row = connection.execute(
            """
            SELECT
                run_id,
                status,
                total_invoices
            FROM processing_runs
            """
        ).fetchone()

        persisted_invoice_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM invoice_assurance_results
                WHERE run_id = ?
                """,
                (
                    run_row["run_id"],
                ),
            ).fetchone()[0]
        )

    assert (
        run_row["status"]
        == "COMPLETED"
    )

    assert (
        run_row["total_invoices"]
        == 3
    )

    assert (
        persisted_invoice_count
        == run_row["total_invoices"]
    )

    assert (
        result["summary"][
            "total_invoices"
        ]
        == 3
    )
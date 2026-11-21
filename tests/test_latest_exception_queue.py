import assurance.repository as repository

from assurance.service import (
    run_synthetic_demo,
)


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "latest_exception_queue.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()

    return database_path


def test_latest_active_exception_per_invoice(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    first_run = run_synthetic_demo()
    second_run = run_synthetic_demo()

    rows = (
        repository
        .list_latest_active_exceptions()
    )

    invoice_numbers = [
        row["invoice_number"]
        for row in rows
    ]

    assert (
        invoice_numbers.count(
            "SYNTH-INV-003"
        )
        == 1
    )

    latest_reconciliation = next(
        row
        for row in rows
        if row["invoice_number"]
        == "SYNTH-INV-003"
    )

    assert (
        latest_reconciliation["run_id"]
        == second_run[
            "summary"
        ][
            "run_id"
        ]
    )

    assert len(rows) == 2


def test_historical_results_are_preserved(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    run_synthetic_demo()
    run_synthetic_demo()

    all_exceptions = (
        repository
        .list_invoice_results(
            exceptions_only=True
        )
    )

    latest_exceptions = (
        repository
        .list_latest_active_exceptions()
    )

    assert len(all_exceptions) == 4

    assert len(latest_exceptions) == 2
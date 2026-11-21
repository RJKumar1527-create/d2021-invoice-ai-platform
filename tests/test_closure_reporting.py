from datetime import (
    datetime,
    timedelta,
    timezone,
)

import assurance.repository as repository
import assurance.supplier_query_service as query_service

from assurance.service import (
    run_synthetic_demo,
)


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "closure_reporting_test.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()

    return database_path


def create_demo_query(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    result = run_synthetic_demo()

    invoice = next(
        item
        for item
        in result["exception_queue"]
        if item[
            "recommended_decision"
        ]
        == "QUERY SUPPLIER"
    )

    due_date = (
        datetime.now(
            timezone.utc
        ).date()
        + timedelta(days=5)
    ).isoformat()

    query = query_service.create_query(
        run_id=invoice["run_id"],
        invoice_number=invoice[
            "invoice_number"
        ],
        owner="Supplier Query Team",
        due_date=due_date,
    )

    return invoice, query


def accept_supplier_response(
    query,
    recovered_value=3500,
):
    query_service.update_query(
        query_id=query["query_id"],
        query_status=(
            "RESPONSE RECEIVED"
        ),
        supplier_response=(
            "Supplier provided supporting "
            "billing evidence."
        ),
        final_resolution="",
        recovered_value=0,
    )

    return query_service.update_query(
        query_id=query["query_id"],
        query_status=(
            "RESPONSE ACCEPTED"
        ),
        supplier_response=(
            "Supplier confirmed that the "
            "source charge was incorrect."
        ),
        final_resolution=(
            "Corrected invoice requested."
        ),
        recovered_value=(
            recovered_value
        ),
    )


def test_resolved_invoice_leaves_active_queue(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_demo_query(
        tmp_path,
        monkeypatch,
    )

    accept_supplier_response(
        query
    )

    active = (
        repository.list_active_exceptions()
    )

    active_numbers = {
        item["invoice_number"]
        for item in active
    }

    assert (
        invoice["invoice_number"]
        not in active_numbers
    )

    assert len(active) == 1


def test_resolved_invoice_enters_history(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_demo_query(
        tmp_path,
        monkeypatch,
    )

    accept_supplier_response(
        query,
        recovered_value=2500,
    )

    resolved = (
        repository
        .list_resolved_exceptions()
    )

    assert len(resolved) == 1

    assert (
        resolved[0]["invoice_number"]
        == invoice["invoice_number"]
    )

    assert (
        resolved[0]["workflow_status"]
        == "RESOLVED"
    )


def test_financial_control_summary(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_demo_query(
        tmp_path,
        monkeypatch,
    )

    accept_supplier_response(
        query,
        recovered_value=3500,
    )

    summary = (
        repository
        .get_financial_control_summary()
    )

    assert (
        summary["invoices_assured"]
        == 3
    )

    assert (
        summary["cleared_invoices"]
        == 1
    )

    assert (
        summary["active_exceptions"]
        == 1
    )

    assert (
        summary["resolved_exceptions"]
        == 1
    )

    assert (
        summary["open_exposure"]
        == 3500
    )

    assert (
        summary["recovered_value"]
        == 3500
    )

    assert (
        summary["recovery_rate"]
        == 50
    )


def test_current_ageing_band(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    run_synthetic_demo()

    ageing = (
        repository
        .get_exception_ageing_summary()
    )

    assert (
        ageing[
            "total_active_exceptions"
        ]
        == 2
    )

    assert (
        ageing["ageing_bands"][
            "0-2 days"
        ]
        == 2
    )


def test_latest_supplier_query_is_visible(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_demo_query(
        tmp_path,
        monkeypatch,
    )

    found = (
        repository
        .get_invoice_supplier_query(
            run_id=invoice["run_id"],
            invoice_number=invoice[
                "invoice_number"
            ],
        )
    )

    assert found is not None

    assert (
        found["query_reference"]
        == query["query_reference"]
    )

    assert (
        found["query_status"]
        == "OPEN"
    )
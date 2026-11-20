from datetime import (
    datetime,
    timedelta,
    timezone,
)

import assurance.repository as repository
import assurance.supplier_query_service as service

from assurance.service import (
    run_synthetic_demo,
)


def use_temporary_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "supplier_query_test.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()

    return database_path


def create_test_query(
    tmp_path,
    monkeypatch,
):
    use_temporary_database(
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

    query = service.create_query(
        run_id=invoice["run_id"],
        invoice_number=invoice[
            "invoice_number"
        ],
        owner="Supplier Query Team",
        due_date=due_date,
    )

    return query


def test_supplier_query_is_created(
    tmp_path,
    monkeypatch,
):
    query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    assert (
        query["query_status"]
        == "OPEN"
    )

    assert query[
        "query_reference"
    ].startswith("SQ-")


def test_duplicate_active_query_is_blocked(
    tmp_path,
    monkeypatch,
):
    query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    try:
        service.create_query(
            run_id=query["run_id"],
            invoice_number=query[
                "invoice_number"
            ],
            owner="Supplier Query Team",
            due_date=query["due_date"],
        )

        assert False

    except ValueError as error:
        assert (
            "already exists"
            in str(error)
        )


def test_recovered_value_cannot_exceed_dispute(
    tmp_path,
    monkeypatch,
):
    query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    try:
        service.update_query(
            query_id=query["query_id"],
            query_status=(
                "RESPONSE ACCEPTED"
            ),
            supplier_response=(
                "Synthetic supplier response"
            ),
            final_resolution=(
                "Synthetic accepted resolution"
            ),
            recovered_value=(
                query[
                    "disputed_amount"
                ]
                + 1
            ),
        )

        assert False

    except ValueError as error:
        assert (
            "cannot exceed"
            in str(error)
        )


def test_accepted_response_resolves_invoice(
    tmp_path,
    monkeypatch,
):
    query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    updated = service.update_query(
        query_id=query["query_id"],
        query_status=(
            "RESPONSE ACCEPTED"
        ),
        supplier_response=(
            "Supplier confirmed the charge "
            "calculation was incorrect."
        ),
        final_resolution=(
            "Corrected invoice requested."
        ),
        recovered_value=3500,
    )

    assert (
        updated["query_status"]
        == "RESPONSE ACCEPTED"
    )

    invoice = (
        repository.get_invoice_result(
            updated["run_id"],
            updated[
                "invoice_number"
            ],
        )
    )

    assert (
        invoice["workflow_status"]
        == "RESOLVED"
    )


def test_query_summary(
    tmp_path,
    monkeypatch,
):
    create_test_query(
        tmp_path,
        monkeypatch,
    )

    summary = (
        service.get_query_summary()
    )

    assert (
        summary["total_queries"]
        == 1
    )

    assert (
        summary["open_queries"]
        == 1
    )
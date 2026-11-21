from datetime import (
    datetime,
    timedelta,
    timezone,
)

import assurance.repository as repository
import assurance.supplier_query_service as service

from assurance.service import run_synthetic_demo


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "query_state_integrity.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()


def create_test_query(
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
        for item in result[
            "exception_queue"
        ]
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

    return invoice, query


def test_query_creation_synchronizes_invoice(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    stored_invoice = (
        repository.get_invoice_result(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    assert (
        query["query_status"]
        == "OPEN"
    )

    assert (
        stored_invoice["workflow_status"]
        == "AWAITING SUPPLIER"
    )


def test_invalid_direct_resolution_is_blocked(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    try:
        service.update_query(
            query_id=query["query_id"],
            query_status="RESOLVED",
            supplier_response=(
                "Supplier response"
            ),
            final_resolution=(
                "Resolution"
            ),
            recovered_value=0,
        )

        assert False, (
            "OPEN to RESOLVED should "
            "have been blocked."
        )

    except ValueError as error:
        assert (
            "Invalid supplier-query transition"
            in str(error)
        )


def test_valid_response_acceptance_resolves_invoice(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    response_received = (
        service.update_query(
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
    )

    assert (
        response_received[
            "query_status"
        ]
        == "RESPONSE RECEIVED"
    )

    response_accepted = (
        service.update_query(
            query_id=query["query_id"],
            query_status=(
                "RESPONSE ACCEPTED"
            ),
            supplier_response=(
                "Supplier confirmed that the "
                "charge was incorrect."
            ),
            final_resolution=(
                "Corrected invoice requested."
            ),
            recovered_value=1000,
        )
    )

    assert (
        response_accepted[
            "query_status"
        ]
        == "RESPONSE ACCEPTED"
    )

    stored_invoice = (
        repository.get_invoice_result(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    assert (
        stored_invoice["workflow_status"]
        == "RESOLVED"
    )

    assert (
        stored_invoice[
            "confirmed_root_cause"
        ]
        == "Corrected invoice requested."
    )


def test_closed_query_cannot_be_reopened(
    tmp_path,
    monkeypatch,
):
    invoice, query = create_test_query(
        tmp_path,
        monkeypatch,
    )

    response_received = service.update_query(
        query_id=query["query_id"],
        query_status=(
            "RESPONSE RECEIVED"
        ),
        supplier_response=(
            "Supplier provided evidence."
        ),
        final_resolution="",
        recovered_value=0,
    )

    accepted = service.update_query(
        query_id=response_received[
            "query_id"
        ],
        query_status=(
            "RESPONSE ACCEPTED"
        ),
        supplier_response=(
            "Supplier confirmed the correction."
        ),
        final_resolution=(
            "Corrected invoice requested."
        ),
        recovered_value=500,
    )

    closed = service.update_query(
        query_id=accepted["query_id"],
        query_status="CLOSED",
        supplier_response=(
            "Supplier confirmed the correction."
        ),
        final_resolution=(
            "Corrected invoice received "
            "and verified."
        ),
        recovered_value=500,
    )

    assert (
        closed["query_status"]
        == "CLOSED"
    )

    try:
        service.update_query(
            query_id=closed["query_id"],
            query_status="OPEN",
            supplier_response=(
                "Supplier confirmed the correction."
            ),
            final_resolution=(
                "Attempt to reopen."
            ),
            recovered_value=500,
        )

        assert False, (
            "A closed supplier query "
            "must not be reopened."
        )

    except ValueError as error:
        assert (
            "Invalid supplier-query transition"
            in str(error)
        )
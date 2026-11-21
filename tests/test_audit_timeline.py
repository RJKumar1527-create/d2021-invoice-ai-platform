import assurance.repository as repository

from assurance.service import run_synthetic_demo


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "audit_timeline.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()


def test_completed_run_event_is_returned(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    result = run_synthetic_demo()

    invoice = result[
        "exception_queue"
    ][0]

    events = (
        repository
        .list_invoice_audit_history(
            run_id=invoice["run_id"],
            invoice_number=invoice[
                "invoice_number"
            ],
        )
    )

    assert len(events) == 1

    assert (
        events[0]["event_type"]
        == "PROCESSING_RUN_COMPLETED"
    )

    assert events[0]["scope"] == "RUN"

    assert (
        events[0]["payload"][
            "total_invoices"
        ]
        == 3
    )


def test_resolution_event_is_returned(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    result = run_synthetic_demo()

    invoice = result[
        "exception_queue"
    ][0]

    repository.update_invoice_resolution(
        run_id=invoice["run_id"],
        invoice_number=invoice[
            "invoice_number"
        ],
        workflow_status="IN REVIEW",
        owner="Finance Analyst",
        confirmed_root_cause=(
            "Investigation in progress"
        ),
        resolution_notes=(
            "Initial review recorded."
        ),
    )

    events = (
        repository
        .list_invoice_audit_history(
            run_id=invoice["run_id"],
            invoice_number=invoice[
                "invoice_number"
            ],
        )
    )

    event_types = [
        item["event_type"]
        for item in events
    ]

    assert event_types == [
        "PROCESSING_RUN_COMPLETED",
        "INVOICE_RESOLUTION_UPDATED",
    ]

    resolution = events[-1]

    assert resolution["scope"] == "INVOICE"

    assert (
        resolution["payload"]["owner"]
        == "Finance Analyst"
    )

    assert (
        resolution["payload"][
            "workflow_status"
        ]
        == "IN REVIEW"
    )


def test_other_invoice_events_are_excluded(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    result = run_synthetic_demo()

    first = result[
        "exception_queue"
    ][0]

    second = result[
        "exception_queue"
    ][1]

    repository.update_invoice_resolution(
        run_id=first["run_id"],
        invoice_number=first[
            "invoice_number"
        ],
        workflow_status="IN REVIEW",
        owner="Analyst One",
        confirmed_root_cause="",
        resolution_notes=(
            "First invoice reviewed."
        ),
    )

    repository.update_invoice_resolution(
        run_id=second["run_id"],
        invoice_number=second[
            "invoice_number"
        ],
        workflow_status="IN REVIEW",
        owner="Analyst Two",
        confirmed_root_cause="",
        resolution_notes=(
            "Second invoice reviewed."
        ),
    )

    events = (
        repository
        .list_invoice_audit_history(
            run_id=first["run_id"],
            invoice_number=first[
                "invoice_number"
            ],
        )
    )

    invoice_events = [
        item
        for item in events
        if item["scope"]
        == "INVOICE"
    ]

    assert len(invoice_events) == 1

    assert (
        invoice_events[0][
            "invoice_number"
        ]
        == first["invoice_number"]
    )
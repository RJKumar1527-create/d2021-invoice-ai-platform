from pathlib import Path

import assurance.repository as repository
import processing.daily_file_service as service


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_FILE = (
    PROJECT_ROOT
    / "sample_data"
    / "synthetic_d2021_demo.txt"
)


def configure_registry(
    tmp_path,
    monkeypatch,
):
    registry_path = (
        tmp_path
        / "failed_file_retry.db"
    )

    assurance_path = (
        tmp_path
        / "failed_file_retry_assurance.db"
    )

    monkeypatch.setattr(
        service,
        "REGISTRY_PATH",
        registry_path,
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        assurance_path,
    )

    service.initialise_registry()
    repository.initialise_repository()

    return registry_path


def insert_failed_record(
    file_name,
    file_bytes,
):
    checksum = service.calculate_checksum(
        file_bytes
    )

    registry_id = service.register_file(
        file_name=file_name,
        checksum=checksum,
        file_size_bytes=len(
            file_bytes
        ),
        encoding="utf-8",
        record_count=1,
    )

    service.fail_registry_record(
        registry_id=registry_id,
        reason=(
            "Synthetic processing failure"
        ),
    )

    return registry_id


def test_failed_file_can_be_retried(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    file_bytes = SAMPLE_FILE.read_bytes()

    insert_failed_record(
        SAMPLE_FILE.name,
        file_bytes,
    )

    before_retry = (
        service.list_registered_files()
    )

    assert len(before_retry) == 1

    assert (
        before_retry[0][
            "processing_status"
        ]
        == "FAILED"
    )

    result = service.process_runtime_file(
        SAMPLE_FILE.name,
        file_bytes,
    )

    assert (
        result["summary"][
            "total_invoices"
        ]
        == 12
    )

    history = (
        service.list_registered_files()
    )

    assert len(history) == 1

    assert (
        history[0][
            "processing_status"
        ]
        == "COMPLETED"
    )

    assert (
        history[0]["invoice_count"]
        == 12
    )

    assert (
        history[0][
            "processing_run_id"
        ]
    )


def test_completed_file_remains_blocked(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    file_bytes = SAMPLE_FILE.read_bytes()

    service.process_runtime_file(
        SAMPLE_FILE.name,
        file_bytes,
    )

    try:
        service.process_runtime_file(
            SAMPLE_FILE.name,
            file_bytes,
        )

        assert False, (
            "Completed duplicate should "
            "have been rejected."
        )

    except (
        service
        .DailyFileProcessingError
    ) as error:
        message = str(error)

        assert (
            "already been registered"
            in message
        )

        assert "COMPLETED" in message


def test_retry_replaces_failed_registry_record(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    file_bytes = SAMPLE_FILE.read_bytes()

    failed_registry_id = (
        insert_failed_record(
            SAMPLE_FILE.name,
            file_bytes,
        )
    )

    service.process_runtime_file(
        SAMPLE_FILE.name,
        file_bytes,
    )

    history = (
        service.list_registered_files()
    )

    assert len(history) == 1

    assert (
        history[0]["registry_id"]
        != failed_registry_id
    )

    assert (
        history[0][
            "processing_status"
        ]
        == "COMPLETED"
    )
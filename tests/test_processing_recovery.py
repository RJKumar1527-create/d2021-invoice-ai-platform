from datetime import (
    datetime,
    timedelta,
    timezone,
)

import processing.daily_file_service as file_service
import processing.recovery_service as recovery


def configure_registry(
    tmp_path,
    monkeypatch,
):
    registry_path = (
        tmp_path
        / "processing_recovery.db"
    )

    monkeypatch.setattr(
        file_service,
        "REGISTRY_PATH",
        registry_path,
    )

    recovery.initialise_recovery_schema()

    return registry_path


def create_processing_record(
    checksum="synthetic-checksum",
):
    return file_service.register_file(
        file_name="H12345678.uff",
        checksum=checksum,
        file_size_bytes=100,
        encoding="utf-8",
        record_count=10,
    )


def get_record(
    registry_id,
):
    with (
        file_service
        .get_registry_connection()
    ) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM file_registry
            WHERE registry_id = ?
            """,
            (registry_id,),
        ).fetchone()

    return dict(row)


def test_recovery_schema_is_added(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    with (
        file_service
        .get_registry_connection()
    ) as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(file_registry)"
            ).fetchall()
        }

    assert "processing_stage" in columns
    assert "failure_code" in columns
    assert "last_activity_at" in columns
    assert "retry_count" in columns
    assert "recovery_required" in columns
    assert "recovered_at" in columns


def test_processing_stage_is_updated(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    recovery.update_processing_stage(
        registry_id,
        "PARSING",
    )

    record = get_record(
        registry_id
    )

    assert (
        record["processing_status"]
        == "PROCESSING"
    )

    assert (
        record["processing_stage"]
        == "PARSING"
    )

    assert record["last_activity_at"]


def test_stale_record_is_marked_for_recovery(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    old_timestamp = (
        datetime.now(
            timezone.utc
        )
        - timedelta(minutes=60)
    ).isoformat()

    with (
        file_service
        .get_registry_connection()
    ) as connection:
        connection.execute(
            """
            UPDATE file_registry
            SET last_activity_at = ?
            WHERE registry_id = ?
            """,
            (
                old_timestamp,
                registry_id,
            ),
        )

    count = (
        recovery
        .mark_stale_processing_records(
            stale_minutes=30
        )
    )

    assert count == 1

    record = get_record(
        registry_id
    )

    assert (
        record["processing_status"]
        == "RECOVERY REQUIRED"
    )

    assert (
        record["processing_stage"]
        == "RECOVERY REQUIRED"
    )

    assert (
        record["failure_code"]
        == "STALE_PROCESSING"
    )

    assert (
        record["recovery_required"]
        == 1
    )


def test_recent_processing_is_not_stale(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    recovery.update_processing_stage(
        registry_id,
        "PARSING",
    )

    count = (
        recovery
        .mark_stale_processing_records(
            stale_minutes=30
        )
    )

    assert count == 0

    record = get_record(
        registry_id
    )

    assert (
        record["processing_status"]
        == "PROCESSING"
    )

    assert (
        record["processing_stage"]
        == "PARSING"
    )


def test_processing_failure_is_recorded(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    recovery.record_processing_failure(
        registry_id=registry_id,
        stage="PARSING",
        failure_code=(
            "PARSING_FAILED"
        ),
        reason=(
            "Synthetic parser failure"
        ),
    )

    record = get_record(
        registry_id
    )

    assert (
        record["processing_status"]
        == "FAILED"
    )

    assert (
        record["processing_stage"]
        == "PARSING"
    )

    assert (
        record["failure_code"]
        == "PARSING_FAILED"
    )

    assert (
        record["failure_reason"]
        == "Synthetic parser failure"
    )


def test_retry_authorization(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    recovery.record_processing_failure(
        registry_id=registry_id,
        stage="PARSING",
        failure_code=(
            "PARSING_FAILED"
        ),
        reason=(
            "Synthetic parser failure"
        ),
    )

    updated = recovery.authorize_retry(
        registry_id
    )

    assert (
        updated["processing_status"]
        == "FAILED"
    )

    assert (
        updated["processing_stage"]
        == "FAILED"
    )

    assert updated["retry_count"] == 1
    assert updated["recovery_required"] == 0
    assert updated["failure_code"] == ""
    assert updated["recovered_at"]

    assert (
        updated["failure_reason"]
        == (
            "Retry authorized. Select "
            "the source file again."
        )
    )


def test_completed_record_cannot_be_authorized(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    file_service.complete_registry_record(
        registry_id=registry_id,
        invoice_count=1,
        processing_run_id=(
            "RUN-TEST-001"
        ),
    )

    try:
        recovery.authorize_retry(
            registry_id
        )

        assert False, (
            "A completed record must not "
            "be authorized for retry."
        )

    except ValueError as error:
        assert (
            "Only failed or stale"
            in str(error)
        )


def test_invalid_stage_is_rejected(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    try:
        recovery.update_processing_stage(
            registry_id,
            "UNKNOWN STAGE",
        )

        assert False

    except ValueError as error:
        assert (
            "Invalid processing stage"
            in str(error)
        )


def test_invalid_failure_code_is_rejected(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    registry_id = create_processing_record()

    try:
        recovery.record_processing_failure(
            registry_id=registry_id,
            stage="PARSING",
            failure_code=(
                "UNKNOWN_FAILURE"
            ),
            reason="Synthetic failure",
        )

        assert False

    except ValueError as error:
        assert (
            "Invalid failure code"
            in str(error)
        )
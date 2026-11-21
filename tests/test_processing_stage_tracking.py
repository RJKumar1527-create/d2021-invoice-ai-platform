from pathlib import Path

import processing.daily_file_service as service
import processing.recovery_service as recovery


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
        / "stage_tracking.db"
    )

    monkeypatch.setattr(
        service,
        "REGISTRY_PATH",
        registry_path,
    )

    recovery.initialise_recovery_schema()

    return registry_path


def get_registry_record():
    records = (
        service.list_registered_files()
    )

    assert len(records) == 1

    return records[0]


def test_successful_processing_reaches_completed(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    result = service.process_runtime_file(
        SAMPLE_FILE.name,
        SAMPLE_FILE.read_bytes(),
    )

    record = get_registry_record()

    assert (
        result["summary"]["total_invoices"]
        == 12
    )

    assert (
        record["processing_status"]
        == "COMPLETED"
    )

    assert (
        record["processing_stage"]
        == "COMPLETED"
    )

    assert record["failure_code"] == ""
    assert record["recovery_required"] == 0
    assert record["last_activity_at"]


def test_parser_failure_records_stage(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    modules = (
        service.load_processing_modules()
    )

    def fail_parser(lines):
        raise RuntimeError(
            "Synthetic parser failure"
        )

    modules["parser"].parse_d2021 = (
        fail_parser
    )

    monkeypatch.setattr(
        service,
        "load_processing_modules",
        lambda: modules,
    )

    try:
        service.process_runtime_file(
            SAMPLE_FILE.name,
            SAMPLE_FILE.read_bytes(),
        )

        assert False

    except RuntimeError as error:
        assert (
            "Synthetic parser failure"
            in str(error)
        )

    record = get_registry_record()

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


def test_reconciliation_failure_records_stage(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    modules = (
        service.load_processing_modules()
    )

    def fail_reconciliation(
        parsed_data,
    ):
        raise RuntimeError(
            "Synthetic reconciliation failure"
        )

    modules[
        "reconciliation"
    ].reconcile_invoices = (
        fail_reconciliation
    )

    monkeypatch.setattr(
        service,
        "load_processing_modules",
        lambda: modules,
    )

    try:
        service.process_runtime_file(
            SAMPLE_FILE.name,
            SAMPLE_FILE.read_bytes(),
        )

        assert False

    except RuntimeError as error:
        assert (
            "Synthetic reconciliation failure"
            in str(error)
        )

    record = get_registry_record()

    assert (
        record["processing_status"]
        == "FAILED"
    )

    assert (
        record["processing_stage"]
        == "RECONCILIATION"
    )

    assert (
        record["failure_code"]
        == "RECONCILIATION_FAILED"
    )


def test_risk_failure_records_stage(
    tmp_path,
    monkeypatch,
):
    configure_registry(
        tmp_path,
        monkeypatch,
    )

    modules = (
        service.load_processing_modules()
    )

    def fail_risk(*args, **kwargs):
        raise RuntimeError(
            "Synthetic risk failure"
        )

    modules[
        "risk"
    ].create_risk_results = fail_risk

    monkeypatch.setattr(
        service,
        "load_processing_modules",
        lambda: modules,
    )

    try:
        service.process_runtime_file(
            SAMPLE_FILE.name,
            SAMPLE_FILE.read_bytes(),
        )

        assert False

    except RuntimeError as error:
        assert (
            "Synthetic risk failure"
            in str(error)
        )

    record = get_registry_record()

    assert (
        record["processing_status"]
        == "FAILED"
    )

    assert (
        record["processing_stage"]
        == "RISK SCORING"
    )

    assert (
        record["failure_code"]
        == "RISK_SCORING_FAILED"
    )
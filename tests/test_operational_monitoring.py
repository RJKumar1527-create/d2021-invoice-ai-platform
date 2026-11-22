import assurance.repository as repository
import processing.daily_file_service as file_service

from monitoring import operations


def configure_databases(
    tmp_path,
    monkeypatch,
):
    assurance_path = (
        tmp_path
        / "monitoring_assurance.db"
    )

    registry_path = (
        tmp_path
        / "monitoring_registry.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        assurance_path,
    )

    monkeypatch.setattr(
        file_service,
        "REGISTRY_PATH",
        registry_path,
    )

    repository.initialise_repository()
    file_service.initialise_registry()


def test_database_health_is_up(
    tmp_path,
    monkeypatch,
):
    configure_databases(
        tmp_path,
        monkeypatch,
    )

    result = (
        operations.database_health()
    )

    assert result["status"] == "UP"

    assert (
        result["databases"][
            "assurance"
        ]["integrity_check"]
        == "ok"
    )

    assert (
        result["databases"][
            "file_registry"
        ]["integrity_check"]
        == "ok"
    )


def test_operational_counts_are_zero(
    tmp_path,
    monkeypatch,
):
    configure_databases(
        tmp_path,
        monkeypatch,
    )

    result = (
        operations.operational_counts()
    )

    assert result[
        "processing_runs"
    ] == 0

    assert result[
        "invoice_results"
    ] == 0

    assert result[
        "registered_files"
    ] == 0

    assert result[
        "failed_files"
    ] == 0


def test_request_metrics_are_recorded():
    before = (
        operations
        .request_metric_snapshot()
    )

    operations.record_request(
        status_code=200,
        duration_ms=25.5,
    )

    operations.record_request(
        status_code=503,
        duration_ms=10.0,
        failed=True,
    )

    after = (
        operations
        .request_metric_snapshot()
    )

    assert (
        after["requests_total"]
        == before["requests_total"]
        + 2
    )

    assert (
        after["responses_2xx"]
        == before["responses_2xx"]
        + 1
    )

    assert (
        after["responses_5xx"]
        == before["responses_5xx"]
        + 1
    )

    assert (
        after["request_failures"]
        == before["request_failures"]
        + 1
    )


def test_monitoring_snapshot(
    tmp_path,
    monkeypatch,
):
    configure_databases(
        tmp_path,
        monkeypatch,
    )

    result = (
        operations.monitoring_snapshot()
    )

    assert result["status"] == "UP"
    assert result["uptime_seconds"] >= 0
    assert "requests" in result
    assert "operations" in result
    assert "database" in result
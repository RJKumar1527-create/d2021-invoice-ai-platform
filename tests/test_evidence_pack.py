import csv
import hashlib
import io
import json
from zipfile import ZipFile

import assurance.repository as repository

from assurance.evidence_pack_service import (
    build_invoice_evidence_pack,
    sanitize_filename_component,
)
from assurance.service import (
    run_synthetic_demo,
)


EXPECTED_FILES = {
    "manifest.json",
    "invoice.csv",
    "validation_findings.csv",
    "exceptions.csv",
    "supplier_queries.csv",
    "audit_timeline.csv",
    "evidence_snapshot.json",
}


def configure_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "evidence_pack.db"
    )

    monkeypatch.setattr(
        repository,
        "DATABASE_PATH",
        database_path,
    )

    repository.initialise_repository()


def test_evidence_pack_contains_expected_files(
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

    archive_bytes, filename = (
        build_invoice_evidence_pack(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    assert archive_bytes.startswith(
        b"PK"
    )

    assert filename.startswith(
        "invoice-evidence-"
    )

    assert filename.endswith(".zip")

    with ZipFile(
        io.BytesIO(archive_bytes)
    ) as archive:
        assert set(
            archive.namelist()
        ) == EXPECTED_FILES


def test_manifest_checksums_match_files(
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

    archive_bytes, _ = (
        build_invoice_evidence_pack(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    with ZipFile(
        io.BytesIO(archive_bytes)
    ) as archive:
        manifest = json.loads(
            archive.read(
                "manifest.json"
            )
        )

        assert (
            manifest["schema_version"]
            == "1.0"
        )

        assert (
            manifest["run_id"]
            == invoice["run_id"]
        )

        assert (
            manifest["invoice_number"]
            == invoice[
                "invoice_number"
            ]
        )

        for item in manifest["files"]:
            content = archive.read(
                item["name"]
            )

            assert len(content) == (
                item["size_bytes"]
            )

            assert hashlib.sha256(
                content
            ).hexdigest() == item["sha256"]


def test_invoice_and_audit_csv_are_readable(
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

    archive_bytes, _ = (
        build_invoice_evidence_pack(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    with ZipFile(
        io.BytesIO(archive_bytes)
    ) as archive:
        invoice_rows = list(
            csv.DictReader(
                io.StringIO(
                    archive.read(
                        "invoice.csv"
                    ).decode(
                        "utf-8-sig"
                    )
                )
            )
        )

        assert len(invoice_rows) == 1

        assert (
            invoice_rows[0][
                "invoice_number"
            ]
            == invoice["invoice_number"]
        )

        audit_rows = list(
            csv.DictReader(
                io.StringIO(
                    archive.read(
                        "audit_timeline.csv"
                    ).decode(
                        "utf-8-sig"
                    )
                )
            )
        )

        assert audit_rows

        assert (
            audit_rows[0]["event_type"]
            == "PROCESSING_RUN_COMPLETED"
        )


def test_snapshot_preserves_nested_evidence(
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

    archive_bytes, _ = (
        build_invoice_evidence_pack(
            invoice["run_id"],
            invoice["invoice_number"],
        )
    )

    with ZipFile(
        io.BytesIO(archive_bytes)
    ) as archive:
        snapshot = json.loads(
            archive.read(
                "evidence_snapshot.json"
            )
        )

    assert isinstance(
        snapshot["validation_findings"],
        list,
    )

    assert isinstance(
        snapshot["recommended_actions"],
        list,
    )

    assert isinstance(
        snapshot["audit_timeline"],
        list,
    )


def test_missing_invoice_is_rejected(
    tmp_path,
    monkeypatch,
):
    configure_database(
        tmp_path,
        monkeypatch,
    )

    try:
        build_invoice_evidence_pack(
            "RUN-NOT-FOUND",
            "INV-NOT-FOUND",
        )

    except ValueError as error:
        assert (
            str(error)
            == "Invoice assurance result was not found."
        )

    else:
        raise AssertionError(
            "Missing invoice was not rejected."
        )


def test_filename_component_is_sanitized():
    assert (
        sanitize_filename_component(
            ' INV/001:*?"<>| '
        )
        == "INV-001"
    )

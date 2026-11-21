import asyncio
import json
from types import SimpleNamespace

import billing_finance_ops_app as app_module


def request_for(
    run_id: str,
    invoice_number: str,
):
    return SimpleNamespace(
        path_params={
            "run_id": run_id,
            "invoice_number": invoice_number,
        }
    )


def test_evidence_pack_api_returns_zip(
    monkeypatch,
):
    expected_archive = (
        b"PK\x03\x04-test-archive"
    )

    monkeypatch.setattr(
        app_module,
        "build_invoice_evidence_pack",
        lambda run_id, invoice_number: (
            expected_archive,
            (
                "invoice-evidence-"
                f"{run_id}-"
                f"{invoice_number}.zip"
            ),
        ),
    )

    response = asyncio.run(
        app_module.invoice_evidence_pack_api(
            request_for(
                "RUN-20261121-001",
                "INV-001",
            )
        )
    )

    assert response.status_code == 200

    assert (
        response.media_type
        == "application/zip"
    )

    assert (
        response.body
        == expected_archive
    )

    assert (
        response.headers[
            "content-disposition"
        ]
        == (
            'attachment; filename="'
            "invoice-evidence-"
            "RUN-20261121-001-"
            'INV-001.zip"'
        )
    )

    assert (
        response.headers["cache-control"]
        == "no-store"
    )


def test_evidence_pack_api_returns_not_found(
    monkeypatch,
):
    def missing_invoice(
        run_id,
        invoice_number,
    ):
        raise ValueError(
            "Invoice assurance result was not found."
        )

    monkeypatch.setattr(
        app_module,
        "build_invoice_evidence_pack",
        missing_invoice,
    )

    response = asyncio.run(
        app_module.invoice_evidence_pack_api(
            request_for(
                "RUN-NOT-FOUND",
                "INV-NOT-FOUND",
            )
        )
    )

    assert response.status_code == 404

    assert json.loads(
        response.body
    ) == {
        "error": (
            "Invoice assurance result "
            "was not found."
        )
    }


def test_evidence_pack_api_returns_bad_request(
    monkeypatch,
):
    def invalid_request(
        run_id,
        invoice_number,
    ):
        raise ValueError(
            "An invoice number is required."
        )

    monkeypatch.setattr(
        app_module,
        "build_invoice_evidence_pack",
        invalid_request,
    )

    response = asyncio.run(
        app_module.invoice_evidence_pack_api(
            request_for(
                "RUN-001",
                "",
            )
        )
    )

    assert response.status_code == 400

    assert json.loads(
        response.body
    )["error"] == (
        "An invoice number is required."
    )

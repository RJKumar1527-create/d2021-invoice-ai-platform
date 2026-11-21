import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from assurance.repository import (
    get_invoice_result,
    list_invoice_audit_history,
)
from assurance.supplier_query_service import (
    list_queries,
)


EXPORT_SCHEMA_VERSION = "1.0"

NESTED_INVOICE_FIELDS = {
    "recommended_actions",
    "unusual_features",
    "validation_findings",
    "rule_citations",
}


def sanitize_filename_component(
    value: str,
) -> str:
    normalized = str(value or "").strip()

    normalized = re.sub(
        r'[\x00-\x1f<>:"/\\|?*]+',
        "-",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        "-",
        normalized,
    )

    normalized = re.sub(
        r"-+",
        "-",
        normalized,
    )

    normalized = normalized.strip(
        ".-_ "
    )

    return normalized[:100] or "unknown"


def json_text(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def csv_bytes(
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> bytes:
    output = io.StringIO(
        newline=""
    )

    if fieldnames is None:
        discovered_fields: list[str] = []

        for row in rows:
            for field in row:
                if field not in discovered_fields:
                    discovered_fields.append(field)

        fieldnames = discovered_fields

    if not fieldnames:
        fieldnames = ["record"]

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )

    writer.writeheader()

    for row in rows:
        normalized_row = {}

        for field in fieldnames:
            value = row.get(
                field,
                "",
            )

            if isinstance(
                value,
                (
                    dict,
                    list,
                    tuple,
                    set,
                ),
            ):
                value = json_text(value)

            elif isinstance(value, bool):
                value = str(value).lower()

            elif value is None:
                value = ""

            normalized_row[field] = value

        writer.writerow(
            normalized_row
        )

    return output.getvalue().encode(
        "utf-8-sig"
    )


def invoice_csv_row(
    invoice: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in invoice.items()
        if key not in NESTED_INVOICE_FIELDS
    }


def validation_finding_rows(
    invoice: dict[str, Any],
) -> list[dict[str, Any]]:
    findings = invoice.get(
        "validation_findings"
    ) or []

    rows = []

    for position, finding in enumerate(
        findings,
        start=1,
    ):
        row = {
            "finding_number": position,
            "run_id": invoice["run_id"],
            "invoice_number": invoice[
                "invoice_number"
            ],
        }

        if isinstance(finding, dict):
            row.update(finding)
        else:
            row["finding"] = finding

        rows.append(row)

    return rows


def exception_rows(
    invoice: dict[str, Any],
) -> list[dict[str, Any]]:
    if (
        invoice.get("assurance_status")
        != "EXCEPTION"
    ):
        return []

    return [
        {
            "run_id": invoice["run_id"],
            "invoice_number": invoice[
                "invoice_number"
            ],
            "exception_category": invoice.get(
                "exception_category"
            ),
            "priority": invoice.get(
                "priority"
            ),
            "risk_score": invoice.get(
                "risk_score"
            ),
            "risk_level": invoice.get(
                "risk_level"
            ),
            "estimated_exposure": invoice.get(
                "estimated_exposure"
            ),
            "exposure_percentage": invoice.get(
                "exposure_percentage"
            ),
            "blocks_approval": invoice.get(
                "blocks_approval"
            ),
            "workflow_status": invoice.get(
                "workflow_status"
            ),
            "owner": invoice.get("owner"),
            "due_date": invoice.get(
                "due_date"
            ),
            "confirmed_root_cause": invoice.get(
                "confirmed_root_cause"
            ),
            "resolution_notes": invoice.get(
                "resolution_notes"
            ),
            "decision": invoice.get(
                "decision"
            ),
            "decision_reason": invoice.get(
                "decision_reason"
            ),
        }
    ]


def supplier_query_rows(
    run_id: str,
    invoice_number: str,
) -> list[dict[str, Any]]:
    return [
        query
        for query in list_queries()
        if (
            query.get("run_id") == run_id
            and query.get(
                "invoice_number"
            ) == invoice_number
        )
    ]


def audit_csv_rows(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []

    for event in events:
        rows.append(
            {
                "audit_id": event.get(
                    "audit_id"
                ),
                "run_id": event.get(
                    "run_id"
                ),
                "invoice_number": event.get(
                    "invoice_number"
                ),
                "scope": event.get(
                    "scope"
                ),
                "event_type": event.get(
                    "event_type"
                ),
                "created_at": event.get(
                    "created_at"
                ),
                "payload_json": json_text(
                    event.get("payload") or {}
                ),
            }
        )

    return rows


def sha256_hex(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def build_invoice_evidence_pack(
    run_id: str,
    invoice_number: str,
) -> tuple[bytes, str]:
    normalized_run_id = str(
        run_id
    ).strip()

    normalized_invoice_number = str(
        invoice_number
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "A processing run ID is required."
        )

    if not normalized_invoice_number:
        raise ValueError(
            "An invoice number is required."
        )

    invoice = get_invoice_result(
        normalized_run_id,
        normalized_invoice_number,
    )

    if invoice is None:
        raise ValueError(
            "Invoice assurance result was not found."
        )

    queries = supplier_query_rows(
        normalized_run_id,
        normalized_invoice_number,
    )

    audit_events = (
        list_invoice_audit_history(
            run_id=normalized_run_id,
            invoice_number=(
                normalized_invoice_number
            ),
        )
    )

    snapshot = {
        "schema_version": (
            EXPORT_SCHEMA_VERSION
        ),
        "exported_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "run_id": normalized_run_id,
        "invoice_number": (
            normalized_invoice_number
        ),
        "invoice": invoice,
        "validation_findings": invoice.get(
            "validation_findings"
        ) or [],
        "recommended_actions": invoice.get(
            "recommended_actions"
        ) or [],
        "unusual_features": invoice.get(
            "unusual_features"
        ) or [],
        "rule_citations": invoice.get(
            "rule_citations"
        ) or [],
        "exceptions": exception_rows(
            invoice
        ),
        "supplier_queries": queries,
        "audit_timeline": audit_events,
    }

    files = {
        "invoice.csv": csv_bytes(
            [invoice_csv_row(invoice)]
        ),
        "validation_findings.csv": csv_bytes(
            validation_finding_rows(invoice),
            fieldnames=None,
        ),
        "exceptions.csv": csv_bytes(
            exception_rows(invoice),
            fieldnames=[
                "run_id",
                "invoice_number",
                "exception_category",
                "priority",
                "risk_score",
                "risk_level",
                "estimated_exposure",
                "exposure_percentage",
                "blocks_approval",
                "workflow_status",
                "owner",
                "due_date",
                "confirmed_root_cause",
                "resolution_notes",
                "decision",
                "decision_reason",
            ],
        ),
        "supplier_queries.csv": csv_bytes(
            queries
        ),
        "audit_timeline.csv": csv_bytes(
            audit_csv_rows(
                audit_events
            ),
            fieldnames=[
                "audit_id",
                "run_id",
                "invoice_number",
                "scope",
                "event_type",
                "created_at",
                "payload_json",
            ],
        ),
        "evidence_snapshot.json": (
            json.dumps(
                snapshot,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ),
    }

    record_counts = {
        "invoice": 1,
        "validation_findings": len(
            snapshot["validation_findings"]
        ),
        "exceptions": len(
            snapshot["exceptions"]
        ),
        "supplier_queries": len(
            queries
        ),
        "audit_timeline": len(
            audit_events
        ),
    }

    manifest = {
        "schema_version": (
            EXPORT_SCHEMA_VERSION
        ),
        "exported_at": snapshot[
            "exported_at"
        ],
        "run_id": normalized_run_id,
        "invoice_number": (
            normalized_invoice_number
        ),
        "record_counts": record_counts,
        "files": [
            {
                "name": name,
                "size_bytes": len(content),
                "sha256": sha256_hex(
                    content
                ),
            }
            for name, content in files.items()
        ],
    }

    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")

    archive_buffer = io.BytesIO()

    with ZipFile(
        archive_buffer,
        mode="w",
        compression=ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "manifest.json",
            manifest_bytes,
        )

        for name, content in files.items():
            archive.writestr(
                name,
                content,
            )

    safe_run_id = (
        sanitize_filename_component(
            normalized_run_id
        )
    )

    safe_invoice_number = (
        sanitize_filename_component(
            normalized_invoice_number
        )
    )

    filename = (
        "invoice-evidence-"
        f"{safe_run_id}-"
        f"{safe_invoice_number}.zip"
    )

    return (
        archive_buffer.getvalue(),
        filename,
    )

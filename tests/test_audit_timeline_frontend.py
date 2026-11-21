from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_JS = (
    PROJECT_ROOT
    / "billing_finance_ops_web"
    / "app.js"
)

STYLES_CSS = (
    PROJECT_ROOT
    / "billing_finance_ops_web"
    / "styles.css"
)


def read_app_js() -> str:
    return APP_JS.read_text(
        encoding="utf-8"
    )


def read_styles_css() -> str:
    return STYLES_CSS.read_text(
        encoding="utf-8"
    )


def test_audit_timeline_uses_readable_formatters():
    source = read_app_js()

    assert (
        "function formatAuditDateTime("
        in source
    )

    assert (
        'timeZone: "Asia/Kolkata"'
        in source
    )

    assert (
        "function formatAuditPercentage("
        in source
    )

    assert (
        "return money(value);"
        in source
    )

    assert (
        '"estimated_financial_exposure"'
        in source
    )

    assert (
        '"disputed_amount"'
        in source
    )


def test_processing_run_payload_is_compact():
    source = read_app_js()

    assert (
        'eventType === "PROCESSING_RUN_COMPLETED"'
        in source
    )

    assert (
        "entries.length > 6"
        in source
    )

    assert (
        "Show all details"
        in source
    )

    assert (
        'class="audit-payload-details"'
        in source
    )


def test_audit_event_filter_is_available():
    source = read_app_js()

    assert (
        'id="auditEventFilter"'
        in source
    )

    assert (
        'onchange="filterInvoiceAuditHistory()"'
        in source
    )

    assert (
        "function auditEventFilterOptions("
        in source
    )

    assert (
        "function filterInvoiceAuditHistory("
        in source
    )

    assert (
        "function renderInvoiceAuditEvents("
        in source
    )

    assert re.search(
        r"item\.event_type\s*===\s*selectedEventType",
        source
    )


def test_audit_timeline_styles_support_details_and_filter():
    styles = read_styles_css()

    assert ".audit-payload-details {" in styles
    assert ".audit-timeline-actions {" in styles
    assert ".audit-filter-control {" in styles

    assert (
        ".audit-filter-control select {"
        in styles
    )

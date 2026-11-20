from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


@dataclass
class InvoiceAssuranceInput:
    invoice_number: str
    safe_invoice_alias: str
    source_file: str
    invoice_type: str
    billing_period_start: str
    billing_period_end: str

    invoice_net_amount: float
    reconciliation_variance: float
    anomaly_score: float
    risk_score: float
    risk_level: str

    critical_validation_failures: int = 0
    validation_warnings: int = 0
    reconciliation_status: str = "UNKNOWN"
    model_result: str = "UNKNOWN"

    billed_rate: float | None = None
    expected_rate: float | None = None
    billed_quantity: float | None = None

    billed_capacity: float | None = None
    approved_capacity: float | None = None
    capacity_rate: float | None = None
    billing_period_factor: float = 1.0

    billed_charge_amount: float | None = None
    robust_expected_amount: float | None = None

    unusual_features: list[str] = field(
        default_factory=list
    )

    validation_findings: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    rule_citations: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinancialExposure:
    confirmed_variance: float
    rate_exposure: float
    capacity_exposure: float
    statistical_exposure: float
    estimated_exposure: float
    exposure_percentage: float
    exposure_basis: str
    exposure_confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssuranceDecision:
    decision: str
    decision_reason: str
    recommended_actions: list[str]
    exception_category: str
    priority: str
    requires_human_review: bool
    requires_supplier_query: bool
    blocks_approval: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssuredInvoice:
    processing_run_id: str
    invoice: InvoiceAssuranceInput
    exposure: FinancialExposure
    decision: AssuranceDecision
    assurance_status: str
    created_at: str = field(
        default_factory=utc_timestamp
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DailyProcessingRun:
    run_id: str
    run_date: str
    source_files: list[str]
    status: str
    started_at: str
    completed_at: str | None
    invoices: list[AssuredInvoice]

    @classmethod
    def create(
        cls,
        source_files: list[str],
    ):
        now = datetime.now(
            timezone.utc
        )

        return cls(
            run_id=(
                "RUN-"
                + now.strftime("%Y%m%d")
                + "-"
                + uuid4().hex[:8].upper()
            ),
            run_date=now.date().isoformat(),
            source_files=source_files,
            status="PROCESSING",
            started_at=now.isoformat(),
            completed_at=None,
            invoices=[],
        )

    def complete(self):
        self.status = "COMPLETED"

        self.completed_at = datetime.now(
            timezone.utc
        ).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
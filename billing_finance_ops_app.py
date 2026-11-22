import csv
import io
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
)
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from configuration.settings import settings

from assurance.repository import (
    create_supplier_query,
    get_exception_ageing_summary,
    get_financial_control_summary,
    get_invoice_result,
    get_invoice_supplier_query,
    get_report_summary,
    latest_run_summary,
    list_active_exceptions,
    list_daily_run_trend,
    list_invoice_results,
    list_invoice_audit_history,
    list_latest_active_exceptions,
    list_processing_runs,
    list_resolved_exceptions,
    list_supplier_queries,
    update_invoice_resolution,
    update_supplier_query,
)
from assurance.evidence_pack_service import (
    build_invoice_evidence_pack,
)
from assurance.service import run_synthetic_demo
from assurance.supplier_query_service import (
    create_query,
    get_query_summary,
    list_queries,
    update_query,
)


PROJECT_ROOT = Path(__file__).resolve().parent

WEB_ROOT = (
    PROJECT_ROOT
    / "billing_finance_ops_web"
)

from processing.daily_file_service import (
    DailyFileProcessingError,
    get_daily_intake_summary,
    get_failed_files,
    list_registered_files,
    process_runtime_file,
)

from monitoring.operations import (
    CorrelationLoggingMiddleware,
    database_health,
    monitoring_snapshot,
)


from processing.recovery_service import (
    authorize_retry,
    list_recovery_records,
    mark_stale_processing_records,
)

async def home(request: Request):
    return FileResponse(
        WEB_ROOT / "index.html"
    )


async def health_api(request: Request):
    return JSONResponse(
        {
            "status": "UP",
            "application": "Billing / Finance Ops",
        }
    )


async def runs_api(request: Request):
    return JSONResponse(
        {
            "runs": list_processing_runs()
        }
    )


async def latest_dashboard_api(
    request: Request,
):
    summary = latest_run_summary()

    return JSONResponse(
        {
            "available": summary is not None,
            "summary": summary,
        }
    )


async def demo_run_api(request: Request):
    if not settings.demo_mode:
        return JSONResponse(
            {
                "error": (
                    "Synthetic processing is disabled."
                )
            },
            status_code=403,
        )

    try:
        return JSONResponse(
            run_synthetic_demo()
        )

    except Exception as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=500,
        )


async def invoices_api(request: Request):
    run_id = request.query_params.get(
        "run_id"
    )

    exceptions_only = (
        request.query_params.get(
            "exceptions_only",
            "false",
        ).lower()
        == "true"
    )

    if exceptions_only:
        results = list_latest_active_exceptions(
            run_id=run_id
        )

    else:
        results = list_invoice_results(
            run_id=run_id,
            exceptions_only=False,
        )

    return JSONResponse(
        {
            "invoices": results
        }
    )

async def invoice_api(request: Request):
    result = get_invoice_result(
        request.path_params["run_id"],
        request.path_params[
            "invoice_number"
        ],
    )

    if result is None:
        return JSONResponse(
            {
                "error": (
                    "Invoice assurance result "
                    "was not found."
                )
            },
            status_code=404,
        )

    return JSONResponse(result)


async def resolution_api(request: Request):
    payload = await request.json()

    try:
        result = update_invoice_resolution(
            run_id=str(
                payload["run_id"]
            ),
            invoice_number=str(
                payload["invoice_number"]
            ),
            workflow_status=str(
                payload["workflow_status"]
            ),
            owner=str(
                payload.get(
                    "owner",
                    "",
                )
            ),
            confirmed_root_cause=str(
                payload.get(
                    "confirmed_root_cause",
                    "",
                )
            ),
            resolution_notes=str(
                payload.get(
                    "resolution_notes",
                    "",
                )
            ),
        )

        return JSONResponse(result)

    except (
        KeyError,
        ValueError,
    ) as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )


async def supplier_queries_api(
    request: Request,
):
    if request.method == "GET":
        return JSONResponse(
            {
                "queries": (
                    list_queries()
                )
            }
        )

    payload = await request.json()

    try:
        result = create_query(
            run_id=str(
                payload["run_id"]
            ),
            invoice_number=str(
                payload["invoice_number"]
            ),
            owner=str(
                payload.get(
                    "owner",
                    "Supplier Query Team",
                )
            ),
            due_date=str(
                payload.get(
                    "due_date",
                    "",
                )
            ),
        )

        return JSONResponse(result)

    except (
        KeyError,
        ValueError,
    ) as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )


async def supplier_query_update_api(
    request: Request,
):
    payload = await request.json()

    try:
        result = update_query(
            query_id=int(
                request.path_params[
                    "query_id"
                ]
            ),
            query_status=str(
                payload["query_status"]
            ),
            supplier_response=str(
                payload.get(
                    "supplier_response",
                    "",
                )
            ),
            final_resolution=str(
                payload.get(
                    "final_resolution",
                    "",
                )
            ),
            recovered_value=float(
                payload.get(
                    "recovered_value",
                    0,
                )
                or 0
            ),
        )

        return JSONResponse(result)

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )


async def reports_api(request: Request):
    return JSONResponse(
        get_report_summary()
    )


async def export_exceptions_api(
    request: Request,
):
    invoices = list_invoice_results(
        exceptions_only=True
    )

    buffer = io.StringIO()

    writer = csv.writer(buffer)

    writer.writerow(
        [
            "Run ID",
            "Invoice",
            "Invoice Value",
            "Estimated Exposure",
            "Risk Level",
            "Category",
            "Decision",
            "Priority",
            "Workflow Status",
            "Owner",
        ]
    )

    for item in invoices:
        writer.writerow(
            [
                item["run_id"],
                item[
                    "safe_invoice_alias"
                ],
                item["invoice_value"],
                item[
                    "estimated_exposure"
                ],
                item["risk_level"],
                item[
                    "exception_category"
                ],
                item["decision"],
                item["priority"],
                item[
                    "workflow_status"
                ],
                item["owner"],
            ]
        )

    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                "billing_finance_ops_exceptions.csv"
            )
        },
    )


routes = [
    Route(
        "/",
        home,
        methods=["GET"],
    ),
    Route(
        "/health",
        health_api,
        methods=["GET"],
    ),
    Route(
        "/api/runs",
        runs_api,
        methods=["GET"],
    ),
    Route(
        "/api/dashboard/latest",
        latest_dashboard_api,
        methods=["GET"],
    ),
    Route(
        "/api/demo-run",
        demo_run_api,
        methods=["POST"],
    ),
    Route(
        "/api/invoices",
        invoices_api,
        methods=["GET"],
    ),
    Route(
        "/api/invoices/{run_id}/{invoice_number}",
        invoice_api,
        methods=["GET"],
    ),
    Route(
        "/api/resolution",
        resolution_api,
        methods=["PUT"],
    ),
    Route(
        "/api/supplier-queries",
        supplier_queries_api,
        methods=["GET", "POST"],
    ),
    Route(
        "/api/supplier-queries/{query_id:int}",
        supplier_query_update_api,
        methods=["PUT"],
    ),
    Route(
        "/api/reports",
        reports_api,
        methods=["GET"],
    ),
    Route(
        "/api/exports/exceptions.csv",
        export_exceptions_api,
        methods=["GET"],
    ),
]


application = Starlette(
    debug=True,
    routes=routes,
)


application.mount(
    "/assets",
    StaticFiles(
        directory=WEB_ROOT
    ),
    name="assets",
)

# ---------------------------------------------------------
# Grounded invoice investigation
# ---------------------------------------------------------
from assurance.investigation_service import (
    generate_investigation_summary,
)


async def investigation_summary_api(
    request: Request,
):
    payload = await request.json()

    try:
        invoice = get_invoice_result(
            run_id=str(
                payload["run_id"]
            ),
            invoice_number=str(
                payload["invoice_number"]
            ),
        )

        if invoice is None:
            return JSONResponse(
                {
                    "error": (
                        "Invoice assurance result "
                        "was not found."
                    )
                },
                status_code=404,
            )

        generated = (
            generate_investigation_summary(
                invoice
            )
        )

        return JSONResponse(
            generated["investigation"]
        )

    except KeyError as error:
        return JSONResponse(
            {
                "error": (
                    f"Missing request field: "
                    f"{error}"
                )
            },
            status_code=400,
        )

    except Exception as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=500,
        )


application.routes.append(
    Route(
        "/api/investigation-summary",
        investigation_summary_api,
        methods=["POST"],
    )
)


async def supplier_query_summary_api(
    request: Request,
):
    return JSONResponse(
        get_query_summary()
    )


application.routes.append(
    Route(
        "/api/supplier-query-summary",
        supplier_query_summary_api,
        methods=["GET"],
    )
)


async def daily_intake_summary_api(
    request: Request,
):
    run_date = request.query_params.get(
        "run_date"
    )

    return JSONResponse(
        get_daily_intake_summary(
            run_date=run_date
        )
    )


async def failed_files_api(
    request: Request,
):
    return JSONResponse(
        {
            "files": get_failed_files()
        }
    )


application.routes.extend(
    [
        Route(
            "/api/daily-intake-summary",
            daily_intake_summary_api,
            methods=["GET"],
        ),
        Route(
            "/api/failed-files",
            failed_files_api,
            methods=["GET"],
        ),
    ]
)


async def process_file_api(
    request: Request,
):
    file_name = str(
        request.headers.get(
            "X-File-Name",
            "",
        )
    ).strip()

    file_extension = Path(
        file_name
    ).suffix.lower()

    if (
        file_extension
        not in settings.allowed_file_extensions
    ):
        return JSONResponse(
            {
                "error": (
                    "Unsupported billing-file extension. "
                    "Allowed extensions: "
                    + ", ".join(
                        settings.allowed_file_extensions
                    )
                )
            },
            status_code=400,
        )

    file_bytes = await request.body()

    if (
        len(file_bytes)
        > settings.max_file_size_bytes
    ):
        return JSONResponse(
            {
                "error": (
                    "The billing file exceeds the "
                    f"{settings.max_file_size_mb} MB limit."
                )
            },
            status_code=413,
        )

    try:
        result = process_runtime_file(
            file_name=file_name,
            file_bytes=file_bytes,
        )

        return JSONResponse(result)

    except DailyFileProcessingError as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )

    except Exception as error:
        return JSONResponse(
            {
                "error": (
                    "The billing file could not "
                    f"be processed: {error}"
                )
            },
            status_code=500,
        )


async def registered_files_api(
    request: Request,
):
    return JSONResponse(
        {
            "files": list_registered_files()
        }
    )


application.routes.extend(
    [
        Route(
            "/api/process-file",
            process_file_api,
            methods=["POST"],
        ),
        Route(
            "/api/registered-files",
            registered_files_api,
            methods=["GET"],
        ),
    ]
)


async def invoice_supplier_query_api(
    request: Request,
):
    run_id = request.path_params[
        "run_id"
    ]

    invoice_number = (
        request.path_params[
            "invoice_number"
        ]
    )

    query = get_invoice_supplier_query(
        run_id=run_id,
        invoice_number=invoice_number,
    )

    return JSONResponse(
        {
            "available": query is not None,
            "query": query,
        }
    )


application.routes.append(
    Route(
        (
            "/api/invoices/"
            "{run_id}/{invoice_number}/"
            "supplier-query"
        ),
        invoice_supplier_query_api,
        methods=["GET"],
    )
)


async def processing_recovery_api(
    request: Request,
):
    stale_count = (
        mark_stale_processing_records()
    )

    return JSONResponse(
        {
            "stale_records_marked": (
                stale_count
            ),
            "records": (
                list_recovery_records()
            ),
        }
    )


async def authorize_file_retry_api(
    request: Request,
):
    registry_id = int(
        request.path_params[
            "registry_id"
        ]
    )

    try:
        record = authorize_retry(
            registry_id
        )

        return JSONResponse(
            {
                "record": record
            }
        )

    except ValueError as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )


application.routes.extend(
    [
        Route(
            "/api/processing-recovery",
            processing_recovery_api,
            methods=["GET"],
        ),
        Route(
            (
                "/api/processing-recovery/"
                "{registry_id:int}/authorize"
            ),
            authorize_file_retry_api,
            methods=["POST"],
        ),
    ]
)


async def invoice_audit_history_api(
    request: Request,
):
    run_id = request.path_params[
        "run_id"
    ]

    invoice_number = (
        request.path_params[
            "invoice_number"
        ]
    )

    try:
        events = (
            list_invoice_audit_history(
                run_id=run_id,
                invoice_number=(
                    invoice_number
                ),
            )
        )

        return JSONResponse(
            {
                "run_id": run_id,
                "invoice_number": (
                    invoice_number
                ),
                "events": events,
            }
        )

    except ValueError as error:
        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=400,
        )


async def invoice_evidence_pack_api(
    request: Request,
):
    run_id = request.path_params[
        "run_id"
    ]

    invoice_number = request.path_params[
        "invoice_number"
    ]

    try:
        archive_bytes, filename = (
            build_invoice_evidence_pack(
                run_id=run_id,
                invoice_number=(
                    invoice_number
                ),
            )
        )

        return Response(
            archive_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    'attachment; filename="'
                    f'{filename}"'
                ),
                "Cache-Control": (
                    "no-store"
                ),
            },
        )

    except ValueError as error:
        status_code = (
            404
            if "not found" in str(error).lower()
            else 400
        )

        return JSONResponse(
            {
                "error": str(error)
            },
            status_code=status_code,
        )


application.routes.append(
    Route(
        (
            "/api/invoices/"
            "{run_id}/{invoice_number}/"
            "audit-history"
        ),
        invoice_audit_history_api,
        methods=["GET"],
    )
)


application.routes.append(
    Route(
        (
            "/api/invoices/"
            "{run_id}/{invoice_number}/"
            "evidence-pack"
        ),
        invoice_evidence_pack_api,
        methods=["GET"],
    )
)


async def configuration_api(
    request: Request,
):
    return JSONResponse(
        settings.public_configuration()
    )


application.routes.append(
    Route(
        "/api/configuration",
        configuration_api,
        methods=["GET"],
    )
)


async def live_health_api(
    request: Request,
):
    return JSONResponse(
        {
            "status": "UP",
            "application": (
                "Billing / Finance Ops"
            ),
        }
    )


async def database_health_api(
    request: Request,
):
    result = database_health()

    return JSONResponse(
        result,
        status_code=(
            200
            if result["status"] == "UP"
            else 503
        ),
    )


async def readiness_health_api(
    request: Request,
):
    result = database_health()

    ready = (
        result["status"] == "UP"
    )

    return JSONResponse(
        {
            "status": (
                "READY"
                if ready
                else "NOT READY"
            ),
            "checks": result,
        },
        status_code=(
            200
            if ready
            else 503
        ),
    )


async def operations_metrics_api(
    request: Request,
):
    result = monitoring_snapshot()

    return JSONResponse(
        result,
        status_code=(
            200
            if result["status"]
            in {
                "UP",
                "DEGRADED",
            }
            else 503
        ),
    )


application.routes.extend(
    [
        Route(
            "/health/live",
            live_health_api,
            methods=["GET"],
        ),
        Route(
            "/health/ready",
            readiness_health_api,
            methods=["GET"],
        ),
        Route(
            "/health/database",
            database_health_api,
            methods=["GET"],
        ),
        Route(
            "/api/operations/metrics",
            operations_metrics_api,
            methods=["GET"],
        ),
    ]
)


application.add_middleware(
    CorrelationLoggingMiddleware
)


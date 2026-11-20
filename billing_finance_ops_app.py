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
    list_processing_runs,
    list_resolved_exceptions,
    list_supplier_queries,
    update_invoice_resolution,
    update_supplier_query,
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
        results = list_active_exceptions(
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

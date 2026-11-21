let selectedInvoice = null;
let selectedSupplierQuery = null;
let activeExceptionRows = [];


function money(value) {
    return new Intl.NumberFormat(
        "en-GB",
        {
            style: "currency",
            currency: "GBP"
        }
    ).format(
        Number(value || 0)
    );
}


function escapeHtml(value) {
    const element = document.createElement(
        "div"
    );

    element.textContent = value || "";

    return element.innerHTML;
}


function priorityTag(priority) {
    const className = (
        priority === "CRITICAL"
        ? "tag-critical"
        : priority === "HIGH"
        ? "tag-high"
        : "tag-medium"
    );

    return `
        <span class="tag ${className}">
            ${escapeHtml(priority)}
        </span>
    `;
}


document.querySelectorAll(
    ".navigation-tab"
).forEach(
    button => {
        button.addEventListener(
            "click",
            () => {
                document.querySelectorAll(
                    ".navigation-tab"
                ).forEach(
                    item => item.classList.remove(
                        "active"
                    )
                );

                document.querySelectorAll(
                    ".page"
                ).forEach(
                    page => page.classList.remove(
                        "active"
                    )
                );

                button.classList.add(
                    "active"
                );

                const pageId = (
                    button.dataset.page
                );

                document.getElementById(
                    pageId
                ).classList.add(
                    "active"
                );

                if (
                    pageId === "exceptions"
                ) {
                    loadExceptions();
                }

                if (
                    pageId
                    === "supplier-queries"
                ) {
                    loadSupplierQueries();
                }

                if (pageId === "reports") {
                    loadReports();
                }

                if (
                    pageId
                    === "administration"
                ) {
                    loadHealth();
                }
            }
        );
    }
);


function openPage(pageId) {
    const button = document.querySelector(
        `[data-page="${pageId}"]`
    );

    if (button) {
        button.click();
    }
}


function renderSummary(summary) {
    document.getElementById(
        "currentRun"
    ).textContent = (
        summary.run_id
        || "No active run"
    );

    document.getElementById(
        "metricInvoices"
    ).textContent = (
        summary.total_invoices || 0
    );

    document.getElementById(
        "metricSafe"
    ).textContent = (
        summary.safe_to_progress || 0
    );

    document.getElementById(
        "metricExceptions"
    ).textContent = (
        summary.exceptions || 0
    );

    document.getElementById(
        "metricExposure"
    ).textContent = money(
        summary
        .estimated_financial_exposure
        ?? summary.estimated_exposure
    );

    document.getElementById(
        "metricQueries"
    ).textContent = (
        summary
        .supplier_queries_required
        ?? summary.supplier_queries
        ?? 0
    );

    document.getElementById(
        "metricValue"
    ).textContent = money(
        summary.total_invoice_value
    );

    document.getElementById(
        "metricHeld"
    ).textContent = money(
        summary.held_invoice_value
    );

    const exposure = Number(
        summary
        .estimated_financial_exposure
        ?? summary.estimated_exposure
        ?? 0
    );

    const invoiceValue = Number(
        summary.total_invoice_value
        || 0
    );

    document.getElementById(
        "metricExposureRate"
    ).textContent = (
        invoiceValue
        ? (
            exposure
            / invoiceValue
            * 100
        ).toFixed(2)
        : "0.00"
    ) + "%";

    document.getElementById(
        "actionSummary"
    ).innerHTML = `
        <p>
            <strong>
                ${summary.exceptions || 0}
            </strong>
            invoices require business action.
        </p>

        <p>
            <strong>
                ${
                    summary
                    .critical_exceptions
                    || 0
                }
            </strong>
            critical exceptions require
            immediate attention.
        </p>

        <p>
            <strong>
                ${
                    summary
                    .supplier_queries_required
                    ?? summary.supplier_queries
                    ?? 0
                }
            </strong>
            supplier queries are recommended.
        </p>
    `;
}


async function loadLatest() {
    const response = await fetch(
        "/api/dashboard/latest"
    );

    const result = await response.json();

    if (
        result.available
        && result.summary
    ) {
        renderSummary(
            result.summary
        );
    }
}


async function loadRuns() {
    const response = await fetch(
        "/api/runs"
    );

    const result = await response.json();

    const runs = result.runs || [];

    document.getElementById(
        "runTable"
    ).innerHTML = runs.length
        ? `
            <table>
                <thead>
                    <tr>
                        <th>Run</th>
                        <th>Date</th>
                        <th>Files</th>
                        <th>Invoices</th>
                        <th>Safe</th>
                        <th>Exceptions</th>
                        <th>Exposure</th>
                    </tr>
                </thead>

                <tbody>
                    ${runs.map(
                        run => `
                            <tr>
                                <td>
                                    ${escapeHtml(
                                        run.run_id
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        run.run_date
                                    )}
                                </td>

                                <td>
                                    ${
                                        (
                                            run.source_files
                                            || []
                                        ).length
                                    }
                                </td>

                                <td>
                                    ${run.total_invoices}
                                </td>

                                <td>
                                    ${run.safe_to_progress}
                                </td>

                                <td>
                                    ${run.exceptions}
                                </td>

                                <td>
                                    ${money(
                                        run.estimated_exposure
                                    )}
                                </td>
                            </tr>
                        `
                    ).join("")}
                </tbody>
            </table>
        `
        : "<p>No processing runs are available.</p>";
}


async function runDailyBatch() {
    const button = document.getElementById(
        "runBatchButton"
    );

    button.disabled = true;
    button.textContent = "Processing...";

    try {
        const response = await fetch(
            "/api/demo-run",
            {
                method: "POST"
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "Processing failed."
            );
        }

        renderSummary(
            result.summary
        );

        await loadRuns();
        await loadExceptions();

        document.getElementById(
            "serviceHealth"
        ).innerHTML = `
            <div class="status-message">
                Synthetic daily batch completed.
            </div>
        `;

        openPage("control-room");
    }
    catch (error) {
        alert(error.message);
    }
    finally {
        button.disabled = false;
        button.textContent = (
            "Run Synthetic Daily Batch"
        );
    }
}


async function loadExceptions() {
    const response = await fetch(
        "/api/invoices?exceptions_only=true"
    );

    const result = await response.json();

    if (!response.ok) {
        document.getElementById(
            "exceptionQueue"
        ).innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(
                    result.error
                    || "Exceptions could not be loaded."
                )}
            </div>
        `;

        return;
    }

    activeExceptionRows = (
        result.invoices || []
    );

    populateExceptionFilterOptions();

    applyExceptionFilters();
}


function uniqueSortedValues(
    rows,
    fieldName
) {
    return Array.from(
        new Set(
            rows
                .map(
                    row => String(
                        row[fieldName]
                        || ""
                    ).trim()
                )
                .filter(Boolean)
        )
    ).sort();
}


function populateSelectOptions(
    elementId,
    values,
    defaultLabel
) {
    const element = document.getElementById(
        elementId
    );

    if (!element) {
        return;
    }

    const currentValue = element.value;

    element.innerHTML = `
        <option value="">
            ${escapeHtml(defaultLabel)}
        </option>

        ${values.map(
            value => `
                <option value="${escapeHtml(value)}">
                    ${escapeHtml(value)}
                </option>
            `
        ).join("")}
    `;

    if (
        values.includes(
            currentValue
        )
    ) {
        element.value = currentValue;
    }
}


function populateExceptionFilterOptions() {
    populateSelectOptions(
        "exceptionDecisionFilter",
        uniqueSortedValues(
            activeExceptionRows,
            "decision"
        ),
        "All decisions"
    );

    populateSelectOptions(
        "exceptionSourceFilter",
        uniqueSortedValues(
            activeExceptionRows,
            "source_file"
        ),
        "All source files"
    );

    populateSelectOptions(
        "exceptionRunFilter",
        uniqueSortedValues(
            activeExceptionRows,
            "run_id"
        ),
        "All runs"
    );
}


function getFilterValue(elementId) {
    const element = document.getElementById(
        elementId
    );

    return element
        ? String(
            element.value || ""
        )
        : "";
}


function applyExceptionFilters() {
    const priority = getFilterValue(
        "exceptionPriorityFilter"
    );

    const decision = getFilterValue(
        "exceptionDecisionFilter"
    );

    const workflowStatus = getFilterValue(
        "exceptionStatusFilter"
    );

    const sourceFile = getFilterValue(
        "exceptionSourceFilter"
    );

    const runId = getFilterValue(
        "exceptionRunFilter"
    );

    const filtered = activeExceptionRows.filter(
        item => (
            (!priority
                || item.priority === priority)
            && (!decision
                || item.decision === decision)
            && (!workflowStatus
                || item.workflow_status
                === workflowStatus)
            && (!sourceFile
                || item.source_file
                === sourceFile)
            && (!runId
                || item.run_id === runId)
        )
    );

    renderExceptionQueue(filtered);

    const position = document.getElementById(
        "exceptionQueuePosition"
    );

    if (position) {
        position.textContent = (
            `Showing ${filtered.length} of `
            + `${activeExceptionRows.length} `
            + "active exceptions."
        );
    }
}


function clearExceptionFilters() {
    [
        "exceptionPriorityFilter",
        "exceptionDecisionFilter",
        "exceptionStatusFilter",
        "exceptionSourceFilter",
        "exceptionRunFilter"
    ].forEach(
        elementId => {
            const element = document.getElementById(
                elementId
            );

            if (element) {
                element.value = "";
            }
        }
    );

    applyExceptionFilters();
}


function renderExceptionQueue(invoices) {
    const container = document.getElementById(
        "exceptionQueue"
    );

    container.innerHTML = invoices.length
        ? `
            <table>
                <thead>
                    <tr>
                        <th>Invoice</th>
                        <th>Exposure</th>
                        <th>Decision</th>
                        <th>Priority</th>
                        <th></th>
                    </tr>
                </thead>

                <tbody>
                    ${invoices.map(
                        item => `
                            <tr>
                                <td>
                                    <strong>
                                        ${escapeHtml(
                                            item.safe_invoice_alias
                                        )}
                                    </strong>

                                    <div>
                                        ${money(
                                            item.invoice_value
                                        )}
                                    </div>

                                    <div class="queue-secondary">
                                        ${escapeHtml(
                                            item.source_file
                                        )}
                                    </div>
                                </td>

                                <td>
                                    ${money(
                                        item.estimated_exposure
                                    )}

                                    <div>
                                        ${Number(
                                            item.exposure_percentage
                                            || 0
                                        ).toFixed(2)}%
                                    </div>
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.decision
                                    )}

                                    <div class="queue-secondary">
                                        ${escapeHtml(
                                            item.workflow_status
                                        )}
                                    </div>
                                </td>

                                <td>
                                    ${priorityTag(
                                        item.priority
                                    )}
                                </td>

                                <td>
                                    <button
                                        class="compact-button"
                                        onclick='selectInvoice(
                                            ${JSON.stringify(
                                                item.run_id
                                            )},
                                            ${JSON.stringify(
                                                item.invoice_number
                                            )}
                                        )'
                                    >
                                        Review
                                    </button>
                                </td>
                            </tr>
                        `
                    ).join("")}
                </tbody>
            </table>
        `
        : `
            <div class="empty-state compact-empty-state">
                No active exceptions match
                the selected filters.
            </div>
        `;
}


async function selectInvoice(
    runId,
    invoiceNumber
) {
    const panel = document.getElementById(
        "invoiceInvestigation"
    );

    if (!panel) {
        alert(
            "The invoice investigation panel was not found."
        );

        return;
    }

    panel.classList.remove(
        "empty-state"
    );

    panel.innerHTML = `
        <div class="status-message">
            Loading invoice controls and evidence...
        </div>
    `;

    try {
        const invoiceUri = (
            `/api/invoices/${
                encodeURIComponent(runId)
            }/${
                encodeURIComponent(
                    invoiceNumber
                )
            }`
        );

        const response = await fetch(
            invoiceUri
        );

        const invoice = await response.json();

        if (!response.ok) {
            throw new Error(
                invoice.error
                || "Invoice could not be loaded."
            );
        }

        selectedInvoice = invoice;

        let currentQuery = null;

        /*
        Supplier-query lookup is optional. A missing endpoint
        must never prevent the invoice review from opening.
        */
        try {
            const queryResponse = await fetch(
                `${invoiceUri}/supplier-query`
            );

            if (queryResponse.ok) {
                const queryResult = (
                    await queryResponse.json()
                );

                currentQuery = (
                    queryResult.available
                    ? queryResult.query
                    : null
                );
            }
        }
        catch (queryError) {
            console.warn(
                "Supplier-query lookup unavailable:",
                queryError
            );
        }

        selectedInvoice.current_query = (
            currentQuery
        );

        const actions = (
            invoice.recommended_actions
            || []
        );

        panel.innerHTML = `
            <div class="decision-box">
                <strong>
                    ${escapeHtml(
                        invoice.decision
                    )}
                </strong>

                <p>
                    ${escapeHtml(
                        invoice.decision_reason
                    )}
                </p>
            </div>

            <h2>
                ${escapeHtml(
                    invoice.safe_invoice_alias
                )}
            </h2>

            <div class="invoice-context">
                <div>
                    <span>Processing run</span>

                    <strong>
                        ${escapeHtml(
                            invoice.run_id
                        )}
                    </strong>
                </div>

                <div>
                    <span>Source file</span>

                    <strong>
                        ${escapeHtml(
                            invoice.source_file
                        )}
                    </strong>
                </div>

                <div>
                    <span>Workflow status</span>

                    <strong>
                        ${escapeHtml(
                            invoice.workflow_status
                        )}
                    </strong>
                </div>
            </div>

            <div class="exposure-box">
                <div>
                    <span>Invoice value</span>

                    <strong>
                        ${money(
                            invoice.invoice_value
                        )}
                    </strong>
                </div>

                <div>
                    <span>Estimated exposure</span>

                    <strong>
                        ${money(
                            invoice.estimated_exposure
                        )}
                    </strong>
                </div>

                <div>
                    <span>Exposure percentage</span>

                    <strong>
                        ${Number(
                            invoice.exposure_percentage
                            || 0
                        ).toFixed(2)}%
                    </strong>
                </div>

                <div>
                    <span>Exposure confidence</span>

                    <strong>
                        ${escapeHtml(
                            invoice.exposure_confidence
                            || "UNKNOWN"
                        )}
                    </strong>
                </div>

                <div>
                    <span>Risk level</span>

                    <strong>
                        ${escapeHtml(
                            invoice.risk_level
                        )}
                    </strong>
                </div>

                <div>
                    <span>Reconciliation</span>

                    <strong>
                        ${escapeHtml(
                            invoice.reconciliation_status
                        )}
                    </strong>
                </div>
            </div>

            <h3>Required Actions</h3>

            ${
                actions.length
                ? `
                    <ol>
                        ${actions.map(
                            action => `
                                <li>
                                    ${escapeHtml(action)}
                                </li>
                            `
                        ).join("")}
                    </ol>
                `
                : `
                    <p>
                        No additional actions were recorded.
                    </p>
                `
            }

            <div
                style="
                    display:flex;
                    gap:10px;
                    flex-wrap:wrap;
                    margin-top:18px;
                "
            >
                <button
                    class="primary-button"
                    onclick="generateInvestigationSummary()"
                >
                    Generate Investigation Summary
                </button>

                <button
                    class="compact-button"
                    onclick="openResolution()"
                >
                    Record Resolution
                </button>

                ${
                    invoice.requires_supplier_query
                    && !currentQuery
                    ? `
                        <button
                            class="compact-button"
                            onclick="raiseSupplierQuery()"
                        >
                            Raise Supplier Query
                        </button>
                    `
                    : ""
                }
            </div>

            ${
                currentQuery
                ? `
                    <div class="current-query-banner">
                        <strong>
                            Supplier Query:
                            ${escapeHtml(
                                currentQuery.query_reference
                            )}
                        </strong>

                        <span>
                            ${escapeHtml(
                                currentQuery.query_status
                            )}
                        </span>
                    </div>
                `
                : ""
            }

            <div
                id="investigationSummary"
                class="investigation-summary"
            ></div>
        `;
    }
    catch (error) {
        panel.innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(error.message)}
            </div>
        `;

        console.error(
            "Invoice review failed:",
            error
        );
    }
}


async function generateInvestigationSummary() {
    if (!selectedInvoice) {
        alert("Select an invoice first.");
        return;
    }

    const detailPanel = document.getElementById(
        "invoiceInvestigation"
    );

    let container = document.getElementById(
        "investigationSummary"
    );

    if (!container) {
        container = document.createElement(
            "div"
        );

        container.id = "investigationSummary";

        container.className = (
            "investigation-summary"
        );

        detailPanel.appendChild(container);
    }

    container.scrollIntoView(
        {
            behavior: "smooth",
            block: "start"
        }
    );

    container.innerHTML = `
        <div class="status-message">
            Reviewing invoice controls,
            financial exposure, and supporting evidence...
        </div>
    `;

    try {
        const response = await fetch(
            "/api/investigation-summary",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify(
                    {
                        run_id:
                            selectedInvoice.run_id,
                        invoice_number:
                            selectedInvoice
                            .invoice_number
                    }
                )
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "Investigation summary could not be generated."
            );
        }

        container.innerHTML = `
            <h3>Investigation Summary</h3>

            <div class="decision-box">
                <strong>Root Cause</strong>

                <p>
                    ${escapeHtml(
                        result.root_cause_summary
                    )}
                </p>
            </div>

            <div class="investigation-section">
                <h4>Financial Impact</h4>

                <p>
                    ${escapeHtml(
                        result
                        .financial_impact_summary
                    )}
                </p>
            </div>

            <div class="investigation-section">
                <h4>Control Evidence</h4>

                <p>
                    ${escapeHtml(
                        result
                        .control_evidence_summary
                    )}
                </p>
            </div>

            <div class="investigation-section">
                <h4>Resolution Steps</h4>

                <ol>
                    ${(result.resolution_steps || [])
                        .map(
                            step => `
                                <li>
                                    ${escapeHtml(step)}
                                </li>
                            `
                        ).join("")}
                </ol>
            </div>

            ${
                result.supplier_query_draft
                ? `
                    <div class="investigation-section">
                        <h4>Supplier Query Draft</h4>

                        <div class="query-draft">
                            ${escapeHtml(
                                result
                                .supplier_query_draft
                            )}
                        </div>
                    </div>
                `
                : ""
            }

            ${
                (result.limitations || []).length
                ? `
                    <details>
                        <summary>
                            Assessment limitations
                        </summary>

                        <ul>
                            ${result.limitations.map(
                                item => `
                                    <li>
                                        ${escapeHtml(item)}
                                    </li>
                                `
                            ).join("")}
                        </ul>
                    </details>
                `
                : ""
            }
        `;
    }
    catch (error) {
        container.innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(error.message)}
            </div>
        `;
    }
}


function openResolution() {
    if (!selectedInvoice) {
        return;
    }

    document.getElementById(
        "selectedResolutionInvoice"
    ).textContent = (
        "Selected invoice: "
        + selectedInvoice.safe_invoice_alias
    );

    document.getElementById(
        "workflowStatus"
    ).value = (
        selectedInvoice.workflow_status
        || "NEW"
    );

    document.getElementById(
        "resolutionOwner"
    ).value = (
        selectedInvoice.owner
        || "Invoice Assurance"
    );

    document.getElementById(
        "confirmedRootCause"
    ).value = (
        selectedInvoice
        .confirmed_root_cause
        || ""
    );

    document.getElementById(
        "resolutionNotes"
    ).value = (
        selectedInvoice
        .resolution_notes
        || ""
    );

    openPage("resolutions");
}


async function saveResolution() {
    if (!selectedInvoice) {
        alert(
            "Select an invoice first."
        );

        return;
    }

    const payload = {
        run_id:
            selectedInvoice.run_id,
        invoice_number:
            selectedInvoice.invoice_number,
        workflow_status:
            document.getElementById(
                "workflowStatus"
            ).value,
        owner:
            document.getElementById(
                "resolutionOwner"
            ).value,
        confirmed_root_cause:
            document.getElementById(
                "confirmedRootCause"
            ).value,
        resolution_notes:
            document.getElementById(
                "resolutionNotes"
            ).value
    };

    const response = await fetch(
        "/api/resolution",
        {
            method: "PUT",
            headers: {
                "Content-Type":
                    "application/json"
            },
            body: JSON.stringify(
                payload
            )
        }
    );

    const result = await response.json();

    if (!response.ok) {
        alert(result.error);
        return;
    }

    selectedInvoice = result;

    document.getElementById(
        "resolutionMessage"
    ).innerHTML = `
        <div class="status-message">
            Resolution saved successfully.
        </div>
    `;

    await loadExceptions();
}


async function raiseSupplierQuery() {
    if (!selectedInvoice) {
        return;
    }

    const dueDate = new Date();

    dueDate.setDate(
        dueDate.getDate() + 5
    );

    const response = await fetch(
        "/api/supplier-queries",
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json"
            },
            body: JSON.stringify(
                {
                    run_id:
                        selectedInvoice.run_id,
                    invoice_number:
                        selectedInvoice
                        .invoice_number,
                    owner:
                        "Supplier Query Team",
                    due_date:
                        dueDate
                        .toISOString()
                        .slice(0, 10)
                }
            )
        }
    );

    const result = await response.json();

    if (!response.ok) {
        alert(result.error);
        return;
    }

    alert(
        result.query_reference
        + " was created."
    );

    await loadSupplierQueries();

    openPage("supplier-queries");
}


async function loadSupplierQueries() {
    const response = await fetch(
        "/api/supplier-queries"
    );

    const result = await response.json();

    const queries = result.queries || [];

    document.getElementById(
        "supplierQueryTable"
    ).innerHTML = queries.length
        ? `
            <table>
                <thead>
                    <tr>
                        <th>Reference</th>
                        <th>Invoice</th>
                        <th>Disputed Amount</th>
                        <th>Status</th>
                        <th>Owner</th>
                        <th>Due Date</th>
                        <th>Age</th>
                        <th></th>
                    </tr>
                </thead>

                <tbody>
                    ${queries.map(
                        item => `
                            <tr>
                                <td>
                                    ${escapeHtml(
                                        item.query_reference
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.safe_invoice_alias
                                    )}
                                </td>

                                <td>
                                    ${money(
                                        item.disputed_amount
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.query_status
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.owner
                                    )}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.due_date
                                    )}

                                    ${
                                        item.overdue
                                        ? `
                                            <div class="overdue-label">
                                                ${item.overdue_days}
                                                days overdue
                                            </div>
                                        `
                                        : ""
                                    }
                                </td>

                                <td>
                                    ${item.age_days} days
                                </td>

                                <td>
                                    <button
                                        class="compact-button"
                                        onclick='editSupplierQuery(
                                            ${JSON.stringify(
                                                item
                                            )}
                                        )'
                                    >
                                        Update
                                    </button>
                                </td>
                            </tr>
                        `
                    ).join("")}
                </tbody>
            </table>
        `
        : "<p>No supplier queries are available.</p>";
}


function editSupplierQuery(item) {
    selectedSupplierQuery = item;

    document.getElementById(
        "queryStatus"
    ).value = item.query_status;

    document.getElementById(
        "supplierResponse"
    ).value = (
        item.supplier_response || ""
    );

    document.getElementById(
        "queryResolution"
    ).value = (
        item.final_resolution || ""
    );

    document.getElementById(
        "recoveredValue"
    ).value = (
        item.recovered_value || 0
    );

    document.getElementById(
        "supplierQueryEditor"
    ).classList.remove(
        "hidden"
    );
}


async function saveSupplierQuery() {
    if (!selectedSupplierQuery) {
        return;
    }

    const response = await fetch(
        `/api/supplier-queries/${
            selectedSupplierQuery.query_id
        }`,
        {
            method: "PUT",
            headers: {
                "Content-Type":
                    "application/json"
            },
            body: JSON.stringify(
                {
                    query_status:
                        document.getElementById(
                            "queryStatus"
                        ).value,
                    supplier_response:
                        document.getElementById(
                            "supplierResponse"
                        ).value,
                    final_resolution:
                        document.getElementById(
                            "queryResolution"
                        ).value,
                    recovered_value:
                        document.getElementById(
                            "recoveredValue"
                        ).value
                }
            )
        }
    );

    const result = await response.json();

    if (!response.ok) {
        alert(result.error);
        return;
    }

    selectedSupplierQuery = result;

    alert("Supplier query updated.");

    await loadSupplierQueries();
}


async function loadReports() {
    const response = await fetch(
        "/api/reports"
    );

    const result = await response.json();

    const reports = [
        [
            "Invoices Assured",
            result.invoice_count
        ],
        [
            "Cleared Invoices",
            result.cleared_count
        ],
        [
            "Open Exceptions",
            result.exception_count
        ],
        [
            "Financial Exposure",
            money(result.total_exposure)
        ],
        [
            "Open Supplier Queries",
            result.open_queries
        ],
        [
            "Recovered Value",
            money(result.recovered_value)
        ]
    ];

    document.getElementById(
        "reportMetrics"
    ).innerHTML = reports.map(
        item => `
            <div class="report-card">
                <span>
                    ${escapeHtml(item[0])}
                </span>

                <strong>
                    ${escapeHtml(
                        String(item[1])
                    )}
                </strong>
            </div>
        `
    ).join("");
}


async function loadHealth() {
    const response = await fetch(
        "/health"
    );

    const result = await response.json();

    document.getElementById(
        "serviceHealth"
    ).innerHTML = `
        <div class="status-message">
            ${escapeHtml(
                result.application
            )}
            is ${escapeHtml(
                result.status
            )}.
        </div>
    `;
}


loadLatest();
loadRuns();
loadExceptions();

async function processSelectedFile() {
    const input = document.getElementById(
        "billingFile"
    );

    const button = document.getElementById(
        "processFileButton"
    );

    const message = document.getElementById(
        "fileProcessingMessage"
    );

    const files = Array.from(
        input.files || []
    );

    if (!files.length) {
        message.innerHTML = `
            <div class="error-message visible-message">
                Select one or more .uff billing files
                or synthetic .txt demonstration files.
            </div>
        `;

        return;
    }

    button.disabled = true;

    const outcomes = [];

    for (
        let index = 0;
        index < files.length;
        index += 1
    ) {
        const file = files[index];

        button.textContent = (
            `Processing ${index + 1} `
            + `of ${files.length}`
        );

        message.innerHTML = `
            <div class="status-message">
                Processing
                ${escapeHtml(file.name)}...
            </div>
        `;

        try {
            const response = await fetch(
                "/api/process-file",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/octet-stream",
                        "X-File-Name":
                            file.name
                    },
                    body: file
                }
            );

            const result = await response.json();

            if (!response.ok) {
                const errorMessage = String(
                    result.error
                    || "Processing failed."
                );

                const duplicate = (
                    errorMessage.includes(
                        "already been registered"
                    )
                );

                outcomes.push(
                    {
                        fileName: file.name,
                        status: (
                            duplicate
                            ? "DUPLICATE"
                            : "FAILED"
                        ),
                        invoices: 0,
                        exceptions: 0,
                        details: errorMessage
                    }
                );

                continue;
            }

            outcomes.push(
                {
                    fileName: file.name,
                    status: "COMPLETED",
                    invoices: Number(
                        result.summary
                        .total_invoices
                        || 0
                    ),
                    exceptions: Number(
                        result.summary
                        .exceptions
                        || 0
                    ),
                    details: (
                        result.summary.run_id
                    )
                }
            );

            renderSummary(
                result.summary
            );
        }
        catch (error) {
            outcomes.push(
                {
                    fileName: file.name,
                    status: "FAILED",
                    invoices: 0,
                    exceptions: 0,
                    details: error.message
                }
            );
        }
    }

    const completed = outcomes.filter(
        item => item.status
        === "COMPLETED"
    ).length;

    const duplicates = outcomes.filter(
        item => item.status
        === "DUPLICATE"
    ).length;

    const failed = outcomes.filter(
        item => item.status
        === "FAILED"
    ).length;

    const totalInvoices = outcomes.reduce(
        (total, item) => (
            total
            + Number(
                item.invoices || 0
            )
        ),
        0
    );

    const totalExceptions = outcomes.reduce(
        (total, item) => (
            total
            + Number(
                item.exceptions || 0
            )
        ),
        0
    );

    message.innerHTML = `
        <div class="batch-outcome">
            <h3>File Intake Result</h3>

            <div class="batch-outcome-metrics">
                <div>
                    <span>Selected</span>
                    <strong>
                        ${files.length}
                    </strong>
                </div>

                <div>
                    <span>Completed</span>
                    <strong>
                        ${completed}
                    </strong>
                </div>

                <div>
                    <span>Duplicates</span>
                    <strong>
                        ${duplicates}
                    </strong>
                </div>

                <div>
                    <span>Failed</span>
                    <strong>
                        ${failed}
                    </strong>
                </div>

                <div>
                    <span>Invoices</span>
                    <strong>
                        ${totalInvoices}
                    </strong>
                </div>

                <div>
                    <span>Exceptions</span>
                    <strong>
                        ${totalExceptions}
                    </strong>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Status</th>
                        <th>Invoices</th>
                        <th>Exceptions</th>
                        <th>Details</th>
                    </tr>
                </thead>

                <tbody>
                    ${outcomes.map(
                        item => `
                            <tr>
                                <td>
                                    ${escapeHtml(
                                        item.fileName
                                    )}
                                </td>

                                <td>
                                    <span class="file-status file-status-${
                                        item.status.toLowerCase()
                                    }">
                                        ${escapeHtml(
                                            item.status
                                        )}
                                    </span>
                                </td>

                                <td>
                                    ${item.invoices}
                                </td>

                                <td>
                                    ${item.exceptions}
                                </td>

                                <td>
                                    ${escapeHtml(
                                        item.details
                                    )}
                                </td>
                            </tr>
                        `
                    ).join("")}
                </tbody>
            </table>
        </div>
    `;

    input.value = "";

    await Promise.all(
        [
            loadRuns(),
            loadExceptions(),
            loadRegisteredFiles(),
            loadDailyIntakeSummary()
        ]
    );

    button.disabled = false;

    button.textContent = (
        "Process Selected Files"
    );
}


async function loadRegisteredFiles() {
    const container = document.getElementById(
        "registeredFileTable"
    );

    if (!container) {
        return;
    }

    try {
        const response = await fetch(
            "/api/registered-files"
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "File history could not be loaded."
            );
        }

        const files = result.files || [];

        container.innerHTML = files.length
            ? `
                <table>
                    <thead>
                        <tr>
                            <th>File</th>
                            <th>Received</th>
                            <th>Records</th>
                            <th>Invoices</th>
                            <th>Status</th>
                            <th>Processing Run</th>
                        </tr>
                    </thead>

                    <tbody>
                        ${files.map(
                            item => `
                                <tr>
                                    <td>
                                        ${escapeHtml(
                                            item.file_name
                                        )}
                                    </td>

                                    <td>
                                        ${escapeHtml(
                                            item.received_at
                                        )}
                                    </td>

                                    <td>
                                        ${item.record_count}
                                    </td>

                                    <td>
                                        ${item.invoice_count}
                                    </td>

                                    <td>
                                        <span class="file-status file-status-${
                                            String(
                                                item.processing_status
                                            ).toLowerCase()
                                        }">
                                            ${escapeHtml(
                                                item.processing_status
                                            )}
                                        </span>
                                    </td>

                                    <td>
                                        ${escapeHtml(
                                            item.processing_run_id
                                            || ""
                                        )}
                                    </td>
                                </tr>
                            `
                        ).join("")}
                    </tbody>
                </table>
            `
            : `
                <p>
                    No billing files have been registered.
                </p>
            `;
    }
    catch (error) {
        container.innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(error.message)}
            </div>
        `;
    }
}


async function loadDailyIntakeSummary() {
    const container = document.getElementById(
        "dailyIntakeSummary"
    );

    if (!container) {
        return;
    }

    try {
        const dateInput = document.getElementById(
            "intakeDate"
        );

        const selectedDate = (
            dateInput
            ? dateInput.value
            : ""
        );

        const endpoint = selectedDate
            ? (
                "/api/daily-intake-summary?run_date="
                + encodeURIComponent(
                    selectedDate
                )
            )
            : "/api/daily-intake-summary";

        const response = await fetch(
            endpoint
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "Daily intake could not be loaded."
            );
        }

        container.innerHTML = `
            <div class="intake-metric">
                <span>Files Received</span>
                <strong>
                    ${result.files_received || 0}
                </strong>
            </div>

            <div class="intake-metric">
                <span>Completed</span>
                <strong>
                    ${result.files_completed || 0}
                </strong>
            </div>

            <div class="intake-metric">
                <span>Failed</span>
                <strong>
                    ${result.files_failed || 0}
                </strong>
            </div>

            <div class="intake-metric">
                <span>Processing</span>
                <strong>
                    ${result.files_processing || 0}
                </strong>
            </div>

            <div class="intake-metric">
                <span>Invoices</span>
                <strong>
                    ${result.invoices_registered || 0}
                </strong>
            </div>

            <div class="intake-metric">
                <span>Records</span>
                <strong>
                    ${result.records_received || 0}
                </strong>
            </div>
        `;
    }
    catch (error) {
        container.innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(error.message)}
            </div>
        `;
    }
}


/*
Load operational information whenever Administration is opened.
*/
const administrationTab = document.querySelector(
    '[data-page="administration"]'
);

if (administrationTab) {
    administrationTab.addEventListener(
        "click",
        () => {
            const intakeDate = document.getElementById(
                "intakeDate"
            );

            if (
                intakeDate
                && !intakeDate.value
            ) {
                const now = new Date();

                const localDate = new Date(
                    now.getTime()
                    - now.getTimezoneOffset()
                    * 60000
                )
                    .toISOString()
                    .slice(0, 10);

                intakeDate.value = localDate;
            }

            loadRegisteredFiles();
            loadDailyIntakeSummary();
            loadProcessingRecovery();

            if (
                typeof loadHealth
                === "function"
            ) {
                loadHealth();
            }
        }
    );
}


async function loadProcessingRecovery() {
    const summary = document.getElementById(
        "processingRecoverySummary"
    );

    const table = document.getElementById(
        "processingRecoveryTable"
    );

    const refreshButton = document.getElementById(
        "refreshRecoveryButton"
    );

    if (!summary || !table) {
        return;
    }

    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.textContent = "Checking...";
    }

    summary.innerHTML = `
        <div class="status-message">
            Checking for failed and stale processing records...
        </div>
    `;

    try {
        const response = await fetch(
            "/api/processing-recovery"
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "Recovery records could not be loaded."
            );
        }

        const records = result.records || [];

        const failedCount = records.filter(
            item => item.processing_status
            === "FAILED"
        ).length;

        const staleCount = records.filter(
            item => item.processing_status
            === "RECOVERY REQUIRED"
        ).length;

        summary.innerHTML = `
            <div class="recovery-metric">
                <span>Recovery Records</span>
                <strong>${records.length}</strong>
            </div>

            <div class="recovery-metric">
                <span>Failed</span>
                <strong>${failedCount}</strong>
            </div>

            <div class="recovery-metric">
                <span>Stale</span>
                <strong>${staleCount}</strong>
            </div>

            <div class="recovery-metric">
                <span>Newly Marked Stale</span>
                <strong>
                    ${result.stale_records_marked || 0}
                </strong>
            </div>
        `;

        table.innerHTML = records.length
            ? `
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Status</th>
                                <th>Stage</th>
                                <th>Failure Code</th>
                                <th>Last Activity</th>
                                <th>Retries</th>
                                <th>Reason</th>
                                <th></th>
                            </tr>
                        </thead>

                        <tbody>
                            ${records.map(
                                item => `
                                    <tr>
                                        <td>
                                            <strong>
                                                ${escapeHtml(
                                                    item.file_name
                                                )}
                                            </strong>

                                            <div class="queue-secondary">
                                                Registry #${item.registry_id}
                                            </div>
                                        </td>

                                        <td>
                                            <span class="file-status file-status-${
                                                String(
                                                    item.processing_status
                                                )
                                                    .toLowerCase()
                                                    .replaceAll(
                                                        " ",
                                                        "-"
                                                    )
                                            }">
                                                ${escapeHtml(
                                                    item.processing_status
                                                )}
                                            </span>
                                        </td>

                                        <td>
                                            ${escapeHtml(
                                                item.processing_stage
                                                || "UNKNOWN"
                                            )}
                                        </td>

                                        <td>
                                            <code>
                                                ${escapeHtml(
                                                    item.failure_code
                                                    || "NOT RECORDED"
                                                )}
                                            </code>
                                        </td>

                                        <td>
                                            ${escapeHtml(
                                                item.last_activity_at
                                                || item.received_at
                                                || ""
                                            )}
                                        </td>

                                        <td>
                                            ${Number(
                                                item.retry_count || 0
                                            )}
                                        </td>

                                        <td class="recovery-reason">
                                            ${escapeHtml(
                                                item.failure_reason
                                                || ""
                                            )}
                                        </td>

                                        <td>
                                            <button
                                                class="compact-button"
                                                onclick="authorizeProcessingRetry(
                                                    ${Number(
                                                        item.registry_id
                                                    )}
                                                )"
                                            >
                                                Authorize Retry
                                            </button>
                                        </td>
                                    </tr>
                                `
                            ).join("")}
                        </tbody>
                    </table>
                </div>
            `
            : `
                <div class="empty-state compact-empty-state">
                    No failed or stale processing records.
                </div>
            `;
    }
    catch (error) {
        summary.innerHTML = "";

        table.innerHTML = `
            <div class="error-message visible-message">
                ${escapeHtml(error.message)}
            </div>
        `;
    }
    finally {
        if (refreshButton) {
            refreshButton.disabled = false;
            refreshButton.textContent = (
                "Refresh Recovery Queue"
            );
        }
    }
}


async function authorizeProcessingRetry(
    registryId
) {
    const confirmed = window.confirm(
        "Authorize retry for this file record? "
        + "The original billing file must be "
        + "selected and uploaded again."
    );

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(
            `/api/processing-recovery/${
                encodeURIComponent(registryId)
            }/authorize`,
            {
                method: "POST"
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.error
                || "Retry could not be authorized."
            );
        }

        window.alert(
            "Retry authorized. Select the original "
            + "billing file in Register Daily Billing "
            + "Files and process it again."
        );

        await Promise.all(
            [
                loadProcessingRecovery(),
                loadRegisteredFiles()
            ]
        );
    }
    catch (error) {
        window.alert(
            error.message
        );
    }
}

AI-Powered D2021 Invoice Validation and Reconciliation Platform
An end-to-end Finance Operations and Applied AI platform for processing D2021 electricity billing files, validating invoice data, reconciling charges, identifying unusual billing patterns, scoring financial risk, managing exceptions, and preserving a complete audit trail.

The platform combines deterministic business controls, financial reconciliation, machine-learning anomaly detection, semantic business-rule retrieval, grounded AI explanations, human review, supplier-query management, processing recovery, transactional persistence, operational monitoring, Docker packaging, and continuous integration.

Data notice: All demonstration data in this repository is synthetic. The project does not contain confidential client files, real MPANs, customer information, production credentials, or proprietary database objects.

Release Summary
Item	Value
Release	v1.0.0
Runtime	Python 3.13
Operational web framework	Starlette
ASGI server	Uvicorn
Analytical interface	Streamlit
Browser interface	HTML, CSS, JavaScript
Local persistence	SQLite
Automated tests	96
Formally benchmarked volume	1,000 invoices
Expected maximum file volume	2,500 invoices
Container packaging	Docker
Continuous integration	GitHub Actions
Project Objectives
The platform is designed to help Finance Operations teams:

Process D2021 billing files consistently.
Validate invoice and MPAN information.
Reconcile invoice totals against charge-line values.
Identify unusual rates, quantities, capacities, and invoice values.
Prioritize financially significant exceptions.
Record supplier queries and responses.
Track investigation ownership and resolution.
Calculate estimated financial exposure.
Record recovered values.
Produce audit-ready invoice evidence.
Recover safely from failed or stale file-processing activity.
Monitor application and database health.
Project Highlights
Parses hierarchical D2021 .uff billing files.
Supports ZHV, SDT, CDT, CLO, MPC, BCD, CCD, and ZPT records.
Reconstructs distributor, supplier, site, MPAN, invoice, and charge relationships.
Applies structural, invoice, date, MPAN, financial, and charge validations.
Reconciles BCD invoice totals against associated CCD charge amounts.
Detects unusual invoice patterns using machine-learning and deterministic detectors.
Calculates invoice-level risk scores and business-facing assurance decisions.
Estimates financial exposure and held invoice value.
Retrieves relevant business rules using Gemini embeddings with TF-IDF fallback.
Generates grounded explanations using provider failover and deterministic fallback.
Uses safe invoice aliases for supported external AI processing and evidence file names.
Provides a Finance Operations Dashboard and Exception Workbench.
Supports supplier-query creation, tracking, response, resolution, and recovered value.
Records human review decisions and immutable audit-history events.
Generates downloadable invoice Evidence Packs.
Prevents duplicate processing of completed files.
Tracks processing stages and stage-specific failure codes.
Detects stale processing activity.
Supports controlled retry authorization.
Persists assurance results transactionally.
Verifies persisted invoice counts before completing a processing run.
Exposes liveness, readiness, database integrity, configuration, and operational metrics.
Adds HTTP correlation IDs and structured JSON request logs.
Includes Docker packaging and GitHub Actions CI.
End-to-End Workflow
1. Register Billing File
        |
        v
2. Validate File Structure and Encoding
        |
        v
3. Parse D2021 Records
        |
        v
4. Validate Invoice Data
        |
        v
5. Reconcile BCD and CCD Values
        |
        v
6. Analyse Billing Patterns
        |
        v
7. Calculate Risk Scores
        |
        v
8. Retrieve Applicable Business Rules
        |
        v
9. Generate Grounded Explanation
        |
        v
10. Produce Assurance Decision
        |
        v
11. Persist Run and Invoice Results
        |
        +--> Dashboard and Reporting
        |
        +--> Exception Workbench
        |
        +--> Supplier Query Lifecycle
        |
        +--> Resolution and Closure
        |
        +--> Audit Timeline
        |
        +--> Evidence Pack
        |
        +--> Processing Recovery
D2021 File Structure
The parser understands the following hierarchical structure:

ZHV
 ├── SDT
 ├── CDT
 ├── CLO
 │    └── MPC
 │         └── BCD
 │              └── CCD
 └── ZPT
Supported record types
Record	Purpose
ZHV	File header
SDT	Distributor details
CDT	Customer or supplier details
CLO	Customer location or site
MPC	Metering-point information
BCD	Invoice header and financial totals
CCD	Individual charge details
ZPT	File trailer and record count
The parser reconstructs:

File header
Distributor
Supplier
Customer
Site
MPAN
Invoice
Charge lines
File trailer
Unknown records and structural problems are retained as parser findings rather than silently discarded.

Application Areas
1. Finance Operations Dashboard
The dashboard presents the latest completed assurance run, including:

Total invoices
Total invoice value
Safe-to-progress invoices
Exceptions
Critical exceptions
Held invoice value
Estimated financial exposure
Supplier queries required
Open supplier queries
Recovered value
Processing-run status
2. Daily Billing File Registration
The file-registration workflow:

Accepts supported D2021 files.
Validates the file extension.
Enforces the configured maximum file size.
Detects the file encoding.
Validates required D2021 records.
Checks the ZHV header.
Checks the ZPT trailer.
Verifies the record count.
Calculates a SHA-256 checksum.
Blocks duplicate completed files.
Registers processing history.
Tracks the active processing stage.
Records the final processing-run identifier.
Development mode supports:

.uff
.txt
Production-style mode supports:

.uff
3. Parse and Structure
The parser connects:

CLO -> MPC -> BCD -> CCD
The parsed output includes:

Distributor details
Supplier details
Site information
MPAN information
Invoice headers
Billing periods
Invoice totals
Charge descriptions
Quantities
Rates
Billed amounts
Parser errors
Unknown record types
4. Data Validation
The platform validates:

File name
File extension
File size
Supported encoding
Pipe delimiter
Required record types
Header structure
Trailer structure
Record count
Invoice number
Invoice type
MPAN format
Billing dates
Billing period
Charge-line presence
Invoice net amount
VAT amount
Gross amount
Credit and rebill signs
Charge calculations
Required invoice fields
Required site and MPAN relationships
Validation findings are classified as:

Critical failures
Warnings
Informational findings
The assurance adapter indexes findings by invoice number. This prevents repeatedly scanning the complete validation collection for every invoice.

5. Invoice Reconciliation
The reconciliation engine compares:

BCD final invoice net amount
with:

Sum of associated CCD billed amounts
The result includes:

Reconciliation status
Absolute monetary variance
Percentage variance
Invoice-level evidence
Charge-level evidence
Matched or mismatched classification
An invoice can be financially reconciled and still contain an unusual rate, quantity, capacity, or billing pattern.

6. Pattern and Anomaly Analysis
The platform evaluates features such as:

Invoice value
Billing-period duration
MPAN-level values
Charge quantities
Unit rates
Capacity values
Standing charges
Reactive-power quantities
Invoice-to-median ratios
Charge-to-median ratios
Reconciliation variance
Operational anomaly analysis includes Isolation Forest and deterministic evidence-based checks.

The model-evaluation framework compares:

Isolation Forest
Local Outlier Factor
Robust Z-Score
Extreme Ratio Detector
Weighted Ensemble
Threshold selection uses a labelled synthetic tuning dataset. Final evaluation uses a separate unseen synthetic holdout dataset.

7. Risk Scoring
The final risk score combines three control areas:

Validation risk       Maximum 35
Reconciliation risk   Maximum 35
Anomaly risk          Maximum 30
                      -----------
Final risk score      Maximum 100
Score	Risk level
0 to 24.99	Low
25 to 49.99	Medium
50 to 74.99	High
75 to 100	Critical
The risk result includes:

Final risk score
Risk level
Validation contribution
Reconciliation contribution
Anomaly contribution
Unusual features
Supporting evidence
8. Business-Rule Retrieval
Sanitized business rules are stored in:

knowledge_base/business_rules.json
The retrieval layer supports:

Gemini gemini-embedding-001
TF-IDF fallback
Only approved and sanitized query evidence should be sent to an external embedding provider.

Retrieved results can include:

Rule identifier
Rule title
Relevant rule text
Similarity score
Source citation
9. Grounded AI Explanation
The explanation provider chain supports:

Groq
  |
  v
OpenRouter or OpenAI-compatible provider
  |
  v
Deterministic evidence-based fallback
The explanation can include:

Confirmed anomaly drivers
Invoice value compared with the dataset median
Percentage difference
Invoice percentile
Reconciliation result
Passed controls
Ranked likely causes
Required verification
Recommended actions
Retrieved rule citations
Explanation confidence
Known limitations
External AI providers are optional. The deterministic fallback allows the core workflow to continue when an external provider is unavailable.

10. Assurance Decision
The assurance layer combines validation, reconciliation, anomaly, risk, and rule evidence.

Possible decisions include:

PROGRESS
REVIEW
HOLD
QUERY SUPPLIER
CORRECTION REQUIRED
Each assurance result includes:

Decision
Decision reason
Priority
Exception category
Estimated financial exposure
Exposure percentage
Exposure basis
Exposure confidence
Recommended actions
Supplier-query requirement
Approval-blocking status
Assurance status
11. Exception Workbench
The Exception Workbench provides:

Active assurance exceptions
Priority and risk filters
Invoice details
Validation findings
Reconciliation results
Anomaly evidence
Risk evidence
Assurance decision
Financial exposure
Recommended actions
Investigation summary
Workflow status
Assigned owner
Due date
Confirmed root cause
Resolution notes
Resolved and closed exceptions remain available for reporting and audit but no longer appear in the active operational queue.

12. Supplier Query Lifecycle
Supplier-query records contain:

Query reference
Processing-run identifier
Invoice number
Safe invoice alias
Disputed amount
Issue summary
Supporting evidence
Requested supplier action
Owner
Due date
Query status
Supplier response
Final resolution
Recovered value
Created timestamp
Updated timestamp
Supplier-query actions also update the related invoice workflow status.

13. Audit Timeline
The Audit Timeline combines run-level and invoice-level events in chronological order.

Examples include:

PROCESSING_RUN_COMPLETED
INVOICE_RESOLUTION_UPDATED
SUPPLIER_QUERY_CREATED
SUPPLIER_QUERY_UPDATED
INVESTIGATION_SUMMARY_GENERATED
Each event includes:

Audit identifier
Processing-run identifier
Invoice number when applicable
Event type
Event payload
Event timestamp
Run or invoice scope
14. Evidence Pack
The Evidence Pack creates a downloadable ZIP archive for a selected invoice.

The package can include:

Invoice assurance result
Validation findings
Reconciliation evidence
Risk evidence
Anomaly evidence
Assurance decision
Financial exposure
Recommended actions
Supplier-query information
Audit history
Evidence manifest
Evidence files use safe invoice aliases rather than exposing sensitive source identifiers in file names.

15. Processing Recovery
Administration includes a recovery queue for failed and stale processing records.

Each recovery record displays:

File name
Registry identifier
Processing status
Processing stage
Failure code
Failure reason
Last activity timestamp
Retry count
Recovery-required indicator
Authorizing retry does not retain or automatically reprocess the original source file. The operator must select the original file again.

Processing Stage Tracking
Each registered file moves through these stages:

REGISTERED
PARSING
INVOICE VALIDATION
RECONCILIATION
PATTERN ANALYSIS
RISK SCORING
ASSURANCE
PERSISTENCE
COMPLETED
Stage-specific failure codes include:

PARSING_FAILED
INVOICE_VALIDATION_FAILED
RECONCILIATION_FAILED
PATTERN_ANALYSIS_FAILED
RISK_SCORING_FAILED
ASSURANCE_FAILED
PERSISTENCE_FAILED
STALE_PROCESSING
UNEXPECTED_PROCESSING_FAILURE
The file registry preserves:

Processing stage
Processing status
Failure code
Failure reason
Last activity timestamp
Retry count
Completion timestamp
Processing-run identifier
Transactional Persistence
Assurance persistence uses one SQLite transaction for:

Processing-run insertion
Invoice-result insertion
Persisted invoice-count validation
Completion audit insertion
Transaction commit
If any operation fails, the transaction is rolled back.

Failure-injection tests cover:

Processing-run insertion failure
First invoice insertion failure
Middle invoice insertion failure
Final invoice insertion failure
Completion audit insertion failure
Successful complete persistence
Before writing the completion audit event, the repository verifies:

Persisted invoice count = Expected processing-run invoice count
The integrity diagnostic checks:

Orphan invoice results
Completed runs without results
Run invoice-count mismatches
Duplicate invoices within a run
Orphan supplier queries
Measured Results
Synthetic unseen holdout evaluation
Metric	Result
Best detector	Extreme Ratio Detector
Holdout precision	86.36%
Holdout recall	100.00%
Holdout F1 score	92.68%
Holdout accuracy	99.52%
False negatives	0
These are synthetic evaluation results and must not be interpreted as measured production accuracy.

Automated validation
96 passed
The automated suite covers:

Assurance engine
Adapter performance
Application configuration
Audit Timeline
Frontend audit integration
Closure reporting
Evidence Pack generation
Evidence Pack API
Failed-file retry
Investigation service
Latest exception queue
Operational monitoring
Privacy and schema controls
Processing recovery
Processing-stage tracking
Project smoke tests
Query-state integrity
Review database
Supplier-query lifecycle
Transactional persistence
Performance Benchmark
The formal benchmark exercises the complete runtime pipeline:

Parsing
Validation
Reconciliation
Pattern analysis
Risk scoring
Assurance
Transactional persistence
Registry completion
1,000-invoice benchmark
Measurement	Result
Invoices	1,000
D2021 records	9,004
Input file size	642,743 bytes
Processing duration	7.757 seconds
Throughput	128.908 invoices/second
Peak traced memory	27.254 MB
Persisted invoices	1,000
Distinct invoice numbers	1,000
Duplicate groups	0
Processing runs	1
Registry status	COMPLETED
Registry stage	COMPLETED
Integrity result	PASS
Duration target	PASS
The validation-findings adapter was optimized from a repeated quadratic scan to an indexed invoice lookup.

This reduced the 1,000-invoice duration from approximately:

114.138 seconds
to:

7.757 seconds
This is approximately a 14.7-times improvement.

Benchmark results are machine-specific. See:

performance_results/PERFORMANCE_REPORT.md
Technology Stack
Area	Technology
Programming language	Python 3.13
Operational web framework	Starlette
ASGI application server	Uvicorn
Browser interface	HTML, CSS, JavaScript
Analytical interface	Streamlit
Data processing	pandas, NumPy
Machine learning	scikit-learn
Operational anomaly model	Isolation Forest
Evaluation models	Isolation Forest, Local Outlier Factor, Robust Z-Score, Extreme Ratio Detector, Weighted Ensemble
Semantic retrieval	Gemini embeddings
Retrieval fallback	TF-IDF
AI explanation providers	Groq, OpenRouter, OpenAI-compatible providers
Explanation fallback	Deterministic evidence-based explanation
Local persistence	SQLite
Automated testing	pytest, pytest-asyncio
Monitoring	Health checks, readiness, database integrity, operational metrics
Logging	Structured JSON logs with correlation IDs
Container packaging	Docker
Continuous integration	GitHub Actions
Version control	Git and GitHub
The repository contains both the original Streamlit analytical interface and the current Starlette Finance Operations application.

The release operational interface is served by:

billing_finance_ops_app.py
Project Structure
.
├── assurance/
│   ├── adapters.py
│   ├── evidence_pack_service.py
│   ├── investigation_service.py
│   ├── repository.py
│   ├── service.py
│   └── ...
├── billing_finance_ops_web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── configuration/
│   ├── __init__.py
│   └── settings.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS_RUNBOOK.md
│   ├── UAT_CHECKLIST.md
│   ├── RELEASE_CHECKLIST.md
│   └── decisions/
│       └── database-backend.md
├── knowledge_base/
│   └── business_rules.json
├── monitoring/
│   ├── __init__.py
│   └── operations.py
├── page_code/
│   ├── 2_Parse_and_Structure.py
│   ├── 3_Data_Validation.py
│   ├── 4_Invoice_Reconciliation.py
│   ├── 5_Anomaly_Detection.py
│   ├── 6_Risk_Scoring_AI_Explanation.py
│   ├── 7_RAG_Rule_Retrieval.py
│   ├── 8_Grounded_AI_Explanation.py
│   ├── 9_Human_Review.py
│   ├── 10_Final_Dashboard_Report.py
│   └── 11_Model_Evaluation.py
├── performance/
│   └── benchmark_pipeline.py
├── performance_results/
│   ├── benchmark-summary.csv
│   └── PERFORMANCE_REPORT.md
├── processing/
│   ├── daily_file_service.py
│   ├── recovery_service.py
│   └── ...
├── sample_data/
│   ├── synthetic_d2021_demo.txt
│   ├── synthetic_d2021_demo.txt.example
│   └── SYNTHETIC_SAMPLE_README.md
├── scripts/
│   └── validate_release.py
├── tests/
│   ├── test_adapter_performance.py
│   ├── test_application_configuration.py
│   ├── test_assurance_engine.py
│   ├── test_audit_timeline.py
│   ├── test_audit_timeline_frontend.py
│   ├── test_closure_reporting.py
│   ├── test_evidence_pack.py
│   ├── test_evidence_pack_api.py
│   ├── test_failed_file_retry.py
│   ├── test_investigation_service.py
│   ├── test_latest_exception_queue.py
│   ├── test_operational_monitoring.py
│   ├── test_privacy_and_schema.py
│   ├── test_processing_recovery.py
│   ├── test_processing_stage_tracking.py
│   ├── test_project_smoke.py
│   ├── test_query_state_integrity.py
│   ├── test_review_database.py
│   ├── test_supplier_query_lifecycle.py
│   └── test_transactional_persistence.py
├── .dockerignore
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml
├── Dockerfile
├── app.py
├── billing_finance_ops_app.py
├── deployment.env.example
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── requirements-test.txt
├── review_database.py
├── start_server.py
└── README.md
Installation
1. Create a virtual environment
Using a standard Python installation:

python -m venv .venv

& ".\.venv\Scripts\Activate.ps1"
Using the configured Python 3.13 installation:

& "Q:\Rajkumar\Python313\python.exe" `
    -m virtualenv `
    ".venv"

& ".\.venv\Scripts\Activate.ps1"
If PowerShell blocks activation:

Set-ExecutionPolicy `
    -Scope Process `
    -ExecutionPolicy Bypass
2. Install runtime dependencies
python -m pip install `
    --requirement requirements.txt
3. Install test dependencies
python -m pip install `
    --requirement requirements-test.txt
4. Install development dependencies
python -m pip install `
    --requirement requirements-dev.txt
External AI Provider Configuration
External AI integrations are optional. Core parsing, validation, reconciliation, risk scoring, assurance, persistence, recovery, monitoring, and Evidence Pack generation remain locally controlled.

For Streamlit-based AI features, create:

.streamlit/secrets.toml
Example:

GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"

GROQ_API_KEY = "YOUR_GROQ_API_KEY"
GROQ_CHAT_MODEL = "openai/gpt-oss-20b"

OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY"
OPENROUTER_CHAT_MODEL = "openai/gpt-oss-20b"
Never commit:

.streamlit/secrets.toml
.env
.env.local
.env.production
Running the Finance Operations Application
Development mode
$env:APP_ENV = "development"
$env:DEMO_MODE = "true"

python start_server.py
Open:

http://127.0.0.1:8620
Development mode:

Enables the synthetic scenario
Accepts .uff
Accepts .txt
Uses the configured upload-size limit
Production-style mode
$env:APP_ENV = "production"
$env:DEMO_MODE = "false"
$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "8620"
$env:ALLOWED_FILE_EXTENSIONS = ".uff"
$env:APP_VERSION = "1.0.0"

python start_server.py
Production-style mode:

Disables synthetic processing
Returns HTTP 403 from /api/demo-run
Accepts only .uff
Uses one Uvicorn worker
Exposes database-backed readiness
Running the Streamlit Analytical Interface
The original analytical and model-evaluation pages remain available.

Start Streamlit:

python -m streamlit run app.py
Open:

http://localhost:8501
The Streamlit interface covers parsing, validation, reconciliation, anomaly analysis, risk scoring, RAG retrieval, AI explanation, human review, reporting, and model evaluation.

Runtime Configuration
Variable	Default	Description
APP_ENV	development	development, test, or production
DEMO_MODE	Environment-dependent	Enables synthetic processing
APP_HOST	127.0.0.1	HTTP bind address
APP_PORT	8620	HTTP port
MAX_FILE_SIZE_MB	25	Maximum file size
ALLOWED_FILE_EXTENSIONS	.uff,.txt in demo	Permitted extensions
STALE_PROCESSING_MINUTES	30	Stale-processing threshold
APP_VERSION	1.0.0	Monitoring version
Safe templates:

.env.example
deployment.env.example
Monitoring and Health
Endpoint	Purpose
/health	Basic backward-compatible health check
/health/live	Process liveness
/health/ready	Database-backed readiness
/health/database	SQLite connectivity and integrity
/api/operations/metrics	Processing and request metrics
/api/configuration	Safe runtime configuration
Database health reports:

Query availability
SQLite integrity result
Foreign-key status
Check duration
Overall readiness
Operational metrics include:

Processing runs
Invoice results
Active exceptions
Supplier queries
Open supplier queries
Registered files
Completed files
Failed files
Processing files
Recovery-required files
HTTP request count
HTTP 2xx responses
HTTP 4xx responses
HTTP 5xx responses
Request failures
Average request duration
Every HTTP response includes:

X-Correlation-ID
Request logs are emitted as one-line JSON records containing:

timestamp
application
version
event_type
correlation_id
method
path
status_code
duration_ms
Running Tests
Run the full suite:

python -m pytest -v
Expected:

96 passed
Run the complete release validator:

python scripts/validate_release.py
Expected:

96 passed
Release validation passed.
Validate browser JavaScript:

& "Q:\Rajkumar\nodejs\node-v24.16.0-win-x64\node-v24.16.0-win-x64\node.exe" `
    --check `
    ".\billing_finance_ops_web\app.js"
Synthetic Demonstration Data
The standard synthetic D2021 file contains:

1 ZHV header
1 SDT distributor record
1 CDT supplier record
12 CLO site records
12 MPC records
12 BCD invoice records
72 CCD charge records
1 ZPT trailer
112 total records
One invoice contains an intentionally extreme synthetic reactive-power quantity while remaining financially reconciled.

This demonstrates that an invoice can pass arithmetic reconciliation while still containing a statistically unusual billing pattern.

The benchmark generator creates unique:

Invoice numbers
MPANs
Site references
Customer references
Site names
before running generated files through the complete pipeline.

Docker
Build with Bash
docker build \
  --tag project1-billing-finance:1.0.0 \
  .
Build with PowerShell
docker build `
    --tag project1-billing-finance:1.0.0 `
    .
Create the persistent volume
docker volume create project1-data
Run with Bash
docker run \
  --detach \
  --name project1-billing-finance \
  --publish 8620:8620 \
  --volume project1-data:/app/data \
  --env-file deployment.env \
  --restart unless-stopped \
  project1-billing-finance:1.0.0
Run with PowerShell
docker run `
    --detach `
    --name project1-billing-finance `
    --publish 8620:8620 `
    --volume project1-data:/app/data `
    --env-file deployment.env `
    --restart unless-stopped `
    project1-billing-finance:1.0.0
The container:

Uses Python 3.13 slim
Runs under a non-root user
Exposes port 8620
Uses /app/data as a persistent volume
Includes a readiness health check
Runs one application worker
Continuous Integration
The GitHub Actions workflow performs:

Repository checkout
Python 3.13 setup
Node.js 24 setup
Runtime dependency installation
Test dependency installation
Python compilation
JavaScript syntax validation
Complete pytest execution
Container image build
Container startup
Readiness verification
Production-configuration verification
Verification that the synthetic API returns HTTP 403
Workflow:

.github/workflows/ci.yml
Expected jobs:

Validate application
Build and test container
Privacy and Security Controls
All demonstration data is synthetic.
Safe invoice aliases are used in Evidence Pack file names.
Original billing-file content is not stored in the recovery registry.
API keys and environment files are excluded from Git.
SQLite database files are excluded from Git.
Generated benchmark files are excluded from Git.
Generated billing files are excluded from Git.
Unsupported AI rule citations are removed during local validation.
External AI providers should receive only approved and sanitized evidence.
Human review is required for exception resolution.
No automatic payment approval is performed.
Documentation
Document	Purpose
docs/ARCHITECTURE.md	Architecture and component design
docs/DEPLOYMENT.md	Local and container deployment
docs/OPERATIONS_RUNBOOK.md	Operations, recovery, backup, and troubleshooting
docs/UAT_CHECKLIST.md	User acceptance verification
docs/RELEASE_CHECKLIST.md	Version 1.0.0 release controls
docs/decisions/database-backend.md	SQLite and PostgreSQL decision
performance_results/PERFORMANCE_REPORT.md	Processing benchmark

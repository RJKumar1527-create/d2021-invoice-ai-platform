# AI Invoice Reconciliation & Anomaly Detection Platform

An end-to-end Applied AI platform for parsing, validating, reconciling, analysing, and reviewing synthetic D2021 electricity invoice files.

The platform combines deterministic business rules, financial reconciliation, anomaly detection, semantic rule retrieval, grounded LLM explanations, provider failover, human review, persistent audit history, reporting, and unseen holdout evaluation.

> ** project:** All demonstration data is synthetic. No client code, production files, real MPANs, customer information, addresses, credentials, or proprietary database objects are included.

## Project Highlights

- Parses hierarchical D2021 `.uff` files containing `ZHV`, `SDT`, `CDT`, `CLO`, `MPC`, `BCD`, `CCD`, and `ZPT` records.
- Reconstructs sites, MPAN relationships, invoices, and charge lines.
- Applies structural, invoice, date, MPAN, financial, and charge validations.
- Reconciles the BCD invoice net amount against associated CCD charge totals.
- Detects statistically unusual invoice patterns using multiple anomaly detectors.
- Retrieves relevant business rules using Gemini embeddings with TF-IDF fallback.
- Generates grounded root-cause explanations using Groq, then OpenRouter, then deterministic fallback.
- Masks invoice identifiers before external AI calls.
- Records human decisions, risk overrides, ownership, comments, and immutable audit history in SQLite.
- Produces portfolio-safe CSV and ZIP reports using synthetic invoice aliases.
- Evaluates anomaly models using disjoint threshold-tuning and unseen holdout datasets.

## Measured Results

Results from the labelled synthetic unseen holdout evaluation:

| Metric | Result |
|---|---:|
| Best detector | Extreme Ratio Detector |
| Holdout precision | 86.36% |
| Holdout recall | 100.00% |
| Holdout F1 score | 92.68% |
| Holdout accuracy | 99.52% |
| False negatives | 0 |

Automated test result:

```text
14 passed in 9.41 seconds
```

These are synthetic evaluation results and must not be interpreted as production accuracy.

## End-to-End Workflow

```text
1. File Upload
        ↓
2. Parse & Structure
        ↓
3. Data Validation
        ↓
4. Invoice Reconciliation
        ↓
5. ML Anomaly Detection
        ↓
6. Risk Scoring
        ↓
7. Gemini Vector Rule Retrieval
        ↓
8. Grounded AI Explanation
   Groq → OpenRouter → deterministic fallback
        ↓
9. Human Review & Audit History
        ↓
10. Final Dashboard & Reports
        ↓
11. Unseen Holdout Model Evaluation
```

## Application Pages

### 1. File Upload

- Accepts `.uff` files.
- Checks file size, encoding, delimiter, naming convention, required records, ZHV header, and ZPT trailer.
- Uses SHA-256 to detect duplicate uploads during the active session.
- Masks long numeric identifiers in file previews.

### 2. Parse & Structure

- Parses hierarchical D2021 records.
- Connects `CLO → MPC → BCD → CCD` relationships.
- Displays distributor, supplier, site, MPAN, invoice, and charge summaries.
- Captures unknown records and structural parsing errors.

### 3. Data Validation

- Validates invoice numbers, invoice types, MPAN format, billing dates, charge presence, financial totals, credit/rebill signs, and charge calculations.
- Separates critical failures from preliminary warnings.

### 4. Invoice Reconciliation

- Compares BCD final net values with the sum of associated CCD billed amounts.
- Calculates monetary and percentage variance.
- Produces invoice-level and charge-level reconciliation reports.

### 5. Anomaly Detection

- Engineers invoice, period, MPAN, quantity, rate, capacity, unit, reactive, and standing-charge features.
- Uses Isolation Forest for operational anomaly scoring.
- Explains unusual features using dataset-relative evidence.

### 6. Risk Scoring

Combines:

```text
Validation risk       Maximum 35
Reconciliation risk   Maximum 35
ML anomaly risk       Maximum 30
                      -----------
Final risk score      Maximum 100
```

Risk levels:

| Score | Risk |
|---:|---|
| 0–24.99 | Low |
| 25–49.99 | Medium |
| 50–74.99 | High |
| 75–100 | Critical |

### 7. RAG Rule Retrieval

- Stores sanitized business rules in `knowledge_base/business_rules.json`.
- Uses Gemini `gemini-embedding-001` for semantic retrieval.
- Sends only sanitized query evidence to the embedding API.
- Falls back to TF-IDF if Gemini is unavailable.

### 8. Grounded AI Explanation

Provider chain:

```text
Groq
  ↓ failure
OpenRouter
  ↓ failure
Deterministic evidence-based fallback
```

The explanation includes:

- Confirmed anomaly drivers
- Invoice value vs dataset median
- Percentile and percentage difference
- Passed controls
- Ranked likely causes
- Verification required
- Recommended actions
- Rule citations
- Estimated confidence
- Limitations

### 9. Human Review

- Reviewer and owner assignment
- Decision and workflow status
- AI explanation assessment
- Risk override
- False-positive classification
- Due date, comments, evidence, and resolution notes
- Persistent SQLite storage
- Immutable audit-history records

### 10. Final Dashboard & Reports

- Processing, validation, reconciliation, anomaly, risk, RAG, AI, and review summaries
- Effective post-review risk
- Priority-review queue
- Portfolio-safe masked aliases
- Consolidated CSV and complete ZIP package

### 11. Model Evaluation

Compares:

- Isolation Forest
- Local Outlier Factor
- Robust Z-Score
- Extreme Ratio Detector
- Weighted Ensemble

Threshold selection uses a labelled tuning set. Final metrics are calculated on a disjoint unseen synthetic holdout set using the locked threshold.

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.13 |
| User interface | Streamlit |
| Data processing | pandas, NumPy |
| Machine learning | scikit-learn |
| Embeddings | Gemini API |
| LLM generation | Groq and OpenRouter |
| Retrieval fallback | TF-IDF |
| Persistence | SQLite |
| Testing | pytest |
| Version control | Git and GitHub |

## Project Structure

```text
.
├── app.py
├── review_database.py
├── requirements.txt
├── requirements-test.txt
├── pytest.ini
├── TESTING.md
├── knowledge_base/
│   └── business_rules.json
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
├── sample_data/
│   ├── synthetic_d2021_demo.uff.example
│   └── SYNTHETIC_SAMPLE_README.md
└── tests/
    ├── conftest.py
    ├── test_privacy_and_schema.py
    ├── test_project_smoke.py
    └── test_review_database.py
```

## Installation

### 1. Create a virtual environment

```powershell
& "Q:\Rajkumar\Python313\python.exe" -m pip install virtualenv
& "Q:\Rajkumar\Python313\python.exe" -m virtualenv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& ".\.venv\Scripts\Activate.ps1"
```

For a standard Python installation containing `venv`, use:

```powershell
python -m venv .venv
& ".\.venv\Scripts\Activate.ps1"
```

### 2. Install application dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure API keys

Create:

```text
.streamlit/secrets.toml
```

Add:

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"

GROQ_API_KEY = "YOUR_GROQ_API_KEY"
GROQ_CHAT_MODEL = "openai/gpt-oss-20b"

OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY"
OPENROUTER_CHAT_MODEL = "openai/gpt-oss-20b"
```

Never commit `secrets.toml`.

### 4. Prepare the synthetic sample

Copy or rename:

```text
sample_data/synthetic_d2021_demo.uff.example
```

to:

```text
sample_data/synthetic_d2021_demo.uff
```

### 5. Start the application

```powershell
python -m streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

## Running Tests

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -v
```

If pytest is installed only in another Python installation:

```powershell
& "Q:\Rajkumar\Python313\python.exe" -m pytest -v
```

## Synthetic Demonstration Data

The Git-safe sample contains:

- 1 ZHV header
- 1 SDT distributor record
- 1 CDT supplier record
- 12 CLO site sections
- 12 MPC records
- 12 BCD invoices
- 72 CCD charge records
- 1 ZPT trailer

One invoice contains an intentionally extreme synthetic reactive-power quantity while remaining arithmetically reconciled. This demonstrates that an invoice may pass BCD-to-CCD reconciliation while still being statistically anomalous.

## Privacy and Security Controls

- Original invoice identifiers are replaced with aliases such as `INV-00152` before external API calls.
- MPANs, customer names, site names, addresses, and raw D2021 records are excluded from LLM prompts.
- API keys are stored in Streamlit secrets and excluded from Git.
- `.uff`, SQLite, environment, report, and cache files are excluded through `.gitignore`.
- Unsupported LLM rule citations are removed during local validation.
- No automatic production updates or invoice decisions are performed.
- Human review is required for relevant risk findings.

## Important Limitations

- The demonstration data and labelled anomalies are synthetic.
- The current reconciliation confirms BCD-to-CCD arithmetic consistency. Full tariff reconciliation requires approved effective-dated tariffs, source consumption, meter readings, capacity values, and MPAN master data.
- An anomaly indicates statistical unusualness, not fraud or a confirmed billing error.
- LLM confidence is an explanation confidence estimate, not measured production correctness.
- SQLite is suitable for a portfolio prototype. A multi-user production system should use PostgreSQL with authentication and role-based access.
- External APIs must be approved before use with organizational or client data.

## Future Enhancements

- Effective-dated tariff and MPAN master integration
- Deterministic expected-charge calculations
- PostgreSQL persistence
- Authentication and role-based access control
- Background job processing for large files
- Model and prompt monitoring
- Retrieval evaluation with labelled rule queries
- CI pipeline for automated testing
- Deployment using synthetic data only

## Resume-Ready Description

**AI-Powered D2021 Invoice Validation and Reconciliation Platform**

Built an end-to-end Applied AI platform to parse hierarchical D2021 electricity invoice files, validate invoice and MPAN business rules, reconcile BCD and CCD financial values, detect anomalous billing patterns, retrieve relevant rules using Gemini embeddings, and generate grounded root-cause explanations using Groq/OpenRouter with provider failover. Added persistent SQLite human-review workflows, audit history, portfolio-safe reporting, automated tests, and unseen synthetic holdout evaluation achieving 92.68% F1, 86.36% precision, and 100% recall.

## Disclaimer

This repository is an independently developed portfolio prototype. All included demonstration data is synthetic. The project is not a production deployment and does not contain confidential client assets.

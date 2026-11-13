import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "app.py",
    "review_database.py",
    "requirements.txt",
    "knowledge_base/business_rules.json",
    "page_code/2_Parse_and_Structure.py",
    "page_code/3_Data_Validation.py",
    "page_code/4_Invoice_Reconciliation.py",
    "page_code/5_Anomaly_Detection.py",
    "page_code/6_Risk_Scoring_AI_Explanation.py",
    "page_code/7_RAG_Rule_Retrieval.py",
    "page_code/8_Grounded_AI_Explanation.py",
    "page_code/9_Human_Review.py",
    "page_code/10_Final_Dashboard_Report.py",
    "page_code/11_Model_Evaluation.py",
]


def test_required_files_exist():
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    assert not missing, f"Missing project files: {missing}"


def test_all_python_files_compile():
    python_files = [ROOT / "app.py", ROOT / "review_database.py"]
    python_files.extend(sorted((ROOT / "page_code").glob("*.py")))

    for python_file in python_files:
        py_compile.compile(str(python_file), doraise=True)


def test_business_rules_are_valid_and_unique():
    path = ROOT / "knowledge_base" / "business_rules.json"
    rules = json.loads(path.read_text(encoding="utf-8"))

    assert len(rules) >= 10

    rule_ids = [rule["rule_id"] for rule in rules]
    assert len(rule_ids) == len(set(rule_ids)), "Rule IDs must be unique"

    required_fields = {
        "rule_id",
        "category",
        "title",
        "rule_text",
        "recommended_action",
        "source",
    }

    for rule in rules:
        assert required_fields.issubset(rule)
        assert all(str(rule[field]).strip() for field in required_fields)


def test_gitignore_protects_sensitive_artifacts():
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    expected_patterns = [
        ".venv/",
        "__pycache__/",
        "*.uff",
        ".streamlit/",
        "secrets.toml",
        "data/*.db",
        "data/*.db-shm",
        "data/*.db-wal",
    ]

    missing = [pattern for pattern in expected_patterns if pattern not in content]
    assert not missing, f"Missing .gitignore protections: {missing}"


def test_no_secrets_are_tracked_in_source_text():
    forbidden_markers = [
        "PASTE_YOUR_GEMINI_API_KEY_HERE",
        "PASTE_YOUR_GROQ_API_KEY_HERE",
        "PASTE_YOUR_OPENROUTER_API_KEY_HERE",
    ]

    source_files = [ROOT / "app.py", ROOT / "review_database.py"]
    source_files.extend((ROOT / "page_code").glob("*.py"))

    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in source_files
    )

    for marker in forbidden_markers:
        assert marker not in combined

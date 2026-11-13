import subprocess
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_real_uff_files_are_not_present_in_repository():
    uff_files = list(ROOT.rglob("*.uff"))
    assert not uff_files, f"UFF files must not be committed: {uff_files}"


import subprocess


def test_sqlite_databases_are_not_tracked_by_git():
    """SQLite files may exist locally but must not be tracked by Git."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "*.db",
            "*.db-shm",
            "*.db-wal",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    tracked_database_files = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    assert not tracked_database_files, (
        "SQLite database files must not be tracked by Git: "
        f"{tracked_database_files}"
    )


def test_grounded_ai_page_masks_identifiers_before_api_use():
    content = (
        ROOT / "page_code" / "8_Grounded_AI_Explanation.py"
    ).read_text(encoding="utf-8")

    assert "safe_invoice_alias" in content
    assert "numeric_anomaly_evidence" in content
    assert "original invoice" in content.lower()
    assert "base_url=\"https://openrouter.ai/api/v1\"" in content


def test_model_evaluation_is_holdout_based():
    content = (
        ROOT / "page_code" / "11_Model_Evaluation.py"
    ).read_text(encoding="utf-8")

    expected_terms = [
        "tuning",
        "holdout",
        "Locked Threshold",
        "Holdout Precision",
        "Holdout Recall",
        "Holdout F1",
    ]

    for term in expected_terms:
        assert term in content

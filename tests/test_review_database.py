import json
from pathlib import Path

import review_database


def sample_review():
    return {
        "invoice_number": "SYNTH-INV-001",
        "safe_invoice_alias": "INV-00001",
        "reviewer_name": "Test Reviewer",
        "assigned_owner": "Test Owner",
        "decision": "NEEDS INVESTIGATION",
        "review_status": "UNDER REVIEW",
        "due_date": "2026-11-20",
        "ai_assessment": "ACCEPTED",
        "original_risk_level": "MEDIUM",
        "risk_override": "NO OVERRIDE",
        "effective_risk_level": "MEDIUM",
        "reviewer_comments": "Synthetic automated test review.",
        "false_positive_reason": "",
        "resolution_notes": "",
        "supporting_evidence": "Synthetic evidence only.",
        "rule_citations": ["CHG-001", "ML-001"],
        "created_at": "2026-11-14 01:00:00",
        "updated_at": "2026-11-14 01:00:00",
    }


def sample_audit():
    return {
        "audit_timestamp": "2026-11-14 01:00:00",
        "invoice_number": "SYNTH-INV-001",
        "safe_invoice_alias": "INV-00001",
        "reviewer_name": "Test Reviewer",
        "decision": "NEEDS INVESTIGATION",
        "review_status": "UNDER REVIEW",
        "effective_risk_level": "MEDIUM",
        "changed_fields": [
            {
                "field": "review",
                "previous_value": None,
                "new_value": "Review created",
            }
        ],
    }


def configure_temp_database(tmp_path, monkeypatch):
    database_path = tmp_path / "d2021_test_reviews.db"
    monkeypatch.setattr(review_database, "DATABASE_PATH", database_path)
    review_database.initialise_database()
    return database_path


def test_database_is_created(tmp_path, monkeypatch):
    database_path = configure_temp_database(tmp_path, monkeypatch)
    assert database_path.exists()


def test_review_round_trip(tmp_path, monkeypatch):
    configure_temp_database(tmp_path, monkeypatch)
    review_database.save_review(sample_review(), sample_audit())

    saved = review_database.get_review("SYNTH-INV-001")
    assert saved["safe_invoice_alias"] == "INV-00001"
    assert saved["decision"] == "NEEDS INVESTIGATION"
    assert saved["rule_citations"] == ["CHG-001", "ML-001"]


def test_review_update_preserves_created_at(tmp_path, monkeypatch):
    configure_temp_database(tmp_path, monkeypatch)
    first = sample_review()
    review_database.save_review(first, sample_audit())

    updated = sample_review()
    updated["decision"] = "APPROVED"
    updated["review_status"] = "CLOSED"
    updated["updated_at"] = "2026-11-14 02:00:00"

    audit = sample_audit()
    audit["audit_timestamp"] = "2026-11-14 02:00:00"
    audit["decision"] = "APPROVED"
    audit["review_status"] = "CLOSED"
    audit["changed_fields"] = [
        {
            "field": "decision",
            "previous_value": "NEEDS INVESTIGATION",
            "new_value": "APPROVED",
        }
    ]

    review_database.save_review(updated, audit)
    saved = review_database.get_review("SYNTH-INV-001")

    assert saved["decision"] == "APPROVED"
    assert saved["review_status"] == "CLOSED"
    assert saved["created_at"] == "2026-11-14 01:00:00"
    assert saved["updated_at"] == "2026-11-14 02:00:00"


def test_audit_history_is_append_only(tmp_path, monkeypatch):
    configure_temp_database(tmp_path, monkeypatch)
    review_database.save_review(sample_review(), sample_audit())

    second_audit = sample_audit()
    second_audit["audit_timestamp"] = "2026-11-14 02:00:00"
    second_audit["changed_fields"] = [
        {
            "field": "review_status",
            "previous_value": "UNDER REVIEW",
            "new_value": "CLOSED",
        }
    ]
    updated = sample_review()
    updated["review_status"] = "CLOSED"
    updated["updated_at"] = "2026-11-14 02:00:00"
    review_database.save_review(updated, second_audit)

    history = review_database.get_audit_history("SYNTH-INV-001")
    assert len(history) == 2
    assert history[1]["changed_fields"][0]["field"] == "review_status"


def test_summary_counts(tmp_path, monkeypatch):
    configure_temp_database(tmp_path, monkeypatch)
    review_database.save_review(sample_review(), sample_audit())

    summary = review_database.get_review_summary()
    assert summary["total_reviews"] == 1
    assert summary["needs_investigation"] == 1
    assert summary["approved"] == 0

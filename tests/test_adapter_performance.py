import assurance.adapters as adapters


def validation_record(
    index,
):
    return {
        "invoice_number": (
            f"PERF-{index:05d}"
        ),
        "findings": [
            {
                "severity": "WARNING",
                "message": (
                    f"Finding {index}"
                ),
            }
        ],
    }


def test_validation_lookup_is_indexed_once(
    monkeypatch,
):
    records = [
        validation_record(index)
        for index in range(
            1,
            501,
        )
    ]

    original = (
        adapters
        .normalize_invoice_reference
    )

    call_count = 0

    def counted_normalization(
        record,
    ):
        nonlocal call_count

        call_count += 1

        return original(
            record
        )

    monkeypatch.setattr(
        adapters,
        "normalize_invoice_reference",
        counted_normalization,
    )

    lookup, global_findings = (
        adapters
        .create_validation_findings_lookup(
            records
        )
    )

    assert len(lookup) == 500
    assert global_findings == []

    assert (
        lookup["PERF-00250"][0][
            "message"
        ]
        == "Finding 250"
    )

    # Each record is normalized while indexing and once
    # within the existing extraction helper. The important
    # control is linear growth, not 500 x 500 scans.
    assert call_count <= 1000


def test_global_findings_are_preserved():
    records = [
        {
            "message": (
                "Global validation warning"
            ),
            "severity": "WARNING",
        },
        validation_record(1),
    ]

    lookup, global_findings = (
        adapters
        .create_validation_findings_lookup(
            records
        )
    )

    assert len(global_findings) == 1

    assert (
        global_findings[0]["message"]
        == "Global validation warning"
    )

    assert len(
        lookup["PERF-00001"]
    ) == 1
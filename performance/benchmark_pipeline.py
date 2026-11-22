from __future__ import annotations

import argparse
import csv
import gc
import json
import sqlite3
import sys
import time
import tracemalloc

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


import assurance.repository as repository
import processing.daily_file_service as file_service
import processing.recovery_service as recovery


SAMPLE_PATH = (
    PROJECT_ROOT
    / "sample_data"
    / "synthetic_d2021_demo.txt"
)

RESULTS_DIRECTORY = (
    PROJECT_ROOT
    / "performance_results"
)

SUMMARY_PATH = (
    RESULTS_DIRECTORY
    / "benchmark-summary.csv"
)

REPORT_PATH = (
    RESULTS_DIRECTORY
    / "PERFORMANCE_REPORT.md"
)


def split_sample():
    lines = SAMPLE_PATH.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    lines = [
        line
        for line in lines
        if line.strip()
    ]

    header = lines[:3]
    trailer = lines[-1]

    body = lines[3:-1]

    blocks = []
    current = []

    for line in body:
        record_type = line.split(
            "|",
            1,
        )[0]

        if (
            record_type == "CLO"
            and current
        ):
            blocks.append(current)
            current = []

        current.append(line)

    if current:
        blocks.append(current)

    if len(blocks) != 12:
        raise RuntimeError(
            "Expected 12 source invoice blocks, "
            f"found {len(blocks)}."
        )

    for block in blocks:
        record_types = [
            line.split("|", 1)[0]
            for line in block
        ]

        if record_types != [
            "CLO",
            "MPC",
            "BCD",
            "CCD",
            "CCD",
            "CCD",
            "CCD",
            "CCD",
            "CCD",
        ]:
            raise RuntimeError(
                "Unexpected invoice-block structure: "
                f"{record_types}"
            )

    return header, blocks, trailer


def rewrite_invoice_block(
    source_block,
    invoice_index,
):
    block = list(source_block)

    site_reference = (
        f"SYN{invoice_index:09d}"
    )

    invoice_number = (
        f"PERF2026{invoice_index:08d}"
    )

    mpan = (
        9900000000000
        + invoice_index
    )

    clo = block[0].split("|")

    clo[1] = (
        f"PERFORMANCE SITE "
        f"{invoice_index:08d}"
    )

    clo[2] = site_reference

    clo[4] = (
        f"PERFORMANCE CUSTOMER "
        f"{invoice_index:08d}"
    )

    block[0] = "|".join(clo)

    mpc = block[1].split("|")

    mpc[2] = str(mpan)

    block[1] = "|".join(mpc)

    bcd = block[2].split("|")

    bcd[4] = invoice_number

    block[2] = "|".join(bcd)

    return block


def generate_file(
    invoice_count,
):
    header, blocks, trailer = (
        split_sample()
    )

    generated = list(header)

    for index in range(
        1,
        invoice_count + 1,
    ):
        source_block = blocks[
            (index - 1)
            % len(blocks)
        ]

        generated.extend(
            rewrite_invoice_block(
                source_block,
                index,
            )
        )

    record_count = (
        len(generated)
        + 1
    )

    trailer_fields = trailer.split("|")

    if len(trailer_fields) > 2:
        trailer_fields[2] = str(
            record_count
        )

    generated.append(
        "|".join(trailer_fields)
    )

    content = (
        "\n".join(generated)
        + "\n"
    )

    return content.encode(
        "utf-8-sig"
    )


def configure_databases(
    invoice_count,
):
    registry_path = (
        RESULTS_DIRECTORY
        / f"registry-{invoice_count}.db"
    )

    assurance_path = (
        RESULTS_DIRECTORY
        / f"assurance-{invoice_count}.db"
    )

    for path in [
        registry_path,
        assurance_path,
    ]:
        path.unlink(
            missing_ok=True
        )

    file_service.REGISTRY_PATH = (
        registry_path
    )

    repository.DATABASE_PATH = (
        assurance_path
    )

    recovery.initialise_recovery_schema()
    repository.initialise_repository()

    return registry_path, assurance_path


def database_checks(
    assurance_path,
    run_id,
):
    connection = sqlite3.connect(
        assurance_path
    )

    try:
        persisted = connection.execute(
            """
            SELECT COUNT(*)
            FROM invoice_assurance_results
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        distinct_invoices = connection.execute(
            """
            SELECT COUNT(
                DISTINCT invoice_number
            )
            FROM invoice_assurance_results
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        duplicate_groups = connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT invoice_number
                FROM invoice_assurance_results
                WHERE run_id = ?
                GROUP BY invoice_number
                HAVING COUNT(*) > 1
            )
            """,
            (run_id,),
        ).fetchone()[0]

        processing_runs = connection.execute(
            """
            SELECT COUNT(*)
            FROM processing_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

    finally:
        connection.close()

    return {
        "persisted_invoices": persisted,
        "distinct_invoices": (
            distinct_invoices
        ),
        "duplicate_groups": (
            duplicate_groups
        ),
        "processing_runs": (
            processing_runs
        ),
    }


def run_benchmark(
    invoice_count,
):
    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry_path, assurance_path = (
        configure_databases(
            invoice_count
        )
    )

    file_bytes = generate_file(
        invoice_count
    )

    generated_path = (
        RESULTS_DIRECTORY
        / (
            "generated-"
            f"{invoice_count}.txt"
        )
    )

    generated_path.write_bytes(
        file_bytes
    )

    gc.collect()

    tracemalloc.start()

    started = time.perf_counter()

    result = (
        file_service
        .process_runtime_file(
            file_name=(
                "performance-"
                f"{invoice_count}.txt"
            ),
            file_bytes=file_bytes,
        )
    )

    duration_seconds = (
        time.perf_counter()
        - started
    )

    current_memory, peak_memory = (
        tracemalloc.get_traced_memory()
    )

    tracemalloc.stop()

    summary = result["summary"]

    run_id = summary["run_id"]

    checks = database_checks(
        assurance_path,
        run_id,
    )

    registry_records = (
        file_service
        .list_registered_files()
    )

    registry_record = (
        registry_records[0]
    )

    throughput = (
        invoice_count
        / duration_seconds
        if duration_seconds
        else 0
    )

    benchmark_result = {
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "invoice_count": (
            invoice_count
        ),
        "record_count": (
            registry_record[
                "record_count"
            ]
        ),
        "file_size_bytes": len(
            file_bytes
        ),
        "duration_seconds": round(
            duration_seconds,
            3,
        ),
        "throughput_invoices_per_second": round(
            throughput,
            3,
        ),
        "peak_memory_mb": round(
            peak_memory
            / 1024
            / 1024,
            3,
        ),
        "run_id": run_id,
        "run_status": summary.get(
            "run_status",
            "",
        ),
        "exceptions": summary.get(
            "exceptions",
            0,
        ),
        "persisted_invoices": checks[
            "persisted_invoices"
        ],
        "distinct_invoices": checks[
            "distinct_invoices"
        ],
        "duplicate_groups": checks[
            "duplicate_groups"
        ],
        "processing_runs": checks[
            "processing_runs"
        ],
        "registry_status": (
            registry_record[
                "processing_status"
            ]
        ),
        "registry_stage": (
            registry_record[
                "processing_stage"
            ]
        ),
    }

    expected = invoice_count

    integrity_passed = (
        checks[
            "persisted_invoices"
        ]
        == expected
        and checks[
            "distinct_invoices"
        ]
        == expected
        and checks[
            "duplicate_groups"
        ]
        == 0
        and checks[
            "processing_runs"
        ]
        == 1
        and registry_record[
            "processing_status"
        ]
        == "COMPLETED"
        and registry_record[
            "processing_stage"
        ]
        == "COMPLETED"
    )

    benchmark_result[
        "integrity_passed"
    ] = integrity_passed

    duration_target_seconds = {
        1000: 60,
        2500: 120,
    }.get(invoice_count)

    benchmark_result[
        "duration_target_seconds"
    ] = duration_target_seconds

    benchmark_result[
        "duration_target_passed"
    ] = (
        duration_target_seconds is None
        or duration_seconds
        <= duration_target_seconds
    )

    if not integrity_passed:
        raise RuntimeError(
            "Benchmark persistence verification "
            f"failed: {benchmark_result}"
        )

    result_path = (
        RESULTS_DIRECTORY
        / (
            "benchmark-"
            f"{invoice_count}.json"
        )
    )

    result_path.write_text(
        json.dumps(
            benchmark_result,
            indent=2,
        ),
        encoding="utf-8",
    )

    return benchmark_result


def write_summary(
    results,
):
    columns = [
        "generated_at_utc",
        "invoice_count",
        "record_count",
        "file_size_bytes",
        "duration_seconds",
        "throughput_invoices_per_second",
        "peak_memory_mb",
        "run_status",
        "exceptions",
        "persisted_invoices",
        "distinct_invoices",
        "duplicate_groups",
        "processing_runs",
        "registry_status",
        "registry_stage",
        "integrity_passed",
        "duration_target_seconds",
        "duration_target_passed",
    ]

    with SUMMARY_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(
            results
        )

    report_lines = [
        "# Project 1 Performance Report",
        "",
        (
            "The benchmark exercises the complete "
            "runtime billing-file pipeline using isolated "
            "registry and assurance databases."
        ),
        "",
        "## Results",
        "",
        (
            "| Invoices | Records | File MB | "
            "Duration (s) | Invoices/s | Peak MB | "
            "Persisted | Duplicates | Integrity |"
        ),
        (
            "|---:|---:|---:|---:|---:|---:|"
            "---:|---:|:---:|"
        ),
    ]

    for item in results:
        file_mb = (
            item["file_size_bytes"]
            / 1024
            / 1024
        )

        report_lines.append(
            "| "
            f"{item['invoice_count']:,} | "
            f"{item['record_count']:,} | "
            f"{file_mb:.3f} | "
            f"{item['duration_seconds']:.3f} | "
            f"{item['throughput_invoices_per_second']:.3f} | "
            f"{item['peak_memory_mb']:.3f} | "
            f"{item['persisted_invoices']:,} | "
            f"{item['duplicate_groups']} | "
            f"{'PASS' if item['integrity_passed'] else 'FAIL'} |"
        )

    report_lines.extend(
        [
            "",
            "## Acceptance criteria",
            "",
            "- 1,000 invoices complete within 60 seconds.",
            "- Expected production files contain no more than 2,500 invoices.",
            "- Persisted invoice count equals generated count.",
            "- Distinct invoice count equals generated count.",
            "- No duplicated invoice number within a run.",
            "- Registry status and stage both equal `COMPLETED`.",
            "",
            "## Notes",
            "",
            (
                "- Generated billing files and SQLite "
                "databases are excluded from Git."
            ),
            (
                "- Results are machine-specific and should "
                "be compared only with runs on similar hardware."
            ),
        ]
    )

    REPORT_PATH.write_text(
        "\n".join(
            report_lines
        )
        + "\n",
        encoding="utf-8",
    )


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--volumes",
        nargs="+",
        type=int,
        default=[
            1000,
        ],
    )

    return parser.parse_args()


def main():
    arguments = parse_arguments()

    results = []

    for volume in arguments.volumes:
        print(
            f"Running benchmark: "
            f"{volume:,} invoices"
        )

        result = run_benchmark(
            volume
        )

        results.append(
            result
        )

        print(
            json.dumps(
                result,
                indent=2,
            )
        )

    write_summary(
        results
    )

    print()
    print(
        f"Summary: {SUMMARY_PATH}"
    )

    print(
        f"Report: {REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
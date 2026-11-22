import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from assurance.repository import get_connection


def main():
    with get_connection() as connection:
        awaiting_without_query = connection.execute(
            """
            SELECT
                results.run_id,
                results.invoice_number,
                results.safe_invoice_alias,
                results.workflow_status
            FROM invoice_assurance_results AS results
            LEFT JOIN supplier_queries AS queries
                ON queries.run_id = results.run_id
                AND queries.invoice_number =
                    results.invoice_number
            WHERE
                results.workflow_status =
                    'AWAITING SUPPLIER'
                AND queries.query_id IS NULL
            ORDER BY results.updated_at DESC
            """
        ).fetchall()

        completed_query_open_invoice = connection.execute(
            """
            SELECT
                results.run_id,
                results.invoice_number,
                results.safe_invoice_alias,
                results.workflow_status,
                queries.query_reference,
                queries.query_status
            FROM invoice_assurance_results AS results
            INNER JOIN supplier_queries AS queries
                ON queries.run_id = results.run_id
                AND queries.invoice_number =
                    results.invoice_number
            WHERE
                queries.query_status IN (
                    'RESPONSE ACCEPTED',
                    'RESOLVED',
                    'CLOSED'
                )
                AND results.workflow_status NOT IN (
                    'RESOLVED',
                    'CLOSED'
                )
            ORDER BY queries.updated_at DESC
            """
        ).fetchall()

        duplicate_active_queries = connection.execute(
            """
            SELECT
                run_id,
                invoice_number,
                COUNT(*) AS active_query_count
            FROM supplier_queries
            WHERE query_status IN (
                'OPEN',
                'AWAITING RESPONSE',
                'RESPONSE RECEIVED',
                'CLARIFICATION REQUIRED',
                'RESPONSE REJECTED'
            )
            GROUP BY
                run_id,
                invoice_number
            HAVING COUNT(*) > 1
            """
        ).fetchall()

    checks = [
        (
            "Awaiting supplier without query",
            awaiting_without_query,
        ),
        (
            "Completed query with open invoice",
            completed_query_open_invoice,
        ),
        (
            "Invoices with multiple active queries",
            duplicate_active_queries,
        ),
    ]

    for label, rows in checks:
        print(f"{label}: {len(rows)}")

        for row in rows:
            print(dict(row))


if __name__ == "__main__":
    main()
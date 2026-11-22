import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from assurance.repository import get_connection


def table_exists(
    connection,
    table_name,
):
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE
            type = 'table'
            AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def show_rows(
    label,
    rows,
):
    print(f"{label}: {len(rows)}")

    for row in rows:
        print(dict(row))


def main():
    with get_connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            ).fetchall()
        }

        print("Tables:")

        for table_name in sorted(tables):
            print(f"  {table_name}")

        required = {
            "processing_runs",
            "invoice_assurance_results",
        }

        missing = required - tables

        if missing:
            print(
                "Required tables missing:",
                sorted(missing),
            )

            return

        orphan_invoice_results = connection.execute(
            """
            SELECT
                results.result_id,
                results.run_id,
                results.invoice_number
            FROM invoice_assurance_results AS results
            LEFT JOIN processing_runs AS runs
                ON runs.run_id = results.run_id
            WHERE runs.run_id IS NULL
            ORDER BY results.result_id
            """
        ).fetchall()

        empty_completed_runs = connection.execute(
            """
            SELECT
                runs.run_id,
                runs.status,
                runs.total_invoices,
                COUNT(
                    results.result_id
                ) AS persisted_results
            FROM processing_runs AS runs
            LEFT JOIN invoice_assurance_results AS results
                ON results.run_id = runs.run_id
            WHERE runs.status = 'COMPLETED'
            GROUP BY
                runs.run_id,
                runs.status,
                runs.total_invoices
            HAVING COUNT(
                results.result_id
            ) = 0
            """
        ).fetchall()

        count_mismatches = connection.execute(
            """
            SELECT
                runs.run_id,
                runs.status,
                runs.total_invoices,
                COUNT(
                    results.result_id
                ) AS persisted_results
            FROM processing_runs AS runs
            LEFT JOIN invoice_assurance_results AS results
                ON results.run_id = runs.run_id
            GROUP BY
                runs.run_id,
                runs.status,
                runs.total_invoices
            HAVING
                runs.total_invoices
                != COUNT(
                    results.result_id
                )
            """
        ).fetchall()

        duplicate_run_invoices = connection.execute(
            """
            SELECT
                run_id,
                invoice_number,
                COUNT(*) AS result_count
            FROM invoice_assurance_results
            GROUP BY
                run_id,
                invoice_number
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        show_rows(
            "Orphan invoice results",
            orphan_invoice_results,
        )

        show_rows(
            "Completed runs without results",
            empty_completed_runs,
        )

        show_rows(
            "Run invoice-count mismatches",
            count_mismatches,
        )

        show_rows(
            "Duplicate invoices within a run",
            duplicate_run_invoices,
        )

        if table_exists(
            connection,
            "supplier_queries",
        ):
            orphan_queries = connection.execute(
                """
                SELECT
                    queries.query_id,
                    queries.query_reference,
                    queries.run_id,
                    queries.invoice_number
                FROM supplier_queries AS queries
                LEFT JOIN invoice_assurance_results AS results
                    ON results.run_id = queries.run_id
                    AND results.invoice_number =
                        queries.invoice_number
                WHERE results.result_id IS NULL
                """
            ).fetchall()

            show_rows(
                "Orphan supplier queries",
                orphan_queries,
            )


if __name__ == "__main__":
    main()
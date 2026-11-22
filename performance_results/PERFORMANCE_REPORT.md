# Project 1 Performance Report

The benchmark exercises the complete runtime billing-file pipeline using isolated registry and assurance databases.

## Results

| Invoices | Records | File MB | Duration (s) | Invoices/s | Peak MB | Persisted | Duplicates | Integrity |
|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1,000 | 9,004 | 0.613 | 7.757 | 128.908 | 27.254 | 1,000 | 0 | PASS |

## Acceptance criteria

- 1,000 invoices complete within 60 seconds.
- Expected production files contain no more than 2,500 invoices.
- Persisted invoice count equals generated count.
- Distinct invoice count equals generated count.
- No duplicated invoice number within a run.
- Registry status and stage both equal `COMPLETED`.

## Notes

- Generated billing files and SQLite databases are excluded from Git.
- Results are machine-specific and should be compared only with runs on similar hardware.
## Operational scope

Daily billing files are expected to contain no more than
2,500 invoices. The formal release benchmark uses 1,000
invoices and exercises parsing, validation, reconciliation,
pattern analysis, risk scoring, assurance decisions, SQLite
persistence, and registry completion.

A 10,000-invoice run is outside the expected operational
scope and is not a Project 1 release requirement.

# Database Deployment Decision

## Current release

Project 1 version 1.0 uses SQLite for:

- Assurance processing and invoice results
- Supplier-query lifecycle
- Audit history
- Billing-file registry and recovery

SQLite is appropriate for the local portfolio and controlled
single-process demonstration deployment.

## Production target

The intended production database is PostgreSQL, accessed using
SQLAlchemy 2.x with Alembic schema migrations and psycopg.

## Current constraint

The development environment does not currently provide:

- SQLAlchemy
- Alembic
- psycopg
- PostgreSQL command-line tools
- Docker
- Access to the public Python package index

The corporate proxy returns HTTP 407 when public packages are
requested.

## Release decision

The PostgreSQL migration is deferred until an approved internal
package repository, offline wheel bundle, PostgreSQL environment,
or Docker-enabled build agent is available.

No untested PostgreSQL implementation is included in version 1.0.

## Production restriction

The SQLite release should run as a single application process.
It is not approved for concurrent multi-instance cloud deployment.

Before multi-user production deployment:

1. Provision PostgreSQL.
2. Install approved SQLAlchemy, Alembic, and psycopg packages.
3. Apply version-controlled schema migrations.
4. Migrate existing SQLite records.
5. Run the full automated suite against PostgreSQL.
6. Repeat the 1,000-invoice benchmark.
7. Validate backup, restore, retention, and disaster recovery.
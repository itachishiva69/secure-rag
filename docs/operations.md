# Secure RAG Operations Runbook

## Purpose

This document describes the operational signals, checks, backup procedures,
recovery procedures, and common recovery actions for the Secure RAG
application.

The application consists of:

* FastAPI API
* PostgreSQL
* Qdrant
* Redis
* RQ worker
* RQ maintenance scheduler
* durable PostgreSQL outbox
* shared application storage

Production service communication between PostgreSQL, Qdrant, Redis, the
worker, scheduler, and API occurs over the Docker Compose network.

Only the API is host-published.

---

## Production Service Perimeter

Expected production host exposure:

```text
127.0.0.1:8001 -> API container:8000
```

PostgreSQL, Qdrant, Redis, worker, and scheduler are not intended to be
directly exposed on the production host.

Check the current production service state:

```bash
docker compose ps
```

Expected production services:

```text
postgres
qdrant
redis
api
worker
scheduler
```

Test infrastructure is isolated behind the Docker Compose `test` profile and
should not be considered part of the normal production runtime.

---

## Health and Readiness

### API health

```bash
curl http://127.0.0.1:8001/health
```

Expected result:

```json
{
  "status": "ok",
  "environment": "production"
}
```

### API readiness

```bash
curl http://127.0.0.1:8001/ready
```

Expected result:

```json
{
  "status": "ready"
}
```

Readiness is the stronger operational check because it verifies that the
application is able to operate with its required dependencies.

### Qdrant health

```bash
curl http://127.0.0.1:8001/health/qdrant
```

Expected result:

```json
{
  "status": "ok"
}
```

### Container health

```bash
docker compose ps
```

The API, PostgreSQL, and Redis containers should report healthy status.

Qdrant currently relies on application-level dependency/readiness checks rather
than a container-level HTTP healthcheck.

---

## Logs

Inspect the API:

```bash
docker compose logs --tail=200 api
```

Inspect the worker:

```bash
docker compose logs --tail=200 worker
```

Inspect the scheduler:

```bash
docker compose logs --tail=200 scheduler
```

Inspect PostgreSQL:

```bash
docker compose logs --tail=200 postgres
```

Inspect Qdrant:

```bash
docker compose logs --tail=200 qdrant
```

Inspect Redis:

```bash
docker compose logs --tail=200 redis
```

Follow a service continuously:

```bash
docker compose logs -f api
```

or:

```bash
docker compose logs -f worker
```

---

## Durable Data Model

The recovery strategy follows the application's data model.

```text
PostgreSQL
    |
    +-- authoritative application metadata and workflow state
    |
    +-- durable outbox

/app/storage/documents
    |
    +-- original uploaded document files

Qdrant
    |
    +-- derived vector/index state

Redis / RQ
    |
    +-- transient queue state
```

PostgreSQL is the authoritative source for application state.

Document files are durable application data and must be included in
production backups.

Qdrant contains derived retrieval state. It is backed up to provide a fast
recovery path, but it can be rebuilt from durable application data if necessary.

Redis/RQ queue state is transient and is intentionally not included in the
backup procedure.

The durable PostgreSQL outbox is the mechanism for preserving asynchronous
work intent across queue interruptions.

---

# Backup Operations

## Production Backup

The production backup script creates a timestamped backup directory containing:

```text
backups/<timestamp>/
├── backup.info
├── sha256sums.txt
├── postgres/
│   └── database.sql.gz
├── documents/
│   └── documents/
└── qdrant/
    └── qdrant_<snapshot>.snapshot.snapshot
```

Run:

```bash
./scripts/backup.sh
```

The script performs:

1. PostgreSQL readiness verification.
2. API readiness verification.
3. PostgreSQL logical backup using `pg_dump`.
4. Uploaded document backup.
5. Full Qdrant storage snapshot creation.
6. Qdrant snapshot download.
7. Backup metadata generation.
8. SHA-256 checksum generation.

The generated backup is written under:

```text
backups/<YYYYMMDD_HHMMSS>/
```

The `backups/` directory is intentionally ignored by Git.

Do not commit production backup contents to the repository.

---

## Backup Verification

After creating a backup, verify its checksums.

Example:

```bash
cd backups/<TIMESTAMP>

sha256sum -c sha256sums.txt
```

Every backed-up file should report:

```text
OK
```

A valid backup should contain at least:

```text
backup.info
sha256sums.txt
postgres/database.sql.gz
documents/documents/<uploaded files>
qdrant/<full snapshot>
```

Inspect metadata:

```bash
cat backup.info
```

Inspect backup size:

```bash
du -sh .
```

A backup should not be considered verified until:

* the backup script completes successfully;
* the expected PostgreSQL dump exists;
* the expected document files exist;
* the Qdrant snapshot exists;
* checksum verification succeeds.

---

# Restore Operations

Restore procedures should be performed in an isolated environment whenever
possible.

Do not overwrite production PostgreSQL or Qdrant data during a restore drill.

---

## PostgreSQL Restore

The PostgreSQL backup is a plain SQL dump compressed with gzip.

Create an isolated PostgreSQL instance:

```bash
docker run -d \
  --name secure-rag-postgres-restore-test \
  -e POSTGRES_DB=restore_test \
  -e POSTGRES_USER=restore_test \
  -e POSTGRES_PASSWORD=restore_test \
  -p 55432:5432 \
  postgres:16.15
```

Wait for readiness:

```bash
until docker exec secure-rag-postgres-restore-test \
  pg_isready -U restore_test -d restore_test >/dev/null 2>&1
do
    sleep 1
done
```

Restore the compressed SQL dump:

```bash
gunzip -c \
  <BACKUP_DIR>/postgres/database.sql.gz |
docker exec -i secure-rag-postgres-restore-test \
  psql -U restore_test -d restore_test
```

Verify the restored tables:

```bash
docker exec secure-rag-postgres-restore-test \
  psql -U restore_test -d restore_test \
  -c '\dt'
```

Verify the public tables explicitly:

```bash
docker exec secure-rag-postgres-restore-test \
  psql -U restore_test -d restore_test \
  -c 'SELECT schemaname, tablename
      FROM pg_tables
      WHERE schemaname = '\''public'\''
      ORDER BY tablename;'
```

Clean up the isolated database:

```bash
docker rm -f secure-rag-postgres-restore-test
```

A successful restore drill should show the application's expected tables,
including:

```text
alembic_version
audit_logs
departments
document_departments
documents
outbox_events
users
```

---

## Document Restore

Uploaded document files are backed up separately from PostgreSQL.

Restore them into an isolated directory first:

```bash
rm -rf /tmp/secure-rag-documents-restore
mkdir -p /tmp/secure-rag-documents-restore

cp -a \
  <BACKUP_DIR>/documents/documents/. \
  /tmp/secure-rag-documents-restore/
```

Inspect the restored files:

```bash
find /tmp/secure-rag-documents-restore \
  -type f \
  -printf '%P\n' |
  sort
```

Verify the backup integrity:

```bash
cd <BACKUP_DIR>

sha256sum -c sha256sums.txt
```

Do not copy restored files directly over production storage until the
production recovery procedure has been deliberately approved.

---

## Qdrant Restore

Qdrant is restored from a full storage snapshot.

Use the same Qdrant minor version as the production snapshot whenever possible.

For an isolated restore drill, create a Docker volume:

```bash
docker volume create secure-rag-qdrant-restore-test
```

Start a temporary preparation container:

```bash
docker run -d \
  --name secure-rag-qdrant-restore-prep \
  -v secure-rag-qdrant-restore-test:/qdrant/snapshots \
  alpine:3.22 \
  sleep 300
```

Copy the snapshot into the Docker volume:

```bash
docker cp \
  <BACKUP_DIR>/qdrant/<SNAPSHOT_FILE> \
  secure-rag-qdrant-restore-prep:/qdrant/snapshots/full-snapshot.snapshot
```

Set readable permissions:

```bash
docker exec secure-rag-qdrant-restore-prep \
  chmod 644 /qdrant/snapshots/full-snapshot.snapshot
```

Verify the snapshot:

```bash
docker exec secure-rag-qdrant-restore-prep \
  ls -lh /qdrant/snapshots/full-snapshot.snapshot
```

Remove the preparation container:

```bash
docker rm -f secure-rag-qdrant-restore-prep
```

Start Qdrant using the snapshot:

```bash
docker run -d \
  --name secure-rag-qdrant-restore-test \
  -p 6335:6333 \
  -v secure-rag-qdrant-restore-test:/qdrant/snapshots \
  qdrant/qdrant:v1.19.1 \
  ./qdrant \
  --storage-snapshot /qdrant/snapshots/full-snapshot.snapshot
```

Inspect startup:

```bash
docker logs secure-rag-qdrant-restore-test
```

Verify the restored collections:

```bash
curl http://127.0.0.1:6335/collections
```

The expected recovery result is that the application collection is available,
for example:

```json
{
  "result": {
    "collections": [
      {
        "name": "documents"
      }
    ]
  },
  "status": "ok"
}
```

Clean up the isolated restore environment:

```bash
docker rm -f secure-rag-qdrant-restore-test
docker volume rm secure-rag-qdrant-restore-test
```

---

# Verified Recovery Checkpoint

The following recovery procedures have been exercised successfully against
the production backup created during Phase 8:

```text
PostgreSQL restore         ✅
Document restore           ✅
Qdrant restore             ✅
SHA-256 verification       ✅
Remote S3 restore drill    ✅
```

The verified backup included:

```text
PostgreSQL database dump
Uploaded document files
Full Qdrant storage snapshot
Backup metadata
SHA-256 manifest
```

The remote archive was synchronized to an isolated restore location and
checksum verification succeeded before the individual PostgreSQL, document,
and Qdrant restore drills were performed.

The live production services remained untouched during the restore drills.

---

# Outbox and Worker Operations

The PostgreSQL outbox is durable application state.

The worker consumes asynchronous work from the queue and processes document
lifecycle operations.

When queue infrastructure is interrupted, the durable outbox preserves work
intent so that operations can be recovered.

Inspect worker logs:

```bash
docker compose logs --tail=200 worker
```

Inspect scheduler logs:

```bash
docker compose logs --tail=200 scheduler
```

When investigating document processing problems, inspect:

1. document state in PostgreSQL;
2. corresponding outbox state;
3. worker logs;
4. Qdrant collection state.

Do not manually modify PostgreSQL lifecycle state unless performing an approved
incident recovery procedure.

---

# Document Lifecycle Incidents

The application uses explicit document lifecycle states.

When a document appears stuck:

1. Inspect the document state in PostgreSQL.
2. Inspect the associated durable outbox event.
3. Inspect worker logs.
4. Inspect Qdrant state if the operation involves vectors.
5. Allow the application's reconciliation mechanisms to handle stale states
   where applicable.

Do not treat Qdrant alone as the authoritative state of a document.

---

# Application Restart

A normal production restart:

```bash
docker compose restart api worker scheduler
```

If the entire application stack needs to be recreated:

```bash
docker compose up -d
```

Then verify:

```bash
docker compose ps
```

and:

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/ready
curl http://127.0.0.1:8001/health/qdrant
```

Do not delete persistent PostgreSQL, Qdrant, or application-storage data merely
to resolve an application startup problem.

---

# Production Configuration Checks

Production containers require critical configuration to be provided through
environment configuration.

Before a production deployment:

```bash
docker compose config >/dev/null
```

This should succeed with the intended production environment configuration.

To verify fail-fast behavior when required configuration is absent:

```bash
docker compose --env-file /dev/null config
```

This should fail rather than silently supplying unsafe production defaults.

Never commit:

```text
.env
```

or production credentials into the repository.

Secrets such as:

```text
POSTGRES_PASSWORD
JWT_SECRET
LLM_API_KEY
```

must be supplied through the production environment configuration.

---

# Test Infrastructure

Test PostgreSQL, Qdrant, and Redis are isolated behind the Docker Compose
`test` profile.

Production services:

```bash
docker compose config --services
```

should list the normal production services.

The test profile can be inspected with:

```bash
docker compose --profile test config --services
```

The test services must not be treated as production dependencies.

---

# Operational Validation

Before declaring a production deployment operational, verify:

```bash
docker compose ps
```

Then:

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/ready
curl http://127.0.0.1:8001/health/qdrant
```

Verify application logs:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 scheduler
```

Verify the test suite from the development environment:

```bash
pytest -q
```

The production deployment should not be considered complete if:

* required production configuration is missing;
* API readiness fails;
* PostgreSQL is unavailable;
* Qdrant is unavailable;
* worker or scheduler is continuously failing;
* backup verification fails;
* restore verification has not been demonstrated.

---

# Incident Recovery Principles

When diagnosing production failures:

```text
1. Preserve durable data.
2. Identify the failing layer.
3. Check application readiness.
4. Check PostgreSQL state.
5. Check outbox/work queue state.
6. Check worker/scheduler state.
7. Check document storage.
8. Check Qdrant derived state.
9. Restore from verified backups when required.
```

Do not destroy application data as a first troubleshooting step.

Do not treat Redis queue state as the authoritative record of pending work.

Do not treat Qdrant as the authoritative record of document lifecycle state.

PostgreSQL and the original document storage are the primary durable
application state.

---

# Backup Retention

Production backups are archived outside the application host using Amazon S3.

The remote backup location is configured through:

```text
BACKUP_REMOTE_URI=s3://<bucket>/secure-rag/production
```

Remote archival is performed by:

```bash
./scripts/archive_backup.sh backups/<TIMESTAMP>
```

The archival process uploads the complete verified backup directory and
verifies the uploaded objects against the local backup checksums.

The production remote archive contains the same logical backup contents as the
local verified backup:

```text
backup.info
documents/
postgres/database.sql.gz
qdrant/<SNAPSHOT_FILE>
sha256sums.txt
```

The remote S3 bucket is hardened with:

* S3 Block Public Access enabled;
* S3 Object Ownership set to `BucketOwnerEnforced`;
* default SSE-S3 encryption;
* bucket versioning enabled;
* no public bucket policy;
* access restricted to the dedicated backup role.

Backup operations use the dedicated `SecureRAGBackupRole`.

The role is assumed through the dedicated `secure-rag-backup-cli` IAM user
and requires MFA.

The backup role is restricted to the production backup prefix and provides only
the S3 permissions required for backup archival, verification, listing, and
normal cleanup.

The backup role does not have `s3:DeleteObjectVersion`.

Permanent deletion of old object versions is therefore delegated to the S3
lifecycle configuration rather than allowing the backup automation to remove
object versions directly.

---

## Remote Backup Archival

Archive a verified local backup:

```bash
BACKUP_REMOTE_URI="s3://<bucket>/secure-rag/production" \
AWS_PROFILE=secure-rag-backup \
./scripts/archive_backup.sh backups/<TIMESTAMP>
```

A successful archival operation must:

1. identify a valid local backup;
2. verify the local SHA-256 manifest;
3. upload the complete backup contents;
4. verify the remote object set;
5. preserve the backup metadata and checksum manifest.

Remote archival has been validated successfully against the production backup
created during Phase 8.

---

## Remote Backup Verification

A remote backup should be synchronized to an isolated location before a remote
restore drill:

```bash
rm -rf /tmp/secure-rag-remote-restore
mkdir -p /tmp/secure-rag-remote-restore

AWS_PROFILE=secure-rag-backup \
aws s3 sync \
  "s3://<bucket>/secure-rag/production/<TIMESTAMP>/" \
  /tmp/secure-rag-remote-restore/
```

Verify the restored archive contents and checksums:

```bash
cd /tmp/secure-rag-remote-restore

sha256sum -c sha256sums.txt
```

The remote restore drill should then use the recovered backup directory as the
input to the PostgreSQL, document, and Qdrant isolated restore procedures.

The remote restore drill completed successfully for the verified production
backup. The remote archive contained the expected six backup objects and the
downloaded contents passed checksum verification before restore testing.

---

## Remote Backup Retention

Remote cleanup is performed by:

```bash
./scripts/cleanup_remote_backups.sh
```

The cleanup process identifies expired timestamped backup generations and
performs normal object deletion for the configured production backup prefix.

S3 versioning provides an additional recovery layer by retaining previous
object versions after normal deletion.

The backup role intentionally does not have permission to permanently delete
object versions.

---

## S3 Lifecycle Retention

The production backup prefix is covered by an S3 lifecycle configuration.

Current lifecycle behavior:

```text
Current object expiration            30 days
Noncurrent version expiration        30 days
Expired delete markers               removed
Incomplete multipart uploads         aborted after 7 days
```

Current-object expiration and noncurrent-version expiration are lifecycle
eligibility periods. S3 lifecycle processing is asynchronous and deletion does
not necessarily occur at the exact expiration timestamp.

Because S3 versioning is enabled, normal object deletion may create a delete
marker. Older object versions remain available until the lifecycle policy
makes them eligible for removal.

The dedicated backup role cannot bypass this control by calling
`s3:DeleteObjectVersion`.

The remote S3 archive therefore provides protection against loss of the
production application host while retaining version-aware lifecycle controls.

---

## Local Backup Retention

The local `backups/` directory remains useful for operational recovery and
short-term investigation.

Production backups must not be treated as protected against host loss unless
the corresponding backup has also been successfully archived remotely.

A verified remote archive should exist before considering the backup workflow
complete.

---


# Production systemd Backup Automation

Production backup automation is executed by the host-level systemd timer rather than by
Docker Compose.

The scheduled backup flow is:

```text
systemd timer
    ↓
secure-rag-backup.service
    ↓
/usr/local/libexec/secure-rag-backup
    ↓
local backup creation
    ↓
checksum verification as secure-rag-backup
    ↓
/usr/local/libexec/secure-rag-archive-backup
    ↓
S3 upload + remote object verification
    ↓
/usr/local/libexec/secure-rag-cleanup-remote-backups
    ↓
remote retention
```

The runtime wrapper is installed at:

```text
/usr/local/libexec/secure-rag-backup
```

The wrapper intentionally runs the local backup creation from the repository as `root`,
because it must access the Docker application storage and other protected host resources.
Remote archival and retention are executed as the dedicated unprivileged service account:

```text
secure-rag-backup
```

The host-installed archival and retention helpers are:

```text
/usr/local/libexec/secure-rag-archive-backup
/usr/local/libexec/secure-rag-cleanup-remote-backups
```

These installed copies are required for the systemd service because the service account must
not depend on traversing the private user home directory.

Do not loosen `/home/shiva` permissions to make the backup service work. Keep the user's
home directory private.

## systemd Service Configuration

The main service definition contains:

```ini
[Service]
TimeoutStartSec=2h
```

A systemd drop-in overrides this with the timeout required by the backup wrapper's retry
policy:

```text
/etc/systemd/system/secure-rag-backup.service.d/override.conf
```

Contents:

```ini
[Service]
TimeoutStartSec=10h
```

The effective configuration can be verified with:

```bash
systemctl show secure-rag-backup.service -p TimeoutStartUSec
```

Expected:

```text
TimeoutStartUSec=10h
```

The 10-hour timeout provides enough headroom for the wrapper's approximately 9-hour-22-minute
retry window for S3 archival and remote retention.

Reload systemd after changing the drop-in:

```bash
sudo systemctl daemon-reload
```

## Backup Timer

The scheduled timer is:

```text
secure-rag-backup.timer
```

Verify it with:

```bash
sudo systemctl status secure-rag-backup.timer --no-pager
sudo systemctl list-timers --all | grep secure-rag-backup
```

The production schedule is daily at approximately 02:30 local time, with persistence and a
small randomized delay.

The service itself is intentionally `disabled`; the timer is the component that is enabled:

```bash
sudo systemctl is-enabled secure-rag-backup.timer
```

Expected:

```text
enabled
```

Run a complete backup manually through systemd when validating the production pipeline:

```bash
sudo systemctl start secure-rag-backup.service
```

Check the result:

```bash
sudo systemctl status secure-rag-backup.service --no-pager
sudo journalctl -u secure-rag-backup.service -n 100 --no-pager
```

A successful run should show:

```text
Backup pipeline completed successfully.
```

## Production Local Backup Verification

The production backup manifest is named:

```text
sha256sums.txt
```

When verifying a production backup from the protected backup directory, use root:

```bash
sudo bash -c '
cd /var/lib/secure-rag-backup/backups/<TIMESTAMP> &&
sha256sum -c sha256sums.txt
'
```

Every manifest entry must report:

```text
OK
```

Do not use `sha256sums` without the `.txt` suffix.

## S3 Archival and Retention

The production remote backup prefix is:

```text
s3://secure-rag-backups-557358104639/secure-rag/production
```

The dedicated automation profile is:

```text
secure-rag-backup-auto
```

The systemd wrapper supplies the required environment to the archive and retention helpers.
Therefore, testing the archive helper by executing it directly without its environment may
produce the expected error:

```text
ERROR: BACKUP_REMOTE_URI is not set.
```

For production validation, execute the complete pipeline through:

```bash
sudo systemctl start secure-rag-backup.service
```

For manual, interactive archival using the repository helper, the repository script remains
available:

```bash
AWS_PROFILE=secure-rag-backup ./scripts/archive_backup.sh backups/<TIMESTAMP>
```

Likewise, the repository retention helper remains available for manual administrative use:

```bash
AWS_PROFILE=secure-rag-backup ./scripts/cleanup_remote_backups.sh
```

The systemd automation does not execute those repository paths as the `secure-rag-backup`
user. It executes the root-owned copies under `/usr/local/libexec`.

## Host-Installed Helper Maintenance

The host-installed helper copies should be refreshed whenever the corresponding repository
scripts change:

```bash
sudo install -o root -g root -m 0755 \
  /home/shiva/Projects/secure-rag/scripts/archive_backup.sh \
  /usr/local/libexec/secure-rag-archive-backup

sudo install -o root -g root -m 0755 \
  /home/shiva/Projects/secure-rag/scripts/cleanup_remote_backups.sh \
  /usr/local/libexec/secure-rag-cleanup-remote-backups
```

Verify ownership and mode:

```bash
sudo ls -l \
  /usr/local/libexec/secure-rag-archive-backup \
  /usr/local/libexec/secure-rag-cleanup-remote-backups
```

Both files should be executable and owned by `root:root`.

Verify that the service account can execute them:

```bash
sudo -u secure-rag-backup test -x \
  /usr/local/libexec/secure-rag-archive-backup

sudo -u secure-rag-backup test -x \
  /usr/local/libexec/secure-rag-cleanup-remote-backups
```

## Persistent Application Storage

The application document volume remains:

```text
secure-rag_app_storage
```

and is mounted inside the application containers at:

```text
/app/storage
```

The obsolete Compose `storage-init` container is not part of the current Compose
configuration and should not be recreated merely to fix backup permissions.

Do not remove the `secure-rag_app_storage` volume when cleaning up obsolete containers.

## Backup Operational Checkpoint

After a successful production run, validate all of the following:

```text
✓ local backup created
✓ checksum manifest verified
✓ PostgreSQL dump present
✓ uploaded documents present
✓ Qdrant full snapshot present
✓ S3 upload completed
✓ remote S3 objects verified
✓ remote retention completed
✓ secure-rag-backup.service exited with status 0
✓ secure-rag-backup.timer remains enabled and waiting
```

Production backups must not be considered protected against host loss until the
corresponding local backup has also been archived successfully to the remote S3 location.

---

# Current Phase 8 Operational Status

```text
Docker hardening                    ✅
Production image pinning            ✅
Test service isolation              ✅
Required production configuration   ✅
Production backup                   ✅
Backup integrity verification       ✅
PostgreSQL restore drill            ✅
Document restore drill              ✅
Qdrant restore drill                ✅
Operational runbook                 ✅
Remote backup archival              ✅
Remote backup restore drill         ✅
Automated backup retention          ✅
S3 lifecycle retention              ✅
Final production review             ⏳
```

#!/usr/bin/env bash

set -Eeuo pipefail

# Secure RAG production backup.
#
# Backup model:
#   PostgreSQL              -> authoritative metadata/state
#   /app/storage/documents -> original uploaded documents
#   Qdrant                  -> derived vector/index state
#   Redis/RQ                -> transient queue state, not backed up
#
# The script is intended to be run from the project root on the Docker host.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_ROOT="${BACKUP_ROOT:-"$PROJECT_ROOT/backups"}"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

POSTGRES_BACKUP="$BACKUP_DIR/postgres"
DOCUMENTS_BACKUP="$BACKUP_DIR/documents"
QDRANT_BACKUP="$BACKUP_DIR/qdrant"

mkdir -p \
    "$POSTGRES_BACKUP" \
    "$DOCUMENTS_BACKUP" \
    "$QDRANT_BACKUP"

cleanup() {
    local exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        echo >&2
        echo "Backup failed. Partial backup remains at:"
        echo "  $BACKUP_DIR"
    fi

    exit "$exit_code"
}

trap cleanup EXIT

echo "========================================"
echo "Secure RAG backup"
echo "========================================"
echo "Project root : $PROJECT_ROOT"
echo "Backup dir   : $BACKUP_DIR"
echo

# ---------------------------------------------------------------------------
# 1. Check production services
# ---------------------------------------------------------------------------

echo "[1/4] Checking production services..."

docker compose ps --services >/dev/null

if ! docker compose exec -T postgres pg_isready >/dev/null 2>&1; then
    echo "ERROR: PostgreSQL is not ready." >&2
    exit 1
fi

if ! docker compose exec -T api python -c \
    'import urllib.request; urllib.request.urlopen("http://localhost:8000/ready", timeout=10).read()' \
    >/dev/null 2>&1; then
    echo "ERROR: API readiness check failed." >&2
    exit 1
fi

echo "  PostgreSQL is reachable."
echo "  API is ready."
echo

# ---------------------------------------------------------------------------
# 2. PostgreSQL backup
# ---------------------------------------------------------------------------

echo "[2/4] Backing up PostgreSQL..."

POSTGRES_DUMP="$POSTGRES_BACKUP/database.sql"

docker compose exec -T postgres \
    sh -c 'pg_dump \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --format=plain \
        --no-owner \
        --no-privileges' \
    > "$POSTGRES_DUMP"

gzip -9 "$POSTGRES_DUMP"

echo "  PostgreSQL backup: ${POSTGRES_DUMP}.gz"
echo

# ---------------------------------------------------------------------------
# 3. Uploaded document backup
# ---------------------------------------------------------------------------

echo "[3/4] Backing up uploaded documents..."

# API and worker share /app/storage/documents.
# Copy through the API container so the host does not need direct access
# to the application's storage volume.

mkdir -p "$DOCUMENTS_BACKUP/documents"

docker compose cp \
    api:/app/storage/documents/. \
    "$DOCUMENTS_BACKUP/documents/"

echo "  Document backup: $DOCUMENTS_BACKUP/documents"
echo

# ---------------------------------------------------------------------------
# 4. Qdrant snapshot backup
# ---------------------------------------------------------------------------

echo "[4/4] Backing up Qdrant..."

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"

echo "  Creating full Qdrant storage snapshot..."

QDRANT_SNAPSHOT_NAME="$(
    docker compose exec -T \
        -e QDRANT_URL="$QDRANT_URL" \
        api \
        python -c '
import json
import os
import sys
import urllib.request

url = os.environ["QDRANT_URL"].rstrip("/") + "/snapshots"

request = urllib.request.Request(
    url,
    method="POST",
    headers={"Accept": "application/json"},
)

try:
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.load(response)
except Exception as exc:
    print(
        f"Qdrant snapshot creation failed: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(1)

if payload.get("status") != "ok":
    print(
        f"Unexpected Qdrant response: {payload}",
        file=sys.stderr,
    )
    raise SystemExit(1)

result = payload.get("result") or {}
name = result.get("name")

if not name:
    print(
        f"Qdrant snapshot name missing: {payload}",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(name)
'
)"

QDRANT_SNAPSHOT_NAME="$(
    printf '%s' "$QDRANT_SNAPSHOT_NAME" |
        tail -n 1 |
        tr -d '\r'
)"

if [[ -z "$QDRANT_SNAPSHOT_NAME" ]]; then
    echo "ERROR: Qdrant returned an empty snapshot name." >&2
    exit 1
fi

echo "  Snapshot created: $QDRANT_SNAPSHOT_NAME"
echo "  Downloading snapshot..."

QDRANT_SNAPSHOT_FILE="$QDRANT_BACKUP/qdrant_${QDRANT_SNAPSHOT_NAME}.snapshot"

docker compose exec -T \
    -e QDRANT_URL="$QDRANT_URL" \
    -e QDRANT_SNAPSHOT_NAME="$QDRANT_SNAPSHOT_NAME" \
    api \
    python -c '
import os
import sys
import urllib.request

base_url = os.environ["QDRANT_URL"].rstrip("/")
snapshot_name = os.environ["QDRANT_SNAPSHOT_NAME"]

url = f"{base_url}/snapshots/{snapshot_name}"

request = urllib.request.Request(
    url,
    method="GET",
)

try:
    with urllib.request.urlopen(request, timeout=600) as response:
        while True:
            chunk = response.read(1024 * 1024)

            if not chunk:
                break

            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
except Exception as exc:
    print(
        f"Qdrant snapshot download failed: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(1)
' > "$QDRANT_SNAPSHOT_FILE"

echo "  Qdrant backup: $QDRANT_SNAPSHOT_FILE"
echo

# ---------------------------------------------------------------------------
# Backup metadata
# ---------------------------------------------------------------------------

echo "Writing backup metadata..."

cat > "$BACKUP_DIR/backup.info" <<EOF
Secure RAG Backup
=================

Created:
$(date --iso-8601=seconds)

Host:
$(hostname)

Git commit:
$(git rev-parse HEAD 2>/dev/null || echo "unknown")

PostgreSQL:
postgres/database.sql.gz

Documents:
documents/documents/

Qdrant:
qdrant/$(basename "$QDRANT_SNAPSHOT_FILE")

Qdrant snapshot:
$QDRANT_SNAPSHOT_NAME

Redis/RQ:
Not backed up; queue state is transient.
EOF

echo "  Metadata: $BACKUP_DIR/backup.info"
echo

# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------

echo "Generating checksums..."

(
    cd "$BACKUP_DIR"

    find . \
        -type f \
        ! -name 'sha256sums.txt' \
        -print0 |
        sort -z |
        xargs -0 sha256sum > sha256sums.txt
)

echo "  Checksums: $BACKUP_DIR/sha256sums.txt"
echo

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

echo "========================================"
echo "Backup completed successfully."
echo "========================================"
echo
echo "Backup location:"
echo "  $BACKUP_DIR"
echo
echo "Contents:"

find "$BACKUP_DIR" \
    -maxdepth 3 \
    -type f \
    -printf '  %P\n' |
    sort
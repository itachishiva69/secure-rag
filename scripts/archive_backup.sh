#!/usr/bin/env bash

set -Eeuo pipefail

# Secure RAG remote backup archival.
#
# Uploads one already-created and checksum-verified local backup directory
# to an S3-compatible object-storage location.
#
# Required:
#   BACKUP_REMOTE_URI=s3://bucket/prefix
#
# Optional:
#   AWS_ENDPOINT_URL=https://...
#
# The AWS CLI obtains credentials from its normal credential chain:
# environment variables, profile, instance role, workload identity, etc.
#
# The script intentionally does not delete the local backup.
#
# Intended to be run from the project root on the Docker host.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_ROOT="${BACKUP_ROOT:-"$PROJECT_ROOT/backups"}"
BACKUP_REMOTE_URI="${BACKUP_REMOTE_URI:-}"

if [[ -z "$BACKUP_REMOTE_URI" ]]; then
    echo "ERROR: BACKUP_REMOTE_URI is not set." >&2
    echo "Example: BACKUP_REMOTE_URI=s3://my-bucket/secure-rag" >&2
    exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: AWS CLI is required but was not found." >&2
    exit 1
fi

usage() {
    cat >&2 <<'EOF'
Usage:
  ./scripts/archive_backup.sh <BACKUP_DIR>

Examples:
  ./scripts/archive_backup.sh backups/20260907_102505
  ./scripts/archive_backup.sh "$(find backups -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
EOF
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

BACKUP_DIR="$1"

if [[ "$BACKUP_DIR" != /* ]]; then
    BACKUP_DIR="$PROJECT_ROOT/$BACKUP_DIR"
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "ERROR: Backup directory does not exist:" >&2
    echo "  $BACKUP_DIR" >&2
    exit 1
fi

BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
BACKUP_NAME="$(basename "$BACKUP_DIR")"

if [[ ! "$BACKUP_NAME" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
    echo "ERROR: Backup directory name must use YYYYMMDD_HHMMSS format." >&2
    echo "  Got: $BACKUP_NAME" >&2
    exit 1
fi

CHECKSUM_FILE="$BACKUP_DIR/sha256sums.txt"

if [[ ! -f "$CHECKSUM_FILE" ]]; then
    echo "ERROR: SHA-256 manifest is missing:" >&2
    echo "  $CHECKSUM_FILE" >&2
    exit 1
fi

required_paths=(
    "$BACKUP_DIR/backup.info"
    "$BACKUP_DIR/postgres/database.sql.gz"
    "$BACKUP_DIR/documents"
    "$BACKUP_DIR/qdrant"
)

for required_path in "${required_paths[@]}"; do
    if [[ ! -e "$required_path" ]]; then
        echo "ERROR: Required backup content is missing:" >&2
        echo "  $required_path" >&2
        exit 1
    fi
done

echo "========================================"
echo "Secure RAG remote backup archival"
echo "========================================"
echo "Backup directory : $BACKUP_DIR"
echo "Remote base      : $BACKUP_REMOTE_URI"
echo

echo "[1/3] Verifying backup checksums..."

(
    cd "$BACKUP_DIR"
    sha256sum -c sha256sums.txt
)

echo
echo "[2/3] Uploading backup..."

REMOTE_URI="${BACKUP_REMOTE_URI%/}/$BACKUP_NAME"

AWS_ARGS=()

if [[ -n "${AWS_ENDPOINT_URL:-}" ]]; then
    AWS_ARGS+=(--endpoint-url "$AWS_ENDPOINT_URL")
fi

aws "${AWS_ARGS[@]}" s3 sync \
    "$BACKUP_DIR/" \
    "$REMOTE_URI/" \
    --only-show-errors

echo
echo "[3/3] Verifying remote backup contents..."

remote_objects="$(
    aws "${AWS_ARGS[@]}" s3api list-objects-v2 \
        --bucket "$(printf '%s' "$REMOTE_URI" | sed -E 's#^s3://([^/]+).*$#\1#')" \
        --prefix "$(printf '%s' "$REMOTE_URI" | sed -E 's#^s3://[^/]+/?(.*)$#\1#')" \
        --query 'Contents[].Key' \
        --output text
)"

if [[ -z "$remote_objects" || "$remote_objects" == "None" ]]; then
    echo "ERROR: Remote verification returned no objects." >&2
    exit 1
fi

remote_count="$(printf '%s\n' "$remote_objects" | wc -w | tr -d ' ')"

if [[ "$remote_count" -lt 1 ]]; then
    echo "ERROR: Remote backup appears empty." >&2
    exit 1
fi

echo "  Remote object count: $remote_count"
echo
echo "Backup archived successfully:"
echo "  $REMOTE_URI"
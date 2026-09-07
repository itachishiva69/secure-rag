#!/usr/bin/env bash

set -Eeuo pipefail

# Secure RAG remote backup retention.
#
# Deletes timestamped backup prefixes older than BACKUP_RETENTION_DAYS
# from an S3-compatible object-storage location.
#
# Required:
#   BACKUP_REMOTE_URI=s3://bucket/prefix
#
# Optional:
#   BACKUP_RETENTION_DAYS=30
#   AWS_ENDPOINT_URL=https://...
#
# Safety:
#   - Requires an explicit BACKUP_REMOTE_URI.
#   - Only processes timestamp-shaped YYYYMMDD_HHMMSS prefixes.
#   - Does not touch objects outside those backup prefixes.
#   - Defaults to a conservative 30-day retention period.
#
# Intended to be run from the project root on the Docker host.

BACKUP_REMOTE_URI="${BACKUP_REMOTE_URI:-}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

if [[ -z "$BACKUP_REMOTE_URI" ]]; then
    echo "ERROR: BACKUP_REMOTE_URI is not set." >&2
    exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: AWS CLI is required but was not found." >&2
    exit 1
fi

if [[ ! "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: BACKUP_RETENTION_DAYS must be a non-negative integer." >&2
    exit 1
fi

if (( BACKUP_RETENTION_DAYS < 1 )); then
    echo "ERROR: BACKUP_RETENTION_DAYS must be at least 1 day." >&2
    exit 1
fi

parse_s3_uri() {
    local uri="$1"

    if [[ "$uri" != s3://* ]]; then
        echo "ERROR: BACKUP_REMOTE_URI must start with s3://." >&2
        exit 1
    fi

    local without_scheme="${uri#s3://}"
    local bucket="${without_scheme%%/*}"
    local prefix=""

    if [[ "$without_scheme" == */* ]]; then
        prefix="${without_scheme#*/}"
    fi

    printf '%s\n%s\n' "$bucket" "$prefix"
}

mapfile -t S3_LOCATION < <(parse_s3_uri "$BACKUP_REMOTE_URI")

BUCKET="${S3_LOCATION[0]}"
PREFIX="${S3_LOCATION[1]}"

if [[ -z "$BUCKET" ]]; then
    echo "ERROR: S3 bucket is missing from BACKUP_REMOTE_URI." >&2
    exit 1
fi

AWS_ARGS=()

if [[ -n "${AWS_ENDPOINT_URL:-}" ]]; then
    AWS_ARGS+=(--endpoint-url "$AWS_ENDPOINT_URL")
fi

ROOT_PREFIX="$PREFIX"

if [[ -n "$ROOT_PREFIX" ]]; then
    ROOT_PREFIX="${ROOT_PREFIX%/}/"
fi

CUTOFF_EPOCH="$(date -d "-${BACKUP_RETENTION_DAYS} days" +%s)"

echo "========================================"
echo "Secure RAG remote backup retention"
echo "========================================"
echo "Remote location   : s3://$BUCKET/$ROOT_PREFIX"
echo "Retention days    : $BACKUP_RETENTION_DAYS"
echo "Cutoff             : $(date -d "@$CUTOFF_EPOCH" --iso-8601=seconds)"
echo

echo "[1/2] Listing backup prefixes..."

prefixes="$(
    aws "${AWS_ARGS[@]}" s3api list-objects-v2 \
        --bucket "$BUCKET" \
        --prefix "$ROOT_PREFIX" \
        --delimiter / \
        --query 'CommonPrefixes[].Prefix' \
        --output text
)"

if [[ -z "$prefixes" || "$prefixes" == "None" ]]; then
    echo "No remote backups found."
    exit 0
fi

deleted_count=0
retained_count=0
ignored_count=0

while IFS= read -r remote_prefix; do
    [[ -z "$remote_prefix" ]] && continue

    backup_name="${remote_prefix%/}"
    backup_name="${backup_name##*/}"

    if [[ ! "$backup_name" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
        ignored_count=$((ignored_count + 1))
        continue
    fi

    year="${backup_name:0:4}"
    month="${backup_name:4:2}"
    day="${backup_name:6:2}"
    hour="${backup_name:9:2}"
    minute="${backup_name:11:2}"
    second="${backup_name:13:2}"

    if ! backup_epoch="$(
        date \
            -d "${year}-${month}-${day} ${hour}:${minute}:${second}" \
            +%s \
            2>/dev/null
    )"; then
        echo "WARNING: Unable to parse backup prefix: $backup_name" >&2
        ignored_count=$((ignored_count + 1))
        continue
    fi

    if (( backup_epoch < CUTOFF_EPOCH )); then
        echo "Deleting expired backup: $backup_name"

        aws "${AWS_ARGS[@]}" s3 rm \
            "s3://$BUCKET/$remote_prefix" \
            --recursive \
            --only-show-errors

        deleted_count=$((deleted_count + 1))
    else
        retained_count=$((retained_count + 1))
    fi
done <<< "$prefixes"

echo
echo "[2/2] Retention summary"
echo "  Deleted : $deleted_count"
echo "  Retained: $retained_count"
echo "  Ignored : $ignored_count"
echo
echo "Remote backup retention completed."
# Phase 8.1 Production Deployment Hardening

Changes in this checkpoint:

- Portable Compose build context (`context: .`).
- Centralized shared API/worker/scheduler environment blocks with Compose YAML anchors.
- Required production secrets/configuration fail fast at Compose interpolation time.
- Qdrant pinned to `v1.19.0`, matching the version used by the verified test environment.
- API container readiness healthcheck uses `/ready`.
- API image runs as non-root UID 10001.
- Hugging Face cache and shared storage are writable by the non-root application user.
- `.env.example` is no longer copied into the runtime image.

No application Python code, migrations, tests, or data were changed.

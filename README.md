# Secure RAG

A production-style, department-aware Retrieval-Augmented Generation (RAG) application built with FastAPI, PostgreSQL, Qdrant, Redis, RQ, local document storage, JWT authentication, Argon2 password hashing, and a Groq OpenAI-compatible LLM.

The project is intentionally developed beyond a minimal RAG demo. Authorization, document lifecycle consistency, background processing, failure handling, API hardening, observability, testing, and operational procedures are treated as first-class concerns.

---

## Project Status

The production-style backend, operational foundation, observability stack,
backup/restore workflow, and security/reliability validation are implemented.
The final production review is the current checkpoint before frontend work.

```text
1. Core Application                    ✅ Complete
2. Authorization / Data Isolation      ✅ Complete
3. Document Lifecycle & Consistency    ✅ Complete
4. RAG Failure Handling                ✅ Complete
5. API & Application Hardening         ✅ Complete
6. Observability & Operations          ✅ Complete
7. Security & Reliability Testing      ✅ Complete
8. Production Deployment               ✅ Complete
9. Frontend                            ⬜ Not Started
10. Final Production Review             🚧 In Progress
```

---

## Technology Stack

| Component | Technology |
|---|---|
| API | FastAPI |
| Language | Python 3.12 |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Vector Database | Qdrant |
| Cache / Queue Backend | Redis |
| Background Jobs | RQ |
| Embeddings | `BAAI/bge-small-en-v1.5` |
| Embedding Runtime | Sentence Transformers, CPU-only |
| LLM | Groq OpenAI-compatible API |
| LLM Model | `openai/gpt-oss-120b` |
| Authentication | JWT |
| Password Hashing | Argon2 |
| Document Storage | Local shared Docker volume |
| Containers | Docker Compose |
| Testing | pytest |

LangChain is intentionally limited to the text-splitting dependency used by the application.

---

## Architecture

```text
                                ┌──────────────────────┐
                                │        Client        │
                                └──────────┬───────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │       FastAPI        │
                                │                      │
                                │ Authentication       │
                                │ Authorization        │
                                │ Rate Limiting        │
                                │ Request Limits       │
                                │ Error Boundary       │
                                │ Metrics              │
                                └──────────┬───────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
             ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
             │ PostgreSQL  │       │   Qdrant    │       │    Redis    │
             │             │       │             │       │             │
             │ Users       │       │ Vectors     │       │ RQ queues   │
             │ Departments │       │ Metadata    │       │ Rate limits │
             │ Documents   │       │ ACL filter  │       │             │
             │ Outbox      │       │             │       │             │
             │ Audit data  │       └─────────────┘       └──────┬──────┘
             └──────┬──────┘                                    │
                    │                                            │
                    │                                            ▼
                    │                                  ┌──────────────────┐
                    │                                  │   RQ Worker      │
                    │                                  │                  │
                    │                                  │ Ingestion        │
                    │                                  │ Deletion         │
                    │                                  │ Maintenance      │
                    │                                  │ Reconciliation   │
                    │                                  │ Outbox dispatch  │
                    │                                  └─────────┬────────┘
                    │                                            │
                    │                                            ▼
                    │                                  ┌──────────────────┐
                    │                                  │ Shared Storage   │
                    │                                  │                  │
                    │                                  │ Uploaded files  │
                    │                                  └──────────────────┘
                    │
                    └─────────────────────────────────────────────────────
```

The API, worker, and scheduler communicate with infrastructure over the Docker Compose network.

Only the API is host-published in the hardened Compose configuration.

---

## Security Model

The central security requirement is:

> A user must never receive document content they are not authorized to access.

Authorization is enforced by application logic and storage/retrieval controls. The LLM is never treated as a security boundary.

The request flow is:

```text
Client
  ↓
JWT authentication
  ↓
Determine authorized departments
  ↓
Database authorization checks
  ↓
Qdrant department filter
  ↓
Retrieve only authorized vectors
  ↓
Validate retrieved document state and department assignment
  ↓
Optional reranking
  ↓
Build authorized context
  ↓
Send context to LLM
  ↓
Return answer
```

### Department authorization

```text
Admin user
    ↓
Unrestricted access

Regular user with department
    ↓
Only that department's documents

Regular user without department
    ↓
No department-scoped documents
```

Authorization is applied before vector retrieval rather than being deferred until after an LLM response is generated.

---

## Document Model

Documents can be associated with multiple departments.

```text
Document
   │
   ├── Engineering
   ├── Finance
   └── HR
```

This allows one stored document to be shared across departments without duplicating the document record.

Document lifecycle states include:

```text
UPLOADED
    ↓
PROCESSING
    ↓
INDEXED
```

Failure and deletion states are handled explicitly:

```text
PROCESSING → FAILED
INDEXED    → DELETING → deleted
```

Processing and deletion timestamps are tracked so stale work can be detected by reconciliation.

---

## Document Lifecycle & Consistency

The document lifecycle is designed so that PostgreSQL remains the durable source of truth for workflow state.

### Upload

```text
Validate upload
    ↓
Write file to storage
    ↓
Create DB document
    ↓
Create ingestion outbox event
    ↓
Record audit information
    ↓
Commit transaction
```

Redis/RQ availability is not required for the upload transaction to remain durable because dispatch is driven from the PostgreSQL outbox.

### Deletion

```text
DELETE request
    ↓
Mark document DELETING
    ↓
Create deletion outbox event
    ↓
Commit transaction
    ↓
Outbox dispatcher
    ↓
RQ deletion job
    ├── Delete Qdrant vectors
    ├── Delete stored file
    └── Delete DB document
```

### Reconciliation

The maintenance job identifies stale documents and safely transitions them back into actionable states.

Reconciliation does not directly enqueue Redis/RQ jobs. It writes durable outbox work and allows the dispatcher to handle enqueueing.

This keeps recovery durable even when Redis is temporarily unavailable.

---

## RAG Pipeline

The RAG path is designed around authorization-first retrieval.

```text
User query
    ↓
Authenticate user
    ↓
Determine authorized departments
    ↓
Generate query embedding
    ↓
Qdrant semantic search with department filter
    ↓
Validate retrieved chunks
    ↓
Validate document existence
    ↓
Validate current department assignments
    ↓
Validate lifecycle state
    ↓
Rerank candidates
    ↓
Build bounded context
    ↓
Call Groq LLM
    ↓
Return grounded response
```

The retrieval service performs defense-in-depth checks rather than trusting vector metadata alone.

---

## API Hardening

The API includes multiple operational and security controls.

### Network perimeter

Production Compose exposes only:

```text
127.0.0.1:8001 → API container:8000
```

PostgreSQL, Qdrant, and Redis are internal-only:

```text
postgres:5432
qdrant:6333
redis:6379
```

### Request security

Implemented controls include:

- Trusted host validation
- CORS policy
- Security response headers
- Production HSTS
- Request body size enforcement
- Login rate limiting
- Upload/query rate limiting
- Structured request IDs
- Structured JSON error responses
- Generic internal-error responses
- Production API documentation disabled

Production documentation endpoints are disabled:

```text
/docs
/redoc
/openapi.json
```

---

## Health & Readiness

The application exposes separate liveness and dependency checks.

### Liveness

```bash
curl http://127.0.0.1:8001/health
```

Expected:

```json
{"status":"ok","environment":"production"}
```

### Readiness

```bash
curl http://127.0.0.1:8001/ready
```

The readiness endpoint checks required dependencies and returns HTTP 503 when one or more dependencies are unavailable.

### Qdrant health

```bash
curl http://127.0.0.1:8001/health/qdrant
```

### Metrics

```bash
curl http://127.0.0.1:8001/metrics
```

The metrics endpoint exposes Prometheus-compatible application and runtime metrics.

---

## Observability

Application logs use structured JSON logging.

Request processing includes a request ID so related log entries can be correlated.

Typical request events include:

```text
http_request_started
http_request_completed
http_request_failed
```

Background processes emit structured events for:

```text
worker_started
worker_failed
scheduler_started
scheduler_failed
```

The project intentionally keeps the application logging namespace separate from framework-level Uvicorn/RQ output.

---

## Operational Metrics

The API exposes operational metrics including:

```text
secure_rag_http_requests_total
secure_rag_http_request_duration_seconds

secure_rag_documents_total

secure_rag_stale_documents_total

secure_rag_outbox_events_total
secure_rag_outbox_events_ready
secure_rag_outbox_pending_oldest_age_seconds

secure_rag_rq_queue_depth

secure_rag_metrics_collections_total
```

These metrics support the deployed Prometheus/Grafana observability
stack and provide operational monitoring and alert-oriented visibility.

Prometheus and Grafana are deployed as part of the production observability
stack. Prometheus scrapes the API metrics endpoint, and the observability
services are host-published only on localhost.

---

## Operations Runbook

The repository contains the operational runbook:

```text
docs/operations.md
```

It covers:

- production perimeter expectations
- health and readiness checks
- structured logs
- worker and scheduler operations
- application metrics
- stale document monitoring
- outbox monitoring
- queue monitoring
- API incidents
- dependency failures
- ingestion/deletion incidents
- restart procedures
- safe operational rules

---

## Project Structure

```text
secure-rag/
├── app/
│   ├── api/
│   │   ├── auth.py
│   │   ├── departments.py
│   │   ├── documents.py
│   │   └── query.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   ├── request_context.py
│   │   └── security.py
│   │
│   ├── db/
│   │   └── database.py
│   │
│   ├── models/
│   │   ├── department.py
│   │   ├── document.py
│   │   ├── document_department.py
│   │   ├── enums.py
│   │   ├── outbox.py
│   │   └── user.py
│   │
│   ├── rag/
│   │   ├── embeddings.py
│   │   ├── qdrant_store.py
│   │   └── ...
│   │
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── department.py
│   │   ├── document.py
│   │   ├── query.py
│   │   └── user.py
│   │
│   └── services/
│       ├── authorization.py
│       ├── document_service.py
│       ├── file_storage.py
│       ├── ingestion.py
│       ├── jobs.py
│       ├── outbox.py
│       ├── queue.py
│       ├── rate_limit.py
│       ├── reconciliation.py
│       ├── retrieval.py
│       └── ...
│
├── alembic/
├── docs/
│   └── operations.md
├── scripts/
│   ├── cron.py
│   ├── worker.py
│   └── ...
├── storage/
│   └── documents/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

`storage/documents/` is runtime application storage for uploaded documents.

`docs/operations.md` is repository documentation and is unrelated to runtime document storage.

---

## Running Locally

### Requirements

- Python 3.12+
- Docker
- Docker Compose

### Create a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

Create `.env` from `.env.example`.

```bash
cp .env.example .env
```

Do not commit `.env`.

Use strong, randomly generated secrets for production.

Example JWT secret generation:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Start the stack

```bash
docker compose up -d
```

### Verify service status

```bash
docker compose ps
```

The hardened Compose setup publishes only the API:

```text
127.0.0.1:8001 → API container:8000
```

The remaining services stay inside the Docker Compose network:

```text
PostgreSQL → postgres:5432
Qdrant     → qdrant:6333
Redis      → redis:6379
```

### Run migrations

```bash
alembic upgrade head
```

### Verify the API

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/ready
curl http://127.0.0.1:8001/health/qdrant
curl http://127.0.0.1:8001/metrics
```

In production configuration, interactive API documentation is disabled.

---

## Testing

The project uses pytest for unit, integration, reliability, and security testing.

Because PostgreSQL, Qdrant, Redis, and the shared storage path are containerized, the full test suite should be run in the application container environment.

On Fedora systems with SELinux enforcing:

```bash
docker run --rm \
  -v "$PWD:/app:Z" \
  --network secure-rag_default \
  -w /app \
  secure-rag-api \
  pytest -q
```

The test suite covers areas including:

- authentication
- authorization
- department isolation
- document lifecycle
- storage validation
- ingestion behavior
- deletion consistency
- reconciliation
- outbox dispatch
- rate limiting
- request size limits
- readiness checks
- error boundary behavior
- metrics
- operational process logging
- retrieval authorization

---

## Configuration Principles

The application configuration is environment-driven.

Important configuration areas include:

```text
APP_ENV
DEBUG
DATABASE_URL
QDRANT_URL
QDRANT_COLLECTION
REDIS_URL
STORAGE_PATH

JWT_ALGORITHM
JWT_SECRET
ACCESS_TOKEN_EXPIRE_MINUTES

LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
LLM_TIMEOUT_SECONDS

MAX_UPLOAD_SIZE_MB

UPLOAD_RATE_LIMIT_REQUESTS
UPLOAD_RATE_LIMIT_WINDOW_SECONDS

QUERY_RATE_LIMIT_REQUESTS
QUERY_RATE_LIMIT_WINDOW_SECONDS

RECONCILIATION_INTERVAL_SECONDS
RECONCILIATION_STALE_PROCESSING_MINUTES
RECONCILIATION_STALE_DELETING_MINUTES
```

Production configuration validation rejects unsafe combinations such as debug mode enabled, weak placeholder JWT secrets, localhost infrastructure URLs, and relative storage paths.

---

## Background Processing

RQ is used for asynchronous document and maintenance work.

Queues include:

```text
document-ingestion
document-maintenance
```

The worker executes jobs such as:

```text
ingest_document_job
delete_document_job
reconcile_stale_documents_job
dispatch_pending_outbox_job
```

The scheduler registers maintenance work on a five-minute interval by default.

The PostgreSQL outbox provides durable work intent between the database transaction and asynchronous queue dispatch.

---

## Durable Outbox

The outbox pattern prevents a successful database transaction from depending on Redis availability.

The sequence is:

```text
Database transaction
      ↓
Persist document state change
      ↓
Persist outbox event
      ↓
Commit
      ↓
Outbox dispatcher claims pending events
      ↓
Enqueue deterministic RQ job
      ↓
Mark event dispatched
```

The dispatcher uses database row locking so multiple dispatchers do not process the same event concurrently.

---

## Failure Handling

The RAG pipeline and document pipeline are designed for partial failure.

Examples include:

```text
Upload succeeds, Redis unavailable
    ↓
Outbox remains durable
    ↓
Dispatcher retries later
```

```text
Ingestion partially indexes vectors
    ↓
Failure detected
    ↓
Partial vector state is cleaned up
```

```text
Deletion starts
    ↓
Worker interrupted
    ↓
Document remains DELETING
    ↓
Reconciliation detects stale state
    ↓
Cleanup work is resumed
```

The goal is to prefer explicit, recoverable states over silent inconsistency.

---

## Storage

Uploaded documents are stored in the shared application storage volume.

Runtime path inside containers:

```text
/app/storage/documents
```

Storage protections include:

- supported-file validation
- PDF/TXT/DOCX support
- basename sanitization
- UUID-based stored filenames
- maximum upload size enforcement
- chunked file writes
- empty-file rejection
- signature validation
- cleanup of partially written files on failure

The storage filename is not treated as an authorization mechanism.

---

## Security Principles

The project follows these core principles:

1. Authorization is enforced outside the LLM.
2. Department filtering happens before semantic retrieval.
3. Database state is checked again before content is used.
4. Durable PostgreSQL state is preferred over transient queue state.
5. Background work is recoverable through reconciliation.
6. Internal infrastructure is not unnecessarily exposed to the host.
7. Production errors do not expose internal exception details.
8. Secrets are supplied through environment configuration and are never committed.
9. Operational metrics and logs are designed to avoid sensitive request payloads.
10. Security behavior is validated by automated tests rather than relying only on configuration.

---

## Development Workflow

Development follows a checkpoint-based workflow:

```text
Implement checkpoint
      ↓
Run targeted tests
      ↓
Run broader/full tests
      ↓
Verify runtime behavior
      ↓
Review git diff
      ↓
Focused commit
      ↓
Next checkpoint
```

This keeps each hardening step isolated and reviewable.

---

## Roadmap

```text
1. Core Application
       ✅ Complete

2. Authorization / Data Isolation
       ✅ Complete

3. Document Lifecycle & Consistency
       ✅ Complete

4. RAG Failure Handling
       ✅ Complete

5. API & Application Hardening
       ✅ Complete

6. Observability & Operations
       ✅ Complete
       ├── 6.1 Observability baseline
       ├── 6.2 Operational metrics
       ├── 6.3 Metrics hardening
       ├── 6.4 Alert-oriented metrics
       └── 6.5 Operational runbook

7. Security & Reliability Testing
       ✅ Complete
       ├── 7.1 Full test suite
       ├── 7.2 Production configuration validation
       ├── 7.3 PostgreSQL restore drill
       ├── 7.4 Document restore drill
       ├── 7.5 Qdrant restore drill
       └── 7.6 Remote backup restore drill

8. Production Deployment
       ✅ Complete
       ├── 8.1 Production Docker deployment
       ├── 8.2 Prometheus / Grafana observability
       └── 8.3 Remote backup archival and retention

9. Frontend
       ⬜ Not Started

10. Final Production Review
       🚧 In Progress
```

---

## Operational Documentation

See:

```text
docs/operations.md
```

That document is the operational reference for health checks, metrics, logs, incident response, restart procedures, and safe production operations.

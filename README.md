# Secure RAG

A production-oriented Retrieval-Augmented Generation (RAG) application with authentication, authorization, department-based document access, PostgreSQL, and Qdrant.

## Project Status

Currently implemented:

* FastAPI backend
* PostgreSQL database
* SQLAlchemy ORM
* Alembic migrations
* Qdrant vector database connection
* JWT authentication
* Argon2 password hashing
* Admin/user roles
* Department management
* Department-based document access model
* Document-to-department many-to-many relationship
* Protected API endpoints

RAG ingestion and retrieval are the next development stages.

## Architecture

```text
                    ┌──────────────┐
                    │    Client    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    └──────┬───────┘
                           │
                    Authentication
                           │
                    Authorization
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       ┌──────────────┐         ┌──────────────┐
       │  PostgreSQL  │         │    Qdrant    │
       │              │         │              │
       │ Users        │         │ Vectors      │
       │ Departments  │         │ Metadata     │
       │ Documents    │         │              │
       └──────────────┘         └──────────────┘
```

## Security Model

Authorization is enforced by the application before document retrieval.

The intended request flow is:

```text
User
 ↓
JWT authentication
 ↓
Determine authorized departments
 ↓
Filter document/vector retrieval
 ↓
Retrieve only authorized content
 ↓
Send authorized context to LLM
 ↓
Generate response
```

The LLM is **not** used as the security boundary.

## Current Data Model

### Users

Users have:

* email
* password hash
* role
* department
* creation timestamp

Roles currently include:

* `admin`
* `user`

### Departments

Departments represent organizational access boundaries.

Examples:

* Engineering
* Finance
* HR

### Documents

Documents contain:

* filename
* storage path
* uploader
* processing status
* creation timestamp

Documents can be associated with multiple departments.

```text
Document
   │
   ├── Engineering
   ├── Finance
   └── HR
```

This allows a document to be shared across departments without duplicating the document record.

## Project Structure

```text
secure-rag/
├── app/
│   ├── api/
│   │   ├── auth.py
│   │   ├── departments.py
│   │   └── documents.py
│   │
│   ├── core/
│   │   ├── config.py
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
│   │   └── user.py
│   │
│   ├── rag/
│   │   └── vector_store.py
│   │
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── department.py
│   │   ├── document.py
│   │   └── user.py
│   │
│   └── services/
│       └── document_service.py
│
├── alembic/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Running Locally

### Requirements

* Python 3.12+
* Docker
* Docker Compose

### Create virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Start infrastructure

```bash
docker compose up -d
```

The development environment uses:

```text
FastAPI    → http://127.0.0.1:8001
PostgreSQL → localhost:5433
Qdrant     → http://localhost:6333
```

### Run migrations

```bash
alembic upgrade head
```

### Start FastAPI

```bash
uvicorn app.main:app --reload --port 8001
```

API documentation:

```text
http://127.0.0.1:8001/docs
```

## Environment Variables

Create `.env` from `.env.example`.

Do **not** commit `.env`.

The JWT secret should be a strong randomly generated value.

Example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Development Roadmap

### Completed

* [x] Project structure
* [x] Docker infrastructure
* [x] PostgreSQL setup
* [x] Qdrant setup
* [x] Database migrations
* [x] JWT authentication
* [x] Password hashing
* [x] Admin authorization
* [x] Department model
* [x] Document model
* [x] Document-department relationship

### Next

* [ ] Normal user authorization tests
* [ ] Actual file upload
* [ ] Object storage integration
* [ ] Document text extraction
* [ ] Text cleaning and normalization
* [ ] Chunking
* [ ] Embedding generation
* [ ] Qdrant collection/index setup
* [ ] Department-filtered vector retrieval
* [ ] RAG query pipeline
* [ ] LLM integration
* [ ] Document citations
* [ ] Background ingestion workers
* [ ] Security/integration test suite
* [ ] Frontend

## Security Principle

The core security requirement is:

> A user must never receive document content they are not authorized to access.

Department authorization must be applied **before vector retrieval**, not after the LLM generates an answer.

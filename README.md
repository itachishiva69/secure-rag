# Secure RAG

A production-oriented, department-aware Retrieval-Augmented Generation (RAG) application built with FastAPI, PostgreSQL, Qdrant, Redis, RQ, local document storage, JWT authentication, Argon2 password hashing, and a Groq OpenAI-compatible LLM.

The project is intentionally developed as a production-style backend rather than as a minimal RAG demo. Security, authorization, document lifecycle consistency, background processing, failure handling, observability, testing, and operational hardening are treated as first-class concerns.

---

## Project Status

The core backend and operational foundation are implemented.

Current progress:

```text
1. Core Application                    ✅ Complete
2. Authorization / Data Isolation      ✅ Complete
3. Document Lifecycle & Consistency    ✅ Complete
4. RAG Failure Handling                ✅ Complete
5. API & Application Hardening         ✅ Complete
6. Observability & Operations          🚧 In Progress
7. Security & Reliability Testing      🚧 Partial
8. Production Deployment               ⬜ Not Started
9. Frontend                            ⬜ Not Started
10. Final Production Review             ⬜ Not Started
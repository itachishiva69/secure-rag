# Secure RAG Operations Runbook

## Purpose

This document describes the operational signals, checks, and recovery actions for the Secure RAG application.

The application consists of:

- FastAPI API
- PostgreSQL
- Qdrant
- Redis
- RQ worker
- RQ maintenance scheduler
- durable PostgreSQL outbox
- shared application storage

Production service communication between PostgreSQL, Qdrant, Redis, the worker, scheduler, and API occurs over the Docker Compose network.

Only the API is host-published.

---

## Production Service Perimeter

Expected production host exposure:

```text
127.0.0.1:8001 -> API container:8000
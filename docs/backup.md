# Secure RAG Backup Operations

## Purpose

This document describes the local backup, remote archival, integrity
verification, retention, and recovery workflow for Secure RAG.

The backup model is:

```text
PostgreSQL
    |
    +-- authoritative application metadata/state

Application document storage
    |
    +-- original uploaded documents

Qdrant
    |
    +-- derived vector/index state

Redis / RQ
    |
    +-- transient queue state
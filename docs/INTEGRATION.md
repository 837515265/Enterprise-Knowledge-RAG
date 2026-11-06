# Backend-neutral integration notes

[Home](../README.md) · [中文首页](../README.zh-CN.md) · [Reproducibility](REPRODUCIBILITY.md)

> **Design proposal, not a shipped adapter.** The original enterprise Java platform is not distributed in the public repository. This document outlines a small, implementation-neutral integration boundary that developers can implement in Java, Python, Node.js or another stack without copying private business code.

## Components

- **Management UI:** Existing Vue knowledge-base, file, chunk, strategy, chat, and graph pages. API/auth configuration is application-specific.
- **Platform adapter (not included):** Authenticates users, handles knowledge-base metadata and file upload/storage, enforces permissions, and forwards AI requests.
- **AI engine:** Existing Python FastAPI parsing, indexing, retrieval, and graph modules.
- **External services:** MySQL, Elasticsearch, Redis, Neo4j, OCR/LLM endpoints, file storage.

A public standalone demo will need an adapter and a simple public file-storage implementation.

## Existing Python endpoints

These routes are described in [python-service/README.md](../python-service/README.md); inspect their current request models before integrating:

| Route | Purpose |
| --- | --- |
| `POST /api/v1/parse/files` | Parse one file by knowledge-base and file-node IDs |
| `GET /api/v1/parse/tasks/{task_id}` | Inspect an asynchronous parse job |
| `POST /api/v1/parse/files:batch-submit` | Submit multiple single-file parse tasks |
| `POST /api/v1/index/files` | Rebuild/index a file |
| `POST /api/v1/index/chunks` | Incrementally update chunk index entries |
| `POST /api/v1/retrieve/query` | Retrieve candidate evidence for a query |

Example request for retrieval (field names from the existing service docs):

```json
{
  "kb_id": 1024,
  "query": "What are the eligibility requirements?",
  "top_k": 5
}
```

Do **not** assume the Python API alone implements login, tenants, file uploads or the complete Vue UI contract.

## Suggested adapter responsibilities

1. **Identity and authorization:** Authenticate callers; validate every knowledge-base and document access.
2. **File lifecycle:** Upload and store a document, assign a stable file ID, provide a controlled download mechanism.
3. **AI orchestration:** Call parse/index/retrieve endpoints; poll task state, handle errors, and pass request IDs.
4. **Result mapping:** Translate retrieval and evidence structures into the frontend's expected response models.
5. **Audit:** Record changes and access events without logging secrets or private document content.
6. **Deployment security:** Keep API tokens on the server side, restrict service-to-service endpoints, and sanitize sample config.

## Public adapter acceptance criteria

- A fresh machine can upload one licensed sample PDF, index it and ask a question.
- The UI displays a result with a verifiable source reference.
- No company-specific Maven artifact, internal host, data source, or credentials are required.
- Unauthorized users cannot fetch or query another knowledge base.
- Integration can be tested with dummy credentials and local storage.

This is a roadmap for a clean public adapter, **not** a claim that these steps currently work end to end.

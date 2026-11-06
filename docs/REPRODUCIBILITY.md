# Reproducibility and local setup status

[Home](../README.md) · [Algorithm map](ALGORITHMS.md) · [Integration](INTEGRATION.md)

This document separates **checked-in source** from **external dependencies** and **missing artifacts**. It is based on file inspection as of 2026-11-06, not a successful clean-machine installation.

## Public source inventory

| Component | Present in repository | External requirements | Status |
| --- | --- | --- | --- |
| Python FastAPI parsing/retrieval | `python-service/src/danbao_poc`, Dockerfile, Compose | MySQL, Elasticsearch 7.x, Neo4j 5.x, Redis, OCR/LLM endpoints, file center | Source/container config present; full setup not verified |
| Vue management UI | Vue components, package manifests, Vite config | Node 14.x, npm ≥ 8.3, platform API/auth adapter | Code present; references an absent build script |
| Generic API adapter | [Interface notes](INTEGRATION.md) only | A new, independently licensed implementation | Not yet implemented |
| UI screenshots | Four images under `assets/screenshots` | None to view | Present |

The organization-specific Java implementation was removed from the proposed public tree because it was not authorized for redistribution. **Deleting current files does not remove them from historical commits**, which must be handled separately before promoting this repository.

## Observed blockers

1. `knowledge-web/package.json` invokes `node ./build/scripts/check-env.js` from `preinstall`, `predev` and `prebuild`, but that script is not in the tracked tree.
2. `python-service/README.md` still refers to local PowerShell helper scripts, yet no `python-service/scripts/` directory is tracked.
3. An older Python deployment document mentions `uv.lock` and a different Compose service layout. The checked-in Dockerfile uses `pip install` and copies source/Cypher files; the current Compose starts only `app-rag-doc`.
4. Python API and Vue UI are not an independently working full stack without a platform metadata/auth/file adapter.
5. No public end-to-end benchmark or verified clean-install result is currently included.

These are source-tree observations, **not runtime test results**.

## Source reading order

1. [Parsing, chunking and retrieval code](../python-service/src/danbao_poc/).
2. [Algorithms and evaluation design](ALGORITHMS.md).
3. [Vue knowledge-management pages](../knowledge-web/src/views/knowledge/).
4. [Backend-neutral adapter requirements](INTEGRATION.md).
5. [Four UI screenshots](../assets/screenshots/).

## Checklist for a reproducible community release

- [ ] Confirm that the remaining Python, Vue and screenshot assets can legally be published.
- [ ] Remove unauthorized source from **all relevant Git history and refs** using an appropriately reviewed procedure, with a private backup; verify no public fork/cached copy still exposes it.
- [ ] Audit checked-in configs/docs for internal addresses, credentials, customer information and binary licenses. Rotate any exposed live credentials.
- [ ] Select an appropriate LICENSE only after checking all rights.
- [ ] Restore or replace the missing Vue environment-check script and verify a Node 14 installation.
- [ ] Update Python setup/deployment documentation and remove unavailable script references.
- [ ] Implement a clean platform adapter and local file storage.
- [ ] Provide a sanitized demo Compose configuration, licensed toy documents and expected output.
- [ ] Add automated unit/integration tests and CI.
- [ ] Publish retrieval, reranking and citation benchmarks with reproducible baselines.

For installation questions, [open an issue](https://github.com/837515265/Enterprise-Knowledge-RAG/issues) with sanitized steps and logs. Never post API keys or internal host addresses.

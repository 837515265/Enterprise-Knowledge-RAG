# Reproducibility and local setup status

[Home](../README.md) · [Algorithm map](ALGORITHMS.md)

This page separates **checked-in code** from **external dependencies** and **missing artifacts**. It is based on a repository inspection as of 2026-11-06, not on a successfully executed full-stack installation.

## Component inventory

| Component | In repository | External requirement | Current status |
| --- | --- | --- | --- |
| Python FastAPI parsing / retrieval | `python-service/src/danbao_poc`, Dockerfile, Compose | MySQL, Elasticsearch 7.x, Neo4j 5.x, Redis, OCR/LLM endpoints, file center | Source and container config present; complete external setup not verified |
| Java 8 knowledge platform | Maven modules, controllers, entities, SQL resources | Internal Maven parent `com.ludan:central-platform` and enterprise libraries/services | Not independently buildable without organization dependencies |
| Vue admin UI | Vite config, Vue components, package manifests | Node 14.x, npm ≥ 8.3, platform APIs and auth | References a missing environment-check script |
| Screenshots | Four files under `assets/screenshots` | None for viewing | Available |

The Python deployment file `python-service/docker-compose.yml` starts one application service. It does **not** provision all backend databases, OCR servers, or the enterprise platform.

## Verified-by-inspection blockers

1. `knowledge-web/package.json` defines `preinstall`, `predev`, and `prebuild` scripts which call `node ./build/scripts/check-env.js`. That file is **not present** in the current tracked file tree.
2. `python-service/README.md` references `scripts/start-local.ps1`, `scripts/test-local.ps1`, and `scripts/stop-local.ps1`, but the tracked file tree contains no `python-service/scripts/` directory.
3. `python-service/deploy/README-docker-compose.md` references `uv.lock` and scripts not present in the checked-in snapshot, and describes an older deployment layout. The actual `python-service/Dockerfile` uses `pip install` and copies `src` and `cypher`.
4. A full local Java installation requires an external Maven parent POM and `com.ludan` artifacts; simply running `mvn clean install` from a public checkout is not guaranteed to succeed.
5. The repository does not publish an automated end-to-end test suite, benchmark results, or a complete sample-data setup.

These are repository-file observations. Actual builds and runtime behavior remain **unverified**.

## What can be inspected without connecting to company systems?

- Parsing and chunking implementation: [Python source](../python-service/src/danbao_poc/).
- API contracts and Java platform orchestration: [Java source](../java-service/app-knowledge-service/src/main/java/).
- Frontend components and knowledge-management pages: [web source](../knowledge-web/src/views/knowledge/).
- Algorithms and possible evaluation methodology: [ALGORITHMS.md](ALGORITHMS.md).
- Product UI: [screenshots](../assets/screenshots/).

## For maintainers: checklist for a community-runnable release

- [ ] Confirm rights to publicly distribute enterprise code, assets, and documentation.
- [ ] Audit tracked configuration and documentation for credentials, network endpoints, internal hostnames, customer information, and proprietary binaries. If a real secret was exposed, rotate it; deleting the current file does not remove Git history.
- [ ] Choose a LICENSE only after clarifying ownership and third-party component licenses.
- [ ] Restore or remove broken `build/scripts/check-env.js` references, then verify Node 14 installation.
- [ ] Reconcile Python deployment documentation with the current Dockerfile/Compose and remove unavailable script references.
- [ ] Provide a sanitized `docker-compose.demo.yml` (or equivalent) that uses public dependencies and no internal file center.
- [ ] Supply a licensed toy document set, a sample indexing command, a query command, and expected output.
- [ ] Add unit/integration tests and CI; document a clean-machine test result.
- [ ] Run a retrieval and citation benchmark with published baselines and metrics.

## Reporting installation issues

Open a [GitHub Issue](https://github.com/837515265/Enterprise-Knowledge-RAG/issues) with the component, environment versions, reproduction steps, and sanitized logs. **Never post secrets or internal network addresses in an issue.**

# Changelog

## 1.0.0

First production-hardened release.

### Added
- `/healthz` endpoint, structured request logging with no applicant data or secrets, and a `Dockerfile` that runs as a
  non-root user with a health check.
- Per-client rate limiting (429), a concurrency cap (503), a request body size cap (413), a pipeline timeout and a
  Claude call timeout, all configurable through `AGENTLEDGER_*` environment variables.
- Security headers on every response, including a strict Content-Security-Policy. The page's CSS and JavaScript moved
  to separate files to allow it.
- Input validation with ranges, lengths and normalisation for every field.
- A much larger test suite (126 tests, 99% coverage), type checking with mypy, a dependency vulnerability audit, a Docker
  build and smoke test in CI, Dependabot, and project docs (`SECURITY.md`, `CONTRIBUTING.md`).

### Changed
- The server's own `ANTHROPIC_API_KEY` is now ignored unless `AGENTLEDGER_SERVER_LLM=true`. Previously anyone able to
  reach the server could spend it.
- Pipeline failures now show a generic message instead of the internal exception text.
- The interactive API docs page (`/docs`) is disabled so the strict CSP can hold. `/openapi.json` is still served.
- The front end shows specific messages for validation errors, rate limits, a busy server and a dropped connection.

### Fixed
- A request containing `NaN` crashed the server with a 500 while building the validation error.
- Validation errors could echo a submitted API key back in the response.
- Oversized bodies sent without a `Content-Length` header returned a generic 400.

## 0.1.0

Initial demo: five agents, streaming dashboard, ablation of each agent's contribution.

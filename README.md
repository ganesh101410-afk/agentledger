# AgentLedger: multi-agent loan underwriting and fraud copilot

[![CI](https://github.com/ganesh101410-afk/agentledger/actions/workflows/ci.yml/badge.svg)](https://github.com/ganesh101410-afk/agentledger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A FinTech project built around one question: **what did each AI agent actually contribute to the decision?**

Five agents evaluate a loan application. The dashboard streams their work live, shows how much risk each one added or
removed, and shows whether the decision would have changed without it.

> **Demo only.** All applicants, watchlist names, thresholds and scoring weights are fictional and illustrative. Do not
> use this to make real lending decisions. See [Limitations](#limitations-and-responsible-use).

## The agents

| Agent | Job | Contribution |
|---|---|---|
| KYC Agent | Identity document, name/selfie match, age, address | Risk points; can force a REFER or DECLINE |
| Credit Risk Agent | Score, debt-to-income, tenure, loan-to-income, APR and payment | Risk points; prices the offer |
| Fraud Detection Agent | Device and IP location, application velocity, email domain age | Risk points |
| Compliance Agent | Sanctions watchlist (fuzzy match), restricted jurisdictions and purposes, AML threshold | Risk points; can force a DECLINE |
| Underwriter Agent | Combines the evidence, ranks the drivers, runs the ablation, writes the memo | Decision and explanation |

```
            +--> Credit Risk ---+
 KYC  ----> +--> Fraud ---------+--> Underwriter --> decision + memo
            +--> Compliance ----+
 stage 1        stage 2 (parallel)      stage 3
```

## How contribution is measured

- Every application starts at a risk score of **50**. Each specialist agent returns signed risk points (negative lowers
  risk). The score is clamped to 0-100: **0-35 approve, 36-60 refer to a human, 61-100 decline**.
- A **hard stop** (for example a probable sanctions match) overrides the score.
- **Ablation:** the policy is re-run with each agent removed. If the outcome flips, that agent was *decisive*. This is
  the headline metric, and it is why the sanctions sample is declined even though its score alone would not decline it.

## Where the LLM fits

The decision is **deterministic policy, not an LLM output**. If a Claude API key is available, Claude writes the decision
memo from the agents' findings; without one, a rule-based memo is used. If the Claude call fails or times out, the
decision is unaffected. A key can come from the visitor (pasted into the page, used for that one request, never stored
or logged) or from the server (`ANTHROPIC_API_KEY` together with `AGENTLEDGER_SERVER_LLM=true`; off by default so a
public deployment cannot spend your key by accident).

## Quick start

```bash
make install   # creates .venv and installs requirements-dev.txt
make run       # serves on http://localhost:8765 (loads .env if present)
```

Or with Docker:

```bash
docker build -t agentledger .
docker run --rm -p 8000:8000 agentledger     # http://localhost:8000
```

Open the page and pick a sample applicant:

| Sample | Outcome | What it shows |
|---|---|---|
| Priya Raman | Approve | Every agent lowers risk |
| Marcus Webb | Refer | Thin margins; KYC verification is what keeps it from declining |
| Elena Marchetti | Decline | Good credit, but the fraud agent is decisive |
| Ivan P. Sokolov | Decline | Excellent credit, but a compliance hard stop |

## Configuration

All settings are optional environment variables; see [.env.example](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Server-side key for memos. Ignored unless `AGENTLEDGER_SERVER_LLM=true` |
| `AGENTLEDGER_SERVER_LLM` | `false` | Allow the server's own key to be used |
| `AGENTLEDGER_MODEL` | `claude-sonnet-5-5` | Model used for memos |
| `AGENTLEDGER_RATE_LIMIT_PER_MIN` | `20` | POSTs per client per minute before 429 (`0` disables) |
| `AGENTLEDGER_MAX_CONCURRENT` | `25` | Simultaneous runs before 503 |
| `AGENTLEDGER_PIPELINE_TIMEOUT` | `45` | Seconds before a run is aborted |
| `AGENTLEDGER_LLM_TIMEOUT` | `20` | Seconds before the Claude call is abandoned |
| `AGENTLEDGER_MAX_BODY_BYTES` | `16384` | Request body size cap (413) |
| `AGENTLEDGER_ALLOW_PACING` | `true` | `false` removes the demo delay between agents |
| `AGENTLEDGER_TRUST_PROXY` | `false` | Use the last `X-Forwarded-For` hop as the client IP. Only behind your own proxy |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PORT` | `8000` | Port inside the Docker image |

## API

| Method and path | Purpose |
|---|---|
| `GET /healthz` | Liveness: `{"status": "ok", "version": "..."}` |
| `GET /api/samples` | The fictional sample applicants |
| `GET /api/graph` | Agents and the stage order |
| `POST /api/underwrite` | Run the pipeline, return every event and the final decision |
| `POST /api/underwrite/stream` | The same, as server-sent events |
| `GET /openapi.json` | Machine-readable schema |

```bash
curl -s localhost:8765/api/samples | python3 -c "import sys, json; print(json.dumps({'application': json.load(sys.stdin)[0]['application'], 'pacing': False}))" \
  | curl -s -X POST localhost:8765/api/underwrite -H 'Content-Type: application/json' -d @- | python3 -m json.tool | head -20
```

Request body: `{"application": {...}, "api_key": "optional", "pacing": true}`. Every application field is validated (see
`core/models.py`); unknown fields are rejected. Stream events are `stage_start`, `agent_start`, `agent_done`, then
`complete` (or `error`).

| Status | Meaning |
|---|---|
| 413 | Body too large |
| 422 | Invalid input; `detail` lists `{field, message}`, never the submitted values |
| 429 | Rate limited; see `Retry-After` |
| 503 | Server at capacity; see `Retry-After` |

## Development

```bash
make check     # lint + format check, mypy, tests with a 95% coverage floor, pip-audit (what CI runs)
make test      # just the tests
make format    # auto-fix lint and formatting
make smoke     # end-to-end check against a running server
```

CI runs the checks on Python 3.11, 3.12 and 3.13, audits dependencies, builds the Docker image, starts the container
and runs the smoke test against it. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add an agent.

```
main.py              FastAPI app, endpoints, error handling, request admission
core/agents/         the five agents
core/decision.py     deterministic scoring policy and ablation
core/orchestrator.py staged async pipeline with timeout and cancellation
core/security.py     rate limiter, body limit and security headers
core/models.py       validated request model and agent result types
static/              the dashboard (no inline scripts, so a strict CSP applies)
tests/               126 tests
```

## Deploying

The Docker image runs as a non-root user, honours `PORT`, and exposes `/healthz` for health checks, so it fits any
container host. Before exposing it publicly:

1. Serve it over **HTTPS** (a visitor's pasted API key travels with their request).
2. If you run behind a reverse proxy, set `AGENTLEDGER_TRUST_PROXY=true` so rate limits apply per real client.
3. Leave `AGENTLEDGER_SERVER_LLM=false` unless you intend to pay for memos for every visitor.
4. Rate limits are in memory and per process. With several instances, rate limit at the proxy as well.

See [SECURITY.md](SECURITY.md) for the full list of protections and their limits.

## Limitations and responsible use

- Applicants, watchlist names, jurisdictions, thresholds and scoring weights are illustrative. The "estimated analyst
  minutes" per agent are an assumption, not a measurement.
- Real lending needs far more: credit bureau and identity-verification integrations, a maintained sanctions and PEP
  screening service, fair-lending testing (for example ECOA/Regulation B disparate impact analysis), adverse-action
  notices (FCRA), model risk management and validation, audit logging, and human oversight. None of that is here.
- There is no authentication and nothing is stored.
- The small delay between agents in the UI is demo pacing so you can watch the stages. It is excluded from each agent's
  reported compute time (`pacing: false`, or `AGENTLEDGER_ALLOW_PACING=false`, removes it).

## License

[MIT](LICENSE)

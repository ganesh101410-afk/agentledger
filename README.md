# AgentLedger: multi-agent loan underwriting and fraud copilot

A FinTech project built around one question: **what did each AI agent actually contribute to the decision?**

Five agents evaluate a loan application. The dashboard streams their work live, then shows how much risk each
one added or removed, and whether the decision would have changed without it.

## The agents

| Agent | Job | Contribution |
|---|---|---|
| KYC Agent | Identity document, name/selfie match, age, address | Risk points, can force a REFER or DECLINE |
| Credit Risk Agent | Score, debt-to-income, tenure, loan-to-income, APR and payment | Risk points, prices the offer |
| Fraud Detection Agent | Device and IP location, application velocity, email domain age | Risk points |
| Compliance Agent | Sanctions watchlist (fuzzy match), restricted jurisdictions and purposes, AML threshold | Risk points, can force a DECLINE |
| Underwriter Agent | Combines the evidence, ranks the drivers, runs the ablation, writes the memo | Decision and explanation |

```
            +--> Credit Risk ---+
 KYC  ----> +--> Fraud ---------+--> Underwriter --> decision + memo
            +--> Compliance ----+
 stage 1        stage 2 (parallel)      stage 3
```

## How contribution is measured

- Every application starts at a risk score of **50**. Each specialist agent returns signed risk points
  (negative lowers risk). The score is clamped to 0-100: **0-35 approve, 36-60 refer to a human, 61-100 decline**.
- A **hard stop** (for example a probable sanctions match) overrides the score.
- **Ablation:** the policy is re-run with each agent removed. If the outcome flips, that agent was *decisive*.
  This is the headline metric, and it is why the sanctions sample is declined even though its score alone would
  not decline it.

## Where the LLM fits

The decision is **deterministic policy, not an LLM output**. If you provide an Anthropic API key (in the UI, or the
`ANTHROPIC_API_KEY` environment variable), Claude writes the decision memo from the agents' findings. Without a key
a rule-based memo is used. If the Claude call fails, the decision is unaffected. Set `AGENTLEDGER_MODEL` to change the
model (default `claude-sonnet-5-5`).

## Run it

```bash
make install   # creates .venv and installs requirements-dev.txt
make run       # serves on http://localhost:8765 (loads .env if present)
```

Optional: copy `.env.example` to `.env` and add `ANTHROPIC_API_KEY` for Claude-written memos.

Open http://localhost:8765 and pick a sample applicant:


| Sample | Outcome | What it shows |
|---|---|---|
| Priya Raman | Approve | Every agent lowers risk |
| Marcus Webb | Refer | Thin margins; KYC verification is what keeps it from declining |
| Elena Marchetti | Decline | Good credit, but the fraud agent is decisive |
| Ivan P. Sokolov | Decline | Excellent credit, but a compliance hard stop |

Tests: `make test`. Lint: `make lint`. Format: `make format`.

## API

- `GET /api/samples`, `GET /api/graph`
- `POST /api/underwrite`: runs the pipeline and returns all events
- `POST /api/underwrite/stream`: the same as server-sent events

## Notes and limits

- All applicants, watchlist names and thresholds are fictional demo data, not legal or credit advice.
- "Estimated analyst time" per agent is an assumption used for illustration, not a measurement.
- The small delay between agents in the UI is demo pacing so you can watch the stages; it is excluded from each
  agent's reported compute time (`pacing: false` on the API disables it).

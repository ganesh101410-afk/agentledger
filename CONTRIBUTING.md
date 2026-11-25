# Contributing

Thanks for taking a look. Bug reports, fixes and new ideas are welcome.

## Set up

```bash
make install     # creates .venv and installs requirements-dev.txt
make run         # http://localhost:8765
```

## Before you open a pull request

```bash
make check       # ruff lint and format check, mypy, tests with a 95% coverage floor, pip-audit
```

This is exactly what CI runs, plus a Docker build and smoke test. `make format` fixes lint and formatting problems
automatically.

## Guidelines

- **Add or adjust a test with every behaviour change.** Tests live in `tests/`; the existing ones show the style.
- **Keep the decision deterministic.** Agents may add risk points and hard stops in `core/agents/`, and `core/decision.py`
  turns them into an outcome. The LLM only explains. Please do not let model output change a decision.
- **Do not log applicant data or API keys**, and do not put either in error responses.
- **Adding an agent:** create a class in `core/agents/` that extends `Agent`, register it in `core/orchestrator.py`
  (`AGENTS` and `STAGES`), add it to `RISK_AGENTS` in `core/decision.py` if it scores risk, and add the matching
  label to the front end.
- Keep changes focused, and describe what you changed and why in the pull request.

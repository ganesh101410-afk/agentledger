# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Do not open a public issue for security problems. You will get an acknowledgement within a
few days. Because this is a demo project maintained by one person, fixes are best effort.

## What the app does to protect itself

- **Input validation.** Every field has a type, range and length limit. Country codes, names and loan purposes are
  normalised and checked. Unknown fields, `NaN` and infinity are rejected.
- **Validation errors never echo input**, so a mistyped request cannot reflect an API key or other secret back.
- **API keys are used for one request only.** A key typed into the page is sent over your connection with that request,
  used to call Anthropic, and then dropped. It is never stored, logged or returned. Applicant data is also not logged.
- **The server's own key is opt-in.** `ANTHROPIC_API_KEY` is ignored unless `AGENTLEDGER_SERVER_LLM=true`, so a public
  deployment cannot be used to spend your key by accident.
- **Limits.** Per-client rate limiting (429), a concurrency cap (503), a request body size cap (413), a pipeline timeout
  and a Claude call timeout.
- **Browser hardening.** A strict Content-Security-Policy (no inline scripts), `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS over HTTPS, and `no-store` on API responses.
- **The LLM cannot change a decision.** Decisions come from deterministic rules. Claude only writes the memo, and its
  input is treated as data, never as instructions.
- **Supply chain.** Dependencies are audited with `pip-audit` in CI and updated through Dependabot. The container runs
  as a non-root user.

## What it does not do

- There is no authentication, and no persistence of any kind. Rate limits are in memory and per process, so running
  several instances multiplies the effective limit. Use a shared limiter at your proxy if you scale out.
- Pasting an API key into a web page is only as safe as the connection. **Serve it over HTTPS** and use a key with a low
  spend limit.
- `AGENTLEDGER_TRUST_PROXY=true` trusts the last `X-Forwarded-For` hop. Enable it only behind a proxy you control.
- It is a demonstration with fictional data and illustrative rules. It is **not** suitable for real credit decisions.
  See the limitations section of the README.

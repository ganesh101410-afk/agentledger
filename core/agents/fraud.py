from __future__ import annotations

from ..models import AgentResult, Application, Context, Finding
from .base import Agent


class FraudAgent(Agent):
    id = "fraud"
    name = "Fraud Detection Agent"
    role = "Scans device, network and velocity signals"
    manual_minutes = 20

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        home = app.residence_country.upper()
        device = app.device_country.upper()
        ip = app.ip_country.upper()
        findings: list[Finding] = []

        if device == home:
            findings.append(Finding("Device location", f"Device is in {device}, matching residence.", -1, "positive"))
        else:
            findings.append(
                Finding("Device location mismatch", f"Device is in {device} but applicant resides in {home}.", 12, "critical")
            )

        if ip == home:
            findings.append(Finding("Network location", f"IP address resolves to {ip}, matching residence.", -1, "positive"))
        else:
            findings.append(
                Finding("IP location mismatch", f"IP resolves to {ip} but applicant resides in {home}.", 10, "critical")
            )

        n = app.apps_last_30d
        if n <= 2:
            findings.append(Finding("Application velocity", f"{n} application(s) in the last 30 days.", -1, "positive"))
        elif n <= 4:
            findings.append(Finding("Elevated velocity", f"{n} applications in the last 30 days.", 5, "warning"))
        else:
            findings.append(Finding("Burst of applications", f"{n} applications in the last 30 days.", 14, "critical"))

        d = app.email_domain_age_days
        if d >= 365:
            findings.append(Finding("Email domain age", f"Domain registered {d} days ago.", -1, "positive"))
        elif d >= 30:
            findings.append(Finding("Young email domain", f"Domain registered only {d} days ago.", 3, "warning"))
        else:
            findings.append(Finding("Newly created email domain", f"Domain registered only {d} days ago.", 10, "critical"))

        flags = sum(1 for f in findings if f.severity in ("warning", "critical"))
        summary = "No fraud indicators." if flags == 0 else f"{flags} fraud indicator{'s' if flags != 1 else ''} detected."
        return self.result(
            summary=summary,
            findings=findings,
            confidence=0.93 if flags == 0 else min(0.97, 0.7 + 0.07 * flags),
            metrics={"flags": flags},
        )

from __future__ import annotations

from ..models import AgentResult, Application, Context, Finding, HardStop
from .base import Agent


class KYCAgent(Agent):
    id = "kyc"
    name = "KYC Agent"
    role = "Verifies identity, age and address"
    manual_minutes = 12

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        findings: list[Finding] = []
        hard_stop = None

        if app.age < 18:
            findings.append(Finding("Underage applicant", f"Age {app.age} is below the legal minimum of 18.", 30, "critical"))
            hard_stop = HardStop("DECLINE", "Applicant is under 18")
        else:
            findings.append(Finding("Age requirement met", f"Applicant is {app.age}.", 0, "neutral"))

        if app.id_document_valid:
            findings.append(Finding("ID document verified", "Document passed authenticity and expiry checks.", -3, "positive"))
        else:
            findings.append(Finding("ID document failed", "Document failed authenticity or expiry checks.", 25, "critical"))
            hard_stop = hard_stop or HardStop("REFER", "Identity document could not be verified")

        if app.id_name_matches:
            findings.append(Finding("Name matches ID", "Application name matches the document and selfie check.", -2, "positive"))
        else:
            findings.append(
                Finding("Name / selfie mismatch", "Name or face on the ID does not match the applicant.", 15, "warning")
            )

        if app.address_verified:
            findings.append(Finding("Address verified", "Address confirmed against a utility or bureau record.", -2, "positive"))
        else:
            findings.append(Finding("Address unverified", "No supporting record found for the stated address.", 8, "warning"))

        clean = all(f.severity in ("positive", "neutral") for f in findings)
        summary = "Identity fully verified." if clean else "Identity verification raised concerns."
        return self.result(
            summary=summary,
            findings=findings,
            confidence=0.97 if clean else 0.82,
            hard_stop=hard_stop,
        )

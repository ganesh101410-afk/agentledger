from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..models import AgentResult, Application, Context, Finding, HardStop
from .base import Agent

# Demo data only: fictional names, and a short illustrative jurisdiction list. Not legal advice.
WATCHLIST = ["Ivan Petrovich Sokolov", "Amara Nwosu-Beltran", "Tomas Reyes Valdivia"]
RESTRICTED_JURISDICTIONS = {"KP", "IR", "SY", "CU"}
RESTRICTED_PURPOSES = {"gambling", "crypto_trading"}
REPORTING_THRESHOLD = 10_000


def _tokens(name: str) -> list[str]:
    return re.sub(r"[^a-z\s]", " ", name.lower()).split()


def name_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    score = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    if ta[0] == tb[0] and ta[-1] == tb[-1]:  # same first and last name, middle name differs or is an initial
        score = max(score, 0.92)
    return score


class ComplianceAgent(Agent):
    id = "compliance"
    name = "Compliance Agent"
    role = "Screens sanctions, jurisdiction and AML rules"
    manual_minutes = 15

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        findings: list[Finding] = []
        hard_stop = None

        best_name, best = max(((n, name_similarity(app.applicant_name, n)) for n in WATCHLIST), key=lambda x: x[1])
        if best >= 0.85:
            findings.append(
                Finding("Sanctions watchlist match", f"Name matches '{best_name}' ({best:.0%} similarity).", 40, "critical")
            )
            hard_stop = HardStop("DECLINE", f"Probable sanctions match against '{best_name}'")
        elif best >= 0.70:
            findings.append(
                Finding(
                    "Possible watchlist match",
                    f"Name is similar to '{best_name}' ({best:.0%}); needs analyst review.",
                    12,
                    "warning",
                )
            )
        else:
            findings.append(Finding("No watchlist hits", "No sanctions or PEP list match.", -2, "positive"))

        if app.residence_country.upper() in RESTRICTED_JURISDICTIONS:
            findings.append(
                Finding(
                    "Restricted jurisdiction",
                    f"Residence country {app.residence_country.upper()} is on the restricted list.",
                    30,
                    "critical",
                )
            )
            hard_stop = hard_stop or HardStop("DECLINE", "Applicant resides in a restricted jurisdiction")

        if app.loan_purpose in RESTRICTED_PURPOSES:
            findings.append(
                Finding("Restricted loan purpose", f"'{app.loan_purpose}' is not an eligible use of funds.", 15, "warning")
            )

        if app.loan_amount >= REPORTING_THRESHOLD:
            findings.append(
                Finding("Large-value transaction", f"${app.loan_amount:,.0f} requires enhanced record-keeping.", 0, "neutral")
            )

        flagged = any(f.severity in ("warning", "critical") for f in findings)
        return self.result(
            summary="Compliance concerns found." if flagged else "Cleared all compliance screens.",
            findings=findings,
            confidence=0.96 if hard_stop else (0.8 if flagged else 0.95),
            hard_stop=hard_stop,
            metrics={"watchlist_best_match": round(best, 2)},
        )

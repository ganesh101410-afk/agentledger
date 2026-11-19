from __future__ import annotations

from ..models import AgentResult, Application, Context, Finding
from .base import Agent


def apr_for_score(score: int) -> float:
    if score >= 740:
        return 7.5
    if score >= 700:
        return 10.5
    if score >= 660:
        return 14.0
    if score >= 620:
        return 19.0
    return 25.0


def monthly_payment(principal: float, apr_pct: float, months: int) -> float:
    r = apr_pct / 100 / 12
    return principal * r / (1 - (1 + r) ** -months)


class CreditRiskAgent(Agent):
    id = "credit"
    name = "Credit Risk Agent"
    role = "Scores repayment capacity and affordability"
    manual_minutes = 25

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        apr = apr_for_score(app.credit_score)
        payment = monthly_payment(app.loan_amount, apr, app.term_months)
        monthly_income = app.annual_income / 12
        dti = (app.monthly_debt + payment) / monthly_income
        lti = app.loan_amount / app.annual_income

        s = app.credit_score
        if s >= 760:
            sd, ss = -16, "positive"
        elif s >= 720:
            sd, ss = -11, "positive"
        elif s >= 680:
            sd, ss = -5, "positive"
        elif s >= 640:
            sd, ss = 6, "warning"
        elif s >= 600:
            sd, ss = 14, "warning"
        else:
            sd, ss = 22, "critical"

        if dti < 0.20:
            dd, ds = -6, "positive"
        elif dti < 0.36:
            dd, ds = -2, "positive"
        elif dti < 0.43:
            dd, ds = 8, "warning"
        elif dti < 0.50:
            dd, ds = 16, "critical"
        else:
            dd, ds = 24, "critical"

        e = app.employment_years
        if e >= 5:
            ed, es = -3, "positive"
        elif e >= 2:
            ed, es = 0, "neutral"
        elif e >= 1:
            ed, es = 3, "warning"
        else:
            ed, es = 8, "warning"

        if lti > 0.6:
            ld, ls = 8, "warning"
        elif lti <= 0.25:
            ld, ls = -2, "positive"
        else:
            ld, ls = 0, "neutral"

        findings = [
            Finding("Credit score", f"Bureau score {s}.", sd, ss),
            Finding("Debt-to-income", f"{dti:.0%} after this loan (existing debt plus a ${payment:,.0f}/mo payment).", dd, ds),
            Finding("Employment tenure", f"{e:g} years at current employer.", ed, es),
            Finding("Loan-to-income", f"Loan is {lti:.0%} of annual income.", ld, ls),
        ]
        total = sum(f.delta for f in findings)
        summary = (
            "Strong repayment capacity."
            if total <= -15
            else "Moderate repayment capacity."
            if total < 10
            else "Weak repayment capacity."
        )
        return self.result(
            summary=summary,
            findings=findings,
            confidence=0.9 if e >= 1 else 0.78,
            metrics={
                "apr": apr,
                "monthly_payment": round(payment, 2),
                "dti": round(dti, 3),
                "loan_to_income": round(lti, 3),
            },
        )

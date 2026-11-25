import asyncio

import pytest

from core.agents.compliance import ComplianceAgent, name_similarity
from core.agents.credit import CreditRiskAgent, apr_for_score, monthly_payment
from core.agents.fraud import FraudAgent
from core.agents.kyc import KYCAgent
from core.agents.underwriter import UnderwriterAgent
from core.decision import APPROVE_MAX, REFER_MAX, ablation, classify, decide
from core.models import AgentResult, Application, Context, HardStop


def run(agent, app: Application) -> AgentResult:
    return asyncio.run(agent.run(app, Context()))


def make_app(sample, **overrides) -> Application:
    return Application(**{**sample, **overrides})


def result(agent_id: str, delta: float, hard: HardStop | None = None) -> AgentResult:
    return AgentResult(agent_id, agent_id.title(), "", "", delta, 1.0, [], hard_stop=hard)


def deltas(r: AgentResult) -> dict[str, float]:
    return {f.label: f.delta for f in r.findings}


# decision policy


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "APPROVE"),
        (APPROVE_MAX, "APPROVE"),
        (APPROVE_MAX + 0.1, "REFER"),
        (REFER_MAX, "REFER"),
        (REFER_MAX + 0.1, "DECLINE"),
        (100, "DECLINE"),
    ],
)
def test_classify_boundaries(score, expected):
    assert classify(score) == expected


def test_score_is_clamped_to_0_100():
    assert decide([result("kyc", -500)])["score"] == 0
    assert decide([result("kyc", 500)])["score"] == 100


def test_decline_hard_stop_overrides_a_low_score():
    out = decide([result("kyc", -30), result("compliance", 0, HardStop("DECLINE", "sanctions"))])
    assert out["outcome"] == "DECLINE" and out["score"] < APPROVE_MAX and out["hard_stops"]


def test_refer_hard_stop_upgrades_approve_but_never_downgrades_decline():
    stop = HardStop("REFER", "id")
    assert decide([result("kyc", -30, stop)])["outcome"] == "REFER"
    assert decide([result("kyc", 30, stop)])["outcome"] == "DECLINE"


def test_ablation_ignores_the_removed_agents_hard_stop():
    rows = {r["agent_id"]: r for r in ablation([result("kyc", -30), result("compliance", 0, HardStop("DECLINE", "x"))])}
    assert rows["compliance"]["flips"] and rows["compliance"]["outcome_without"] == "APPROVE"
    assert not rows["kyc"]["flips"]


def test_non_risk_agents_do_not_affect_the_score():
    assert decide([result("underwriter", 99)])["score"] == 50


# agents


def test_kyc_underage_is_declined_and_failed_id_is_referred(sample):
    assert run(KYCAgent(), make_app(sample, age=17)).hard_stop.outcome == "DECLINE"
    failed = run(KYCAgent(), make_app(sample, id_document_valid=False))
    assert failed.hard_stop.outcome == "REFER" and deltas(failed)["ID document failed"] == 25


def test_kyc_mismatch_and_unverified_address_add_risk(sample):
    r = run(KYCAgent(), make_app(sample, id_name_matches=False, address_verified=False))
    assert deltas(r)["Name / selfie mismatch"] == 15 and deltas(r)["Address unverified"] == 8
    assert r.confidence < 0.9 and r.hard_stop is None


def test_monthly_payment_matches_the_amortisation_formula():
    assert monthly_payment(10_000, 12, 12) == pytest.approx(888.49, abs=0.01)


@pytest.mark.parametrize("score,apr", [(800, 7.5), (740, 7.5), (739, 10.5), (700, 10.5), (660, 14.0), (620, 19.0), (500, 25.0)])
def test_apr_tiers(score, apr):
    assert apr_for_score(score) == apr


@pytest.mark.parametrize("score,delta", [(780, -16), (730, -11), (690, -5), (650, 6), (610, 14), (550, 22)])
def test_credit_score_bands(sample, score, delta):
    assert deltas(run(CreditRiskAgent(), make_app(sample, credit_score=score)))["Credit score"] == delta


def test_credit_debt_to_income_worsens_with_debt(sample):
    low = run(CreditRiskAgent(), make_app(sample, monthly_debt=0))
    high = run(CreditRiskAgent(), make_app(sample, monthly_debt=6000))
    assert deltas(low)["Debt-to-income"] < 0 < deltas(high)["Debt-to-income"]
    assert high.metrics["dti"] > low.metrics["dti"] and high.risk_delta > low.risk_delta


def test_credit_employment_and_loan_to_income(sample):
    new_hire = run(CreditRiskAgent(), make_app(sample, employment_years=0.2, loan_amount=90_000))
    assert deltas(new_hire)["Employment tenure"] == 8 and deltas(new_hire)["Loan-to-income"] == 8
    assert new_hire.confidence < 0.8


@pytest.mark.parametrize("apps,delta", [(0, -1), (2, -1), (3, 5), (4, 5), (5, 14), (40, 14)])
def test_fraud_velocity_bands(sample, apps, delta):
    r = run(FraudAgent(), make_app(sample, apps_last_30d=apps))
    assert [d for label, d in deltas(r).items() if "elocity" in label or "Burst" in label] == [delta]


@pytest.mark.parametrize("days,delta", [(5000, -1), (365, -1), (364, 3), (30, 3), (29, 10), (0, 10)])
def test_fraud_email_domain_age_bands(sample, days, delta):
    r = run(FraudAgent(), make_app(sample, email_domain_age_days=days))
    assert [d for label, d in deltas(r).items() if "omain" in label] == [delta]


def test_fraud_location_mismatches_and_clean_case(sample):
    clean = run(FraudAgent(), make_app(sample))
    assert clean.metrics["flags"] == 0 and clean.summary == "No fraud indicators."
    bad = run(FraudAgent(), make_app(sample, device_country="ro", ip_country="ng"))
    assert bad.metrics["flags"] == 2 and "2 fraud indicators" in bad.summary


def test_name_similarity():
    assert name_similarity("Ivan Petrovich Sokolov", "ivan petrovich sokolov") == pytest.approx(1.0)
    assert name_similarity("Ivan P. Sokolov", "Ivan Petrovich Sokolov") >= 0.85
    assert name_similarity("Ivan Petrovich Sokolow", "Ivan Petrovich Sokolov") >= 0.85
    assert name_similarity("Priya Raman", "Ivan Petrovich Sokolov") < 0.7
    assert name_similarity("", "Ivan") == 0.0 and name_similarity("123", "Ivan") == 0.0


def test_compliance_sanctions_hit_is_a_decline(sample):
    r = run(ComplianceAgent(), make_app(sample, applicant_name="Ivan P. Sokolov"))
    assert r.hard_stop.outcome == "DECLINE" and deltas(r)["Sanctions watchlist match"] == 40


def test_compliance_clean_applicant(sample):
    r = run(ComplianceAgent(), make_app(sample))
    assert r.hard_stop is None and r.summary == "Cleared all compliance screens."


def test_compliance_restricted_jurisdiction_purpose_and_large_value(sample):
    r = run(ComplianceAgent(), make_app(sample, residence_country="kp", loan_purpose="gambling", loan_amount=25_000))
    assert r.hard_stop.outcome == "DECLINE"
    assert deltas(r)["Restricted jurisdiction"] == 30 and deltas(r)["Restricted loan purpose"] == 15
    assert deltas(r)["Large-value transaction"] == 0


def test_compliance_possible_match_band_asks_for_review(sample, monkeypatch):
    monkeypatch.setattr("core.agents.compliance.name_similarity", lambda a, b: 0.75)
    r = run(ComplianceAgent(), make_app(sample))
    assert r.hard_stop is None and deltas(r)["Possible watchlist match"] == 12


def test_underwriter_memo_names_decisive_agent_or_says_none(sample):
    app = make_app(sample)
    memo = UnderwriterAgent._template_memo(app, {"outcome": "APPROVE", "score": 10, "hard_stops": []}, [], ["Credit Risk Agent"])
    assert "depends on Credit Risk Agent" in memo
    none = UnderwriterAgent._template_memo(app, {"outcome": "DECLINE", "score": 90, "hard_stops": ["x: y"]}, [], [])
    assert "No single agent was decisive" in none and "hard stop" in none

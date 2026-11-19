from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class Application(BaseModel):
    applicant_name: str
    age: int = Field(ge=0, le=120)
    residence_country: str = "US"
    id_document_valid: bool = True
    id_name_matches: bool = True
    address_verified: bool = True
    annual_income: float = Field(gt=0)
    monthly_debt: float = Field(ge=0)
    credit_score: int = Field(ge=300, le=850)
    employment_years: float = Field(ge=0)
    loan_amount: float = Field(gt=0)
    term_months: int = Field(ge=6, le=120)
    loan_purpose: str = "debt_consolidation"
    device_country: str = "US"
    ip_country: str = "US"
    apps_last_30d: int = Field(default=1, ge=0)
    email_domain_age_days: int = Field(default=2000, ge=0)


@dataclass
class Finding:
    label: str
    detail: str
    delta: float
    severity: str  # positive | neutral | warning | critical


@dataclass
class HardStop:
    outcome: str  # DECLINE | REFER
    reason: str


@dataclass
class AgentResult:
    agent_id: str
    name: str
    role: str
    summary: str
    risk_delta: float
    confidence: float
    findings: list[Finding]
    hard_stop: HardStop | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    compute_ms: float = 0.0
    manual_minutes: float = 0.0
    used_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Context:
    results: dict[str, AgentResult] = field(default_factory=dict)
    api_key: str | None = None

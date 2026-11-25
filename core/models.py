from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class Application(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0, le=120)
    residence_country: str = "US"
    id_document_valid: bool = True
    id_name_matches: bool = True
    address_verified: bool = True
    annual_income: float = Field(gt=0, le=100_000_000, allow_inf_nan=False)
    monthly_debt: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)
    credit_score: int = Field(ge=300, le=850)
    employment_years: float = Field(ge=0, le=80, allow_inf_nan=False)
    loan_amount: float = Field(gt=0, le=10_000_000, allow_inf_nan=False)
    term_months: int = Field(ge=6, le=120)
    loan_purpose: str = "debt_consolidation"
    device_country: str = "US"
    ip_country: str = "US"
    apps_last_30d: int = Field(default=1, ge=0, le=1000)
    email_domain_age_days: int = Field(default=2000, ge=0, le=36_500)

    @field_validator("applicant_name", mode="before")
    @classmethod
    def _clean_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = " ".join(_CONTROL_CHARS.sub(" ", value).split())
        return value

    @field_validator("residence_country", "device_country", "ip_country", mode="before")
    @classmethod
    def _country_code(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().upper()
            if not re.fullmatch(r"[A-Z]{2}", value):
                raise ValueError("must be a 2-letter country code such as US")
        return value

    @field_validator("loan_purpose", mode="before")
    @classmethod
    def _purpose(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = re.sub(r"[\s-]+", "_", value.strip().lower())
            if not re.fullmatch(r"[a-z][a-z_]{0,39}", value):
                raise ValueError("must be 1-40 letters, e.g. home_improvement")
        return value


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

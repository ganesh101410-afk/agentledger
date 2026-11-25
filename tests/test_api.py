import json

import pytest

import main
from core import __version__
from core.models import Application


def parse_sse(text: str) -> list[dict]:
    return [json.loads(line[5:]) for line in text.split("\n\n") if line.startswith("data:")]


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "version": __version__}


def test_index_and_static_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "AgentLedger" in page.text
    for path in ("/static/app.js", "/static/styles.css", "/static/favicon.svg"):
        assert client.get(path).status_code == 200


def test_page_has_no_inline_script(client):
    assert "<script>" not in client.get("/").text


def test_samples_and_graph(client):
    assert len(client.get("/api/samples").json()) == 4
    graph = client.get("/api/graph").json()
    assert graph["stages"] == [["kyc"], ["credit", "fraud", "compliance"], ["underwriter"]]
    assert {a["id"] for a in graph["agents"]} == {"kyc", "credit", "fraud", "compliance", "underwriter"}


def test_underwrite_returns_decision(client, body):
    out = client.post("/api/underwrite", json=body).json()
    assert out["complete"]["decision"]["outcome"] == "APPROVE"
    assert out["events"][-1]["type"] == "complete"


def test_stream_emits_ordered_server_sent_events(client, body):
    with client.stream("POST", "/api/underwrite/stream", json=body) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse("".join(response.iter_text()))
    types = [e["type"] for e in events]
    assert types[0] == "stage_start" and types[-1] == "complete"
    assert types.count("agent_start") == types.count("agent_done") == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("age", -1),
        ("age", 500),
        ("credit_score", 900),
        ("credit_score", 100),
        ("annual_income", 0),
        ("annual_income", 1e12),
        ("monthly_debt", -5),
        ("loan_amount", 0),
        ("term_months", 1),
        ("term_months", 1000),
        ("applicant_name", ""),
        ("applicant_name", "x" * 101),
        ("residence_country", "USA"),
        ("device_country", "<script>"),
        ("ip_country", "1"),
        ("loan_purpose", "<img src=x onerror=alert(1)>"),
        ("apps_last_30d", 10_000),
        ("id_document_valid", "maybe"),
    ],
)
def test_invalid_fields_are_rejected_without_echoing_input(client, body, field, value):
    body["application"][field] = value
    response = client.post("/api/underwrite", json=body)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail and detail[0]["field"] == field
    if isinstance(value, str) and len(value) > 3:
        assert value not in response.text  # submitted text is never echoed back


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_a_clean_422_not_a_crash(client, sample, literal):
    raw = json.dumps({"application": {**sample, "annual_income": "@@"}, "pacing": False}).replace('"@@"', literal)
    response = client.post("/api/underwrite", content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "annual_income"


def test_unknown_fields_are_rejected(client, body):
    body["application"]["is_admin"] = True
    assert client.post("/api/underwrite", json=body).status_code == 422
    assert client.post("/api/underwrite", json={**body, "extra": 1}).status_code == 422


def test_validation_errors_never_echo_the_api_key(client, body):
    body["api_key"] = ["sk-ant-SUPERSECRET"]
    response = client.post("/api/underwrite", json=body)
    assert response.status_code == 422
    assert "SUPERSECRET" not in response.text


def test_overlong_api_key_is_rejected(client, body):
    body["api_key"] = "k" * 301
    assert client.post("/api/underwrite", json=body).status_code == 422


def test_malformed_json_is_a_422(client):
    response = client.post("/api/underwrite", content="{not json", headers={"content-type": "application/json"})
    assert response.status_code == 422


def test_inputs_are_normalised(sample):
    app = Application(
        **{
            **sample,
            "applicant_name": "  Priya\n\tRaman\x00  ",
            "residence_country": " us ",
            "device_country": "gb",
            "loan_purpose": "Home Improvement",
        }
    )
    assert app.applicant_name == "Priya Raman"
    assert (app.residence_country, app.device_country) == ("US", "GB")
    assert app.loan_purpose == "home_improvement"


def test_blank_api_key_is_treated_as_missing(client, body):
    body["api_key"] = "   "
    assert client.post("/api/underwrite", json=body).status_code == 200


def test_docs_ui_is_disabled_but_openapi_is_available(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").json()["info"]["version"] == __version__


def test_unknown_route_is_404(client):
    assert client.get("/nope").status_code == 404


def test_unexpected_error_returns_generic_500_and_frees_the_slot(client, body, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("internal detail that must not leak")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "run_pipeline", boom)
    response = client.post("/api/underwrite", json=body)
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}

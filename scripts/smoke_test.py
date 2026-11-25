"""End-to-end check against a running AgentLedger: python scripts/smoke_test.py [base_url]

Uses only the standard library so it can run anywhere, including CI against a container.
"""

import json
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
EXPECTED = {"clean": "APPROVE", "borderline": "REFER", "fraud": "DECLINE", "sanctions": "DECLINE"}


def call(path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.headers, response.read()


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


headers, body = call("/healthz")
check(json.loads(body)["status"] == "ok", "healthz reports ok")

headers, body = call("/")
check(b"AgentLedger" in body, "index page is served")
check("script-src 'self'" in headers.get("Content-Security-Policy", ""), "Content-Security-Policy header is set")
check(headers.get("X-Content-Type-Options") == "nosniff", "X-Content-Type-Options header is set")

_, body = call("/api/samples")
samples = json.loads(body)
check({s["id"] for s in samples} == set(EXPECTED), "all sample applicants are available")

for sample in samples:
    _, body = call("/api/underwrite", {"application": sample["application"], "pacing": False})
    outcome = json.loads(body)["complete"]["decision"]["outcome"]
    check(outcome == EXPECTED[sample["id"]], f"{sample['id']}: {outcome}")

print("smoke test passed")

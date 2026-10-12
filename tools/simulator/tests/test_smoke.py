"""Behavioral tests for the smoke run (A-2 to A-9).

Only the HTTP boundary (httpx.MockTransport) and the token prompt (an injected
callable) are substituted; target validation and the phases run for real.
"""

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from report_support import read_report, recorder

from tailtag_simulator.client import MAX_RESPONSE_BYTES
from tailtag_simulator.reports import RunReport
from tailtag_simulator.smoke import run_smoke

TOKEN = "hdr_SECRET-1.payload_SECRET-2.sig_SECRET-3"
USER_ID = 424242
BODY_MARKER = "LEAKY-BODY-MARKER"
SHA = "0123456789abcdef0123456789abcdef01234567"
DEPLOYMENT_ID = "123e4567-e89b-42d3-a456-426614174000"
EVIL = "https://evil.example"

STAGING_ORIGIN = "https://staging.tailtag.app"
LOCAL_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://host.docker.internal:8000",
]

IDENTITY_PATH = "/health/identity"
READY_PATH = "/health/ready"
ME_PATH = "/api/me/"

Responder = Callable[[], httpx.Response]


def identity_body(target: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = (
        {"source_sha": SHA, "deployment_id": DEPLOYMENT_ID, "environment": "staging"}
        if target == "staging"
        else {"source_sha": None, "deployment_id": None, "environment": None}
    )
    return {**body, **overrides}


def identity_ok(target: str) -> Responder:
    return lambda: httpx.Response(200, json=identity_body(target))


def me_body(user_id: object = USER_ID) -> dict[str, object]:
    return {"id": user_id, "display_name": BODY_MARKER}


def me_ok(user_id: object = USER_ID) -> Responder:
    return lambda: httpx.Response(200, json=me_body(user_id))


def origin_of(url: httpx.URL) -> str:
    port = f":{url.port}" if url.port else ""
    return f"{url.scheme}://{url.host}{port}"


@dataclass
class Server:
    """Scripted API. Hosts other than the expected origin answer anything with
    a valid-looking body, so a followed redirect or a stray request succeeds
    visibly instead of failing for an unrelated reason."""

    identity: list[Responder]
    me: list[Responder]
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    seen: dict[str, int] = field(default_factory=dict[str, int])

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if origin_of(request.url) == EVIL:
            return httpx.Response(200, json=me_body())
        if request.url.path == READY_PATH:
            return httpx.Response(200, json={"status": "ok"})
        script = {IDENTITY_PATH: self.identity, ME_PATH: self.me}.get(request.url.path)
        if script is None:
            return httpx.Response(404, text=BODY_MARKER)
        index = self.seen.get(request.url.path, 0)
        self.seen[request.url.path] = index + 1
        return script[min(index, len(script) - 1)]()


@dataclass
class Outcome:
    code: int
    lines: list[str]
    prompts: int
    requests: list[httpx.Request]

    def authorized(self) -> list[httpx.Request]:
        return [r for r in self.requests if "authorization" in r.headers]


def run(
    target: str,
    server: Server,
    *,
    base_url: str | None = None,
    token: str | Exception = TOKEN,
    report: RunReport | None = None,
) -> Outcome:
    lines: list[str] = []
    prompts: list[None] = []

    def prompt_token() -> str:
        prompts.append(None)
        if isinstance(token, Exception):
            raise token
        return token

    code = asyncio.run(
        run_smoke(
            target,
            base_url=base_url,
            prompt_token=prompt_token,
            emit=lines.append,
            transport=httpx.MockTransport(server.handle),
            report=report,
        )
    )
    return Outcome(code, lines, len(prompts), server.requests)


def healthy(target: str) -> Server:
    return Server(identity=[identity_ok(target)], me=[me_ok()])


def assert_no_leak(outcome: Outcome) -> None:
    output = "\n".join(outcome.lines)
    for secret in (TOKEN, str(USER_ID), BODY_MARKER, "SECRET"):
        assert secret not in output


def assert_failed_closed(outcome: Outcome) -> None:
    assert outcome.code == 1
    assert any("FAIL" in line for line in outcome.lines)
    assert_no_leak(outcome)


@pytest.mark.parametrize(
    ("target", "base_url", "origin"),
    [
        ("staging", None, STAGING_ORIGIN),
        ("local", None, "http://127.0.0.1:8000"),
        *[("local", url, url) for url in LOCAL_ORIGINS],
    ],
)
def test_happy_path_authenticates_only_after_identity_and_only_on_me(
    target: str, base_url: str | None, origin: str
) -> None:
    server = healthy(target)

    outcome = run(target, server, base_url=base_url)

    assert outcome.code == 0
    gate = (
        [IDENTITY_PATH, READY_PATH, IDENTITY_PATH]
        if target == "staging"
        else [IDENTITY_PATH] * 2
    )
    assert [r.url.path for r in outcome.requests[: len(gate)]] == gate
    assert [r.url.path for r in outcome.authorized()] == [ME_PATH] * 2
    assert {origin_of(r.url) for r in outcome.requests} == {origin}
    assert all(r.method == "GET" for r in outcome.requests)
    assert all(
        r.headers["authorization"] == f"Bearer {TOKEN}" for r in outcome.authorized()
    )
    assert all(
        r.url.path in {IDENTITY_PATH, READY_PATH}
        for r in outcome.requests
        if "authorization" not in r.headers
    )
    assert outcome.prompts == 1
    assert outcome.lines
    assert not any("FAIL" in line for line in outcome.lines)
    assert_no_leak(outcome)


def test_local_accepts_a_reported_source_sha() -> None:
    server = Server(
        identity=[
            lambda: httpx.Response(200, json=identity_body("local", source_sha=SHA))
        ],
        me=[me_ok()],
    )

    assert run("local", server).code == 0


@pytest.mark.parametrize(
    ("target", "base_url"),
    [
        ("production", None),
        ("development", None),
        ("Staging", None),
        ("LOCAL", None),
        ("", None),
        ("staging", STAGING_ORIGIN),
        ("staging", "https://example.test"),
        ("local", "https://staging.tailtag.app"),
        ("local", "http://127.0.0.1:8001"),
        ("local", "https://127.0.0.1:8000"),
        ("local", "http://127.0.0.1:8000/evil"),
        ("local", "http://127.0.0.1:8000.evil.example"),
        ("local", "http://evil.example:8000"),
    ],
)
def test_unknown_target_or_overridden_origin_is_rejected_before_any_request(
    target: str, base_url: str | None
) -> None:
    outcome = run(target, healthy("staging"), base_url=base_url)

    assert_failed_closed(outcome)
    assert outcome.requests == []
    assert outcome.prompts == 0


def identity_response(body: object, status: int = 200) -> Responder:
    return lambda: httpx.Response(status, json=body)


IDENTITY_FAILURES: dict[str, tuple[str, list[Responder]]] = {
    "non-200": ("staging", [lambda: httpx.Response(503, text=BODY_MARKER)]),
    "created-status": (
        "staging",
        [lambda: httpx.Response(201, json=identity_body("staging"))],
    ),
    "non-json": ("staging", [lambda: httpx.Response(200, text=BODY_MARKER)]),
    "json-list": ("staging", [identity_response([identity_body("staging")])]),
    "extra-key": (
        "staging",
        [identity_response(identity_body("staging", extra=BODY_MARKER))],
    ),
    "missing-key": (
        "staging",
        [identity_response({"source_sha": SHA, "environment": "staging"})],
    ),
    "second-read-differs-in-sha": (
        "staging",
        [
            identity_ok("staging"),
            identity_response(identity_body("staging", source_sha="f" * 40)),
        ],
    ),
    "second-read-differs-in-deployment": (
        "staging",
        [
            identity_ok("staging"),
            identity_response(
                identity_body("staging", deployment_id=str(uuid.UUID(int=1)))
            ),
        ],
    ),
    # Valid JSON padded with whitespace past the response cap.
    "oversized-body": (
        "staging",
        [
            lambda: httpx.Response(
                200,
                content=json.dumps(identity_body("staging"))
                + " " * (MAX_RESPONSE_BYTES + 1),
            )
        ],
    ),
    "second-read-fails": (
        "staging",
        [identity_ok("staging"), lambda: httpx.Response(500, text=BODY_MARKER)],
    ),
    "staging-reports-production": (
        "staging",
        [identity_response(identity_body("staging", environment="production"))],
    ),
    "staging-without-environment": (
        "staging",
        [identity_response(identity_body("staging", environment=None))],
    ),
    "staging-uppercase-sha": (
        "staging",
        [identity_response(identity_body("staging", source_sha=SHA.upper()))],
    ),
    "staging-short-sha": (
        "staging",
        [identity_response(identity_body("staging", source_sha=SHA[:39]))],
    ),
    "staging-null-sha": (
        "staging",
        [identity_response(identity_body("staging", source_sha=None))],
    ),
    "staging-uppercase-uuid": (
        "staging",
        [
            identity_response(
                identity_body("staging", deployment_id=DEPLOYMENT_ID.upper())
            )
        ],
    ),
    "staging-non-uuid-deployment": (
        "staging",
        [identity_response(identity_body("staging", deployment_id="deploy-1"))],
    ),
    "staging-null-deployment": (
        "staging",
        [identity_response(identity_body("staging", deployment_id=None))],
    ),
    "local-reports-staging": (
        "local",
        [identity_response(identity_body("local", environment="staging"))],
    ),
    "local-reports-deployment": (
        "local",
        [identity_response(identity_body("local", deployment_id=DEPLOYMENT_ID))],
    ),
}


@pytest.mark.parametrize("case", IDENTITY_FAILURES)
def test_failed_identity_check_never_prompts_or_sends_credentials(case: str) -> None:
    target, identity = IDENTITY_FAILURES[case]
    server = Server(identity=identity, me=[me_ok()])

    outcome = run(target, server)

    assert_failed_closed(outcome)
    assert outcome.prompts == 0
    assert outcome.authorized() == []
    assert ME_PATH not in [r.url.path for r in outcome.requests]


MALFORMED_TOKENS = [
    "",
    "abc",
    "a.b",
    "a.b.c.d",
    "a..c",
    ".b.c",
    "a.b.",
    "a b.c.d",
    "a.b+x.c",
    "Bearer a.b.c",
    "a.b.c\r\nX-Injected: 1",
]


@pytest.mark.parametrize("token", MALFORMED_TOKENS)
def test_malformed_token_is_rejected_before_any_request_carries_it(
    token: str,
) -> None:
    outcome = run("staging", healthy("staging"), token=token)

    assert_failed_closed(outcome)
    assert outcome.prompts == 1
    assert outcome.authorized() == []
    assert ME_PATH not in [r.url.path for r in outcome.requests]


@pytest.mark.parametrize("error", [EOFError(), RuntimeError(), OSError()])
def test_unavailable_token_prompt_fails_closed(error: Exception) -> None:
    outcome = run("staging", healthy("staging"), token=error)

    assert_failed_closed(outcome)
    assert outcome.authorized() == []


ME_FAILURES: dict[str, list[Responder]] = {
    "unauthorized": [lambda: httpx.Response(401, json={"detail": BODY_MARKER})],
    "server-error": [lambda: httpx.Response(500, text=BODY_MARKER)],
    "created-status": [lambda: httpx.Response(201, json=me_body())],
    "non-json": [lambda: httpx.Response(200, text=BODY_MARKER)],
    "json-list": [lambda: httpx.Response(200, json=[me_body()])],
    "missing-id": [lambda: httpx.Response(200, json={"display_name": BODY_MARKER})],
    "zero-id": [me_ok(0)],
    "negative-id": [me_ok(-USER_ID)],
    "string-id": [me_ok(str(USER_ID))],
    "float-id": [me_ok(1.5)],
    "bool-id": [me_ok(True)],
    "null-id": [me_ok(None)],
    "ids-differ": [me_ok(USER_ID), me_ok(USER_ID + 1)],
    "second-unauthorized": [me_ok(), lambda: httpx.Response(401, text=BODY_MARKER)],
}


@pytest.mark.parametrize("case", ME_FAILURES)
def test_reconciliation_fails_unless_both_me_reads_agree_on_a_positive_id(
    case: str,
) -> None:
    server = Server(identity=[identity_ok("staging")], me=ME_FAILURES[case])

    outcome = run("staging", server)
    assert_failed_closed(outcome)
    if case in {"bool-id", "created-status"}:
        assert len(outcome.authorized()) == 1, (
            "invalid successful reply admitted another workload request"
        )
        assert "FAIL safety reason=correctness" in outcome.lines
    if case in {"unauthorized", "server-error", "second-unauthorized"}:
        assert not any(line.startswith("FAIL safety reason=") for line in outcome.lines)


def redirect(status: int, location: str) -> Responder:
    return lambda: httpx.Response(status, headers={"location": location})


REDIRECT_CASES = {
    "identity-first-cross-host": (
        IDENTITY_PATH,
        [redirect(302, f"{EVIL}{IDENTITY_PATH}"), identity_ok("staging")],
    ),
    "identity-second-cross-host": (
        IDENTITY_PATH,
        [identity_ok("staging"), redirect(307, f"{EVIL}{IDENTITY_PATH}")],
    ),
    "identity-same-host": (
        IDENTITY_PATH,
        [redirect(301, f"{STAGING_ORIGIN}{IDENTITY_PATH}x"), identity_ok("staging")],
    ),
    "me-first-cross-host": (
        ME_PATH,
        [redirect(307, f"{EVIL}{ME_PATH}"), me_ok()],
    ),
    "me-second-cross-host": (
        ME_PATH,
        [me_ok(), redirect(302, f"{EVIL}{ME_PATH}")],
    ),
    "me-same-host": (
        ME_PATH,
        [redirect(308, f"{STAGING_ORIGIN}{ME_PATH}x"), me_ok()],
    ),
}


@pytest.mark.parametrize("case", REDIRECT_CASES)
def test_redirects_fail_and_are_never_followed(case: str) -> None:
    path, script = REDIRECT_CASES[case]
    server = Server(
        identity=script if path == IDENTITY_PATH else [identity_ok("staging")],
        me=script if path == ME_PATH else [me_ok()],
    )

    outcome = run("staging", server)

    assert_failed_closed(outcome)
    assert {origin_of(r.url) for r in outcome.requests} == {STAGING_ORIGIN}
    assert all(not r.url.path.endswith("x") for r in outcome.requests)


@pytest.mark.parametrize("target", ["staging", "local"])
def test_reported_smoke_persists_verified_end_identity_without_changing_workload(
    tmp_path: Path, target: str
) -> None:
    report = recorder(tmp_path, config={"target": target})
    server = healthy(target)
    initial_requests: list[str] = []
    handle = server.handle

    def observed_handle(request: httpx.Request) -> httpx.Response:
        initial_requests.append(read_report(report.path)["outcome"])
        return handle(request)

    server.handle = observed_handle
    outcome = run(target, server, report=report)
    value = read_report(report.path)
    assert outcome.code == 0 and value["outcome"] == "passed"
    assert value["correctness"] == "passed"
    assert value["scenario"]["id"] == "smoke"
    assert value["scenario"]["consumes_randomness"] is False
    assert value["target"]["starting"] == {
        "value": identity_body(target),
        "reason": None,
    }
    assert value["target"]["final"] == {"value": identity_body(target), "reason": None}
    assert value["target"]["attribution"] == "verified"
    assert initial_requests[0] == "running"
    assert [request.url.path for request in outcome.authorized()] == [ME_PATH] * 2
    last_workload = max(
        index
        for index, request in enumerate(outcome.requests)
        if request.url.path == ME_PATH
    )
    assert all(
        request.url.path in {IDENTITY_PATH, READY_PATH}
        and "authorization" not in request.headers
        for request in outcome.requests[last_workload + 1 :]
    )
    assert len(outcome.requests[last_workload + 1 :]) >= (
        3 if target == "staging" else 2
    )
    assert outcome.prompts == 1
    assert_no_leak(outcome)
    text = report.path.read_text()
    assert not any(secret in text for secret in (TOKEN, BODY_MARKER, str(USER_ID)))
    assert value["limits"]["request_timeout"] == {
        "value": 10.0,
        "reason": None,
        "unit": "seconds",
        "scope": "per_request",
    }


@pytest.mark.parametrize("failure", ["target", "setup", "reconciliation"])
def test_reported_smoke_preserves_reached_evidence_and_sanitizes_failures(
    tmp_path: Path, failure: str
) -> None:
    report = recorder(tmp_path)
    server = healthy("staging")
    token: str | Exception = TOKEN
    if failure == "target":
        server.identity = [
            identity_response(identity_body("staging", environment="production"))
        ]
    elif failure == "setup":
        token = RuntimeError("SENTINEL-private-token-error")
    else:
        server.me = [me_ok(), me_ok(USER_ID + 1)]
    outcome = run("staging", server, token=token, report=report)
    value = read_report(report.path)
    assert outcome.code != 0 and value["outcome"] == (
        "aborted" if failure in {"target", "reconciliation"} else "failed"
    )
    reached_stage = "simulation" if failure == "reconciliation" else failure
    assert value["phases"][reached_stage]["status"] == (
        "not_reached" if failure == "target" else "failed"
    )
    if failure == "reconciliation":
        # Both profile successes are validated in the first workload stage.
        assert value["phases"]["reconciliation"]["status"] == "not_reached"
        assert value["safety"]["abort"]["reason"] == "correctness"
    if failure == "target":
        assert value["safety"]["preflight"]["failed"] == 1
        assert value["safety"]["abort"]["reason"] == "identity_mismatch"
        assert outcome.prompts == 0 and outcome.authorized() == []
    assert value["correctness"] == (
        "failed" if failure == "reconciliation" else "not_observed"
    )
    assert value["target"]["final"] == {"value": None, "reason": "not_observed"}
    assert "SENTINEL" not in report.path.read_text()
    assert value["phases"]["release"]["status"] == "not_applicable"

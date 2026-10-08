"""Independent literal #227 schema4 safety evidence, never built by production."""

from typing import Any

from report_support import DEPLOYMENT, SHA

POLICY: dict[str, object] = {
    "requests": 10000,
    "seconds": 900,
    "in_flight": 10,
    "population": 250,
    "final_requests": 1000,
    "final_seconds": 600,
    "poll_seconds": 10,
    "error_window_seconds": 10,
    "error_min_samples": 20,
    "error_percent": 50,
    "error_windows": 2,
}


def literal_safety() -> dict[str, Any]:
    return {
        "policy": dict(POLICY),
        "target": {
            "identity": {
                "source_sha": SHA,
                "deployment_id": DEPLOYMENT,
                "environment": "staging",
            },
            "evidence": "staging",
        },
        "preflight": {"checks": 1, "passed": 1, "failed": 0, "last": "passed"},
        "probes": {
            "checks": 0,
            "passed": 0,
            "failed": 0,
            "consecutive_failures": 0,
            "paused": False,
            "last": "unverified",
        },
        "execution": {
            "requests": 4,
            "ordinary_active": 0,
            "ordinary_peak": 1,
            "control_active": 0,
            "control_peak": 1,
            "elapsed_seconds": 6.0,
            "exhausted": None,
        },
        "finalization": {
            "started": False,
            "allowed": False,
            "requests": 0,
            "ordinary_active": 0,
            "ordinary_peak": 0,
            "control_active": 0,
            "control_peak": 0,
            "elapsed_seconds": 0.0,
            "exhausted": None,
            "reconciliation": "not_attempted",
            "retention": "not_attempted",
            "release": "not_attempted",
            "clerk_closure": "not_attempted",
        },
        "errors": {
            "closed_windows": 0,
            "qualifying_windows": 0,
            "consecutive_windows": 0,
            "current_completed": 2,
            "current_catastrophic": 0,
            "last_completed": 0,
            "last_catastrophic": 0,
        },
        "abort": None,
        "resources": {"monitoring": "unavailable"},
        "concurrency": {"ordinary_limit": 10, "control_limit": 1, "combined_limit": 11},
    }

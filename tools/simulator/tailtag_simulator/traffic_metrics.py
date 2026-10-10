"""Client-side attempt classes and exact latency percentiles per operation (#229)."""

import math
from array import array
from collections.abc import Sequence

OPERATIONS = ("auxiliary", "resolve", "confirm", "read")
CLASSES = (
    "success",
    "expected_rejection",
    "client_error",
    "server_error",
    "timeout",
    "transport_error",
    "injected",
)
RESPONSES = ("success", "expected_rejection", "client_error", "server_error")
PERCENTILES = (("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1.0))


def nearest_rank(sorted_samples: Sequence[float], q: float) -> float:
    """Return the sample at rank ceil(q*n); q is a fraction and 1.0 is the maximum."""
    # The epsilon keeps products such as 0.99 * 300 from rounding up a rank.
    rank = math.ceil(q * len(sorted_samples) - 1e-9)
    return sorted_samples[max(0, rank - 1)]


def classify_reply(status: int) -> str:
    if 200 <= status < 300:
        return "success"
    return "server_error" if 500 <= status < 600 else "client_error"


class OperationMeter:
    """Counts per class and latency samples; raw samples never leave the process."""

    def __init__(self) -> None:
        self.counts: dict[str, dict[str, int]] = {
            op: {outcome: 0 for outcome in CLASSES} for op in OPERATIONS
        }
        self.samples = {op: array("d") for op in OPERATIONS}

    def record(
        self, operation: str, outcome: str, milliseconds: float | None = None
    ) -> None:
        self.counts[operation][outcome] += 1
        if milliseconds is not None:
            self.samples[operation].append(milliseconds)

    def reject(self, operation: str) -> None:
        counts = self.counts[operation]
        if counts["client_error"] < 1:
            raise ValueError("no client error to reclassify")
        counts["client_error"] -= 1
        counts["expected_rejection"] += 1

    def attempts(self) -> dict[str, dict[str, int]]:
        result = {op: dict(counts) for op, counts in self.counts.items()}
        result["total"] = {
            outcome: sum(counts[outcome] for counts in self.counts.values())
            for outcome in CLASSES
        }
        return result

    def throughput(self, window_seconds: float) -> dict[str, float] | None:
        if window_seconds <= 0:
            return None
        return {
            name: sum(counts[outcome] for outcome in RESPONSES) / window_seconds
            for name, counts in self.attempts().items()
        }

    def latency_percentiles(self) -> dict[str, dict[str, object]]:
        pooled = sorted(value for samples in self.samples.values() for value in samples)
        groups = {op: sorted(samples) for op, samples in self.samples.items()}
        return {
            name: {
                "samples": len(ordered),
                **{
                    key: (
                        {
                            "value": round(nearest_rank(ordered, q), 3),
                            "reason": None,
                        }
                        if ordered
                        else {"value": None, "reason": "not_observed"}
                    )
                    for key, q in PERCENTILES
                },
            }
            for name, ordered in (*groups.items(), ("total", pooled))
        }

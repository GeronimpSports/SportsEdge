"""Strict probability-calibration gate from held-out reliability evidence.

The evaluator consumes already-produced held-out reliability bins. It does not
fit or alter Model_P. Calibration intercept/slope are estimated with grouped
binomial logistic recalibration against logit(mean predicted probability), and
ECE is the sample-weighted absolute reliability error.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, isfinite, log
from typing import Any, Mapping


@dataclass(frozen=True)
class CalibrationTruthGate:
    n: int
    intercept: float | None
    slope: float | None
    ece: float | None
    pass_gate: bool
    reason: str
    contract: str = "SPORTSEDGE_CALIBRATION_TRUTH_GATE_V1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pass"] = payload.pop("pass_gate")
        return payload


def _finite(value: Any, error: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if not isfinite(out):
        raise ValueError(error)
    return out


def _clip_probability(value: float) -> float:
    return min(1.0 - 1e-9, max(1e-9, value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def _grouped_logistic(rows: list[tuple[int, float, float]]) -> tuple[float, float] | None:
    """Return grouped-binomial recalibration intercept and slope.

    Each row is (n, mean_probability, empirical_rate). Newton updates solve the
    two-parameter binomial score equations. Singular or non-convergent evidence
    fails closed by returning None.
    """
    if len(rows) < 2:
        return None
    a, b = 0.0, 1.0
    for _ in range(100):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for n, probability, empirical_rate in rows:
            x = log(_clip_probability(probability) / (1.0 - _clip_probability(probability)))
            fitted = _sigmoid(a + b * x)
            observed = n * empirical_rate
            residual = observed - n * fitted
            weight = n * fitted * (1.0 - fitted)
            g0 += residual
            g1 += residual * x
            h00 += weight
            h01 += weight * x
            h11 += weight * x * x
        determinant = h00 * h11 - h01 * h01
        if determinant <= 1e-12 or not isfinite(determinant):
            return None
        da = (g0 * h11 - g1 * h01) / determinant
        db = (g1 * h00 - g0 * h01) / determinant
        if not isfinite(da) or not isfinite(db):
            return None
        a += da
        b += db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            return a, b
    return None


def evaluate_calibration_truth_gate(
    evidence: Mapping[str, Any],
    *,
    min_n: int = 200,
    slope_min: float = 0.90,
    slope_max: float = 1.10,
    intercept_abs_max: float = 0.03,
    ece_max: float = 0.025,
) -> CalibrationTruthGate:
    """Evaluate SportsEdge's preregistered calibration requirements fail-closed."""
    if not isinstance(evidence, Mapping):
        raise ValueError("CALIBRATION_EVIDENCE_REQUIRED")
    try:
        declared_n = int(evidence.get("n"))
    except (TypeError, ValueError) as exc:
        raise ValueError("CALIBRATION_N_INVALID") from exc
    if declared_n < 0:
        raise ValueError("CALIBRATION_N_INVALID")
    bins = evidence.get("bins")
    if not isinstance(bins, list) or not bins:
        return CalibrationTruthGate(declared_n, None, None, None, False, "CALIBRATION_BINS_MISSING")

    grouped: list[tuple[int, float, float]] = []
    total_n = 0
    weighted_error = 0.0
    for raw in bins:
        if not isinstance(raw, Mapping):
            raise ValueError("CALIBRATION_BIN_INVALID")
        try:
            n = int(raw.get("n"))
        except (TypeError, ValueError) as exc:
            raise ValueError("CALIBRATION_BIN_N_INVALID") from exc
        if n <= 0:
            raise ValueError("CALIBRATION_BIN_N_INVALID")
        probability = _finite(raw.get("mean_probability"), "CALIBRATION_BIN_PROBABILITY_INVALID")
        empirical = _finite(raw.get("empirical_rate"), "CALIBRATION_BIN_EMPIRICAL_INVALID")
        if not 0.0 <= probability <= 1.0 or not 0.0 <= empirical <= 1.0:
            raise ValueError("CALIBRATION_BIN_RATE_OUT_OF_RANGE")
        total_n += n
        weighted_error += n * abs(empirical - probability)
        grouped.append((n, probability, empirical))
    if total_n != declared_n:
        raise ValueError("CALIBRATION_BIN_COUNT_MISMATCH")

    ece = weighted_error / total_n if total_n else None
    fit = _grouped_logistic(grouped)
    if declared_n < min_n:
        return CalibrationTruthGate(declared_n, fit[0] if fit else None, fit[1] if fit else None, ece, False, "CALIBRATION_SAMPLE_BELOW_MINIMUM")
    if fit is None or ece is None:
        return CalibrationTruthGate(declared_n, None, None, ece, False, "CALIBRATION_RECALIBRATION_UNIDENTIFIED")
    intercept, slope = fit
    if not slope_min <= slope <= slope_max:
        return CalibrationTruthGate(declared_n, intercept, slope, ece, False, "CALIBRATION_SLOPE_OUT_OF_RANGE")
    if abs(intercept) > intercept_abs_max:
        return CalibrationTruthGate(declared_n, intercept, slope, ece, False, "CALIBRATION_INTERCEPT_OUT_OF_RANGE")
    if ece > ece_max:
        return CalibrationTruthGate(declared_n, intercept, slope, ece, False, "CALIBRATION_ECE_EXCEEDS_LIMIT")
    return CalibrationTruthGate(declared_n, intercept, slope, ece, True, "PASS")

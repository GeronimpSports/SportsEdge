"""Unactivated ordered parallelism for the exact NFL V2J runtime cache.

Each held-out game is an independent readout after its walk-forward fold model has
been fitted.  This helper only distributes those independent game readouts across
processes and returns results in the original input order.  The per-game arithmetic
is delegated unchanged to ``market_readout_exact_cached``.

This module is runtime infrastructure only.  It is not imported by the frozen V2J
first-readout script/workflow and grants no predictive, Model_P, promotion, RUN IT,
staking, OFFICIAL, or rerun authority.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Any, Iterable, Mapping

from .m2_v2j_runtime_cache import market_readout_exact_cached


_WORKER_MODEL: Any | None = None


class NFLV2JOrderedParallelError(ValueError):
    pass


def _initialize_worker(model: Any) -> None:
    global _WORKER_MODEL
    _WORKER_MODEL = model


def _readout_worker(row: dict[str, Any]) -> dict[str, Any]:
    if _WORKER_MODEL is None:
        raise NFLV2JOrderedParallelError("NFL_V2J_PARALLEL_WORKER_MODEL_MISSING")
    return market_readout_exact_cached(_WORKER_MODEL, row)


def ordered_parallel_market_readouts_exact_cached(
    model: Any,
    rows: Iterable[Mapping[str, Any]],
    *,
    max_workers: int,
) -> tuple[dict[str, Any], ...]:
    """Evaluate held-out games concurrently while preserving row/result order.

    ``ProcessPoolExecutor.map`` yields results in input order even when workers
    finish out of order.  No cross-game probability reduction occurs here, so the
    frozen floating-point accumulation order inside every game is unchanged.
    Worker exceptions propagate and fail closed.
    """
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
        raise NFLV2JOrderedParallelError("NFL_V2J_PARALLEL_WORKER_COUNT_INVALID")

    ordered_rows = tuple(dict(row) for row in rows)
    if not ordered_rows:
        return ()
    if max_workers == 1 or len(ordered_rows) == 1:
        return tuple(market_readout_exact_cached(model, row) for row in ordered_rows)

    with ProcessPoolExecutor(
        max_workers=min(max_workers, len(ordered_rows)),
        initializer=_initialize_worker,
        initargs=(model,),
    ) as executor:
        return tuple(executor.map(_readout_worker, ordered_rows, chunksize=1))

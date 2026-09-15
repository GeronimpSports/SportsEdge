from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import PostgamePipeline
from .providers import EspnPublicProvider, FixtureProvider
from .store import JsonJobStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous postgame video factory V0")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="Path to game fixture JSON")
    source.add_argument("--espn-date", help="Zero-key ESPN scan date, YYYYMMDD")
    parser.add_argument("--team", help="Optional team filter for ESPN mode")
    parser.add_argument("--state-dir", default=".postgame_state", help="Persistent job-state directory")
    parser.add_argument("--approve", action="store_true", help="Approve jobs that reach READY_FOR_APPROVAL")
    args = parser.parse_args()

    if args.fixture:
        provider = FixtureProvider(args.fixture)
    else:
        provider = EspnPublicProvider(date=args.espn_date, team=args.team)
    pipeline = PostgamePipeline(JsonJobStore(Path(args.state_dir)), provider)

    new_jobs = pipeline.scan_for_final_games()
    jobs = new_jobs or pipeline.store.all()
    for job in jobs:
        pipeline.run_until_blocked(job)
        print(f"{job.game.away_team} @ {job.game.home_team}: {job.state.value} ({job.job_id})")
        if args.approve and job.state.value == "READY_FOR_APPROVAL":
            pipeline.approve(job)
            print(f"approved -> {job.state.value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

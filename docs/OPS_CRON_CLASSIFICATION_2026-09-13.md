# Scheduled-workflow classification — 2026-09-13

Policy: cron is reserved for irreversible or PIT-sensitive evidence collection that cannot survive seven days without evidence loss.

## Dispatch/event-only
- bb-v6-settlement.yml — objective settlement/recomputation from durable capture state.
- nrfi-v6-settlement.yml — objective settlement/recomputation from durable capture state.
- v7-shadow-cycle.yml — research shadow evaluation; source state can be rebuilt.
- ufc-full-model.yml — model rebuild/card execution; not immutable PIT capture.
- daily-operations-digest.yml — reporting only.
- football-nfl-real-history-audit.yml — public historical audit, fully reproducible.
- football-vsin-contest-context.yml — Layer-B/context-only collection with no promotion authority; not reserved model evidence.
- nfl-v2g-prospective-outcome-capture.yml — objective outcomes are recoverable after the fact.
- statcast-daily-refresh.yml — refresh/cache job; historical Statcast source is recoverable.

## Keep scheduled / explicitly allow
- nfl-v2g-prospective-prediction-capture.yml — first-write forward prediction evidence; no backfill substitute.
- mlb-pit-lineup-starter-archive.yml — timestamped pregame lineup/starter archive used for PIT evidence.
- mlb-prop-pit-archive.yml — timestamped pregame prop quote archive; missed windows are irreversible.
- mlb-game-context-refresh.yml — preserve until context consumers are proven independent of point-in-time snapshots; fail-safe classification.

No entry in this document grants Model_P, Truth Gate, promotion, staking, or OFFICIAL authority.

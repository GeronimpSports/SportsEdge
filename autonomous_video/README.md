# Autonomous Postgame Football Video Factory — V0

This is the first executable backbone for the project.

## What V0 proves

- detects a game marked FINAL
- creates exactly one durable production job for that game
- moves the job through explicit pipeline states
- persists state after every stage
- defines contracts for analysis, evidence-backed scripting, media matching, rendering, and QA
- stops at `READY_FOR_APPROVAL`
- requires explicit approval before `PUBLISHED`
- keeps a hard footage-rights gate in the pipeline
- includes a CFBD adapter for real data once `CFBD_API_KEY` is supplied

V0 intentionally does **not** spend money on AI/video APIs and does not pretend that a dry-run render is a finished video.

## Run the deterministic proof

```bash
python -m autonomous_video.cli \
  --fixture autonomous_video/fixtures/ou_michigan_2026.json \
  --state-dir /tmp/postgame_state
```

Expected terminal state: `Oklahoma @ Michigan: READY_FOR_APPROVAL`.

Add `--approve` to exercise the one-click approval boundary.

## Production integration order

1. CFBD final-game polling + full play ingestion
2. normalized play/evidence schema
3. specialist football-analysis agents
4. claim/evidence reconciliation
5. script generator
6. rights-approved footage ingestion
7. Gemini/TwelveLabs indexing and exact clip matching
8. voice + telestration + programmatic render
9. rendered-video QA and repair loops
10. one-click YouTube publication

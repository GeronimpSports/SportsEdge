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
- can synchronize two real camera angles around the same snap without manual timestamps
- rejects one-frame scene cuts as snap candidates by requiring sustained motion
- chooses wide/end-zone/broadcast cameras from the analysis intent
- can render a multi-angle proof with programmatic telestration and an optional narration track

## Multi-angle proof result

The Oregon sample proof used separate wide and end-zone clips of the same play. The snap detector found a 5.2-second offset with 0.788 confidence, then rendered a wide → end-zone → wide sequence with overlays and narration. Sample footage itself is intentionally not stored in this repository.

## Run the deterministic pipeline proof

```bash
python -m autonomous_video.cli \
  --fixture autonomous_video/fixtures/ou_michigan_2026.json \
  --state-dir /tmp/postgame_state
```

Expected terminal state: `Oklahoma @ Michigan: READY_FOR_APPROVAL`.

## Run the multi-angle media proof

Requires FFmpeg, NumPy, Pillow, and optionally `edge-tts` for zero-key prototype narration.

```bash
python scripts/render_multiview_proof.py \
  --wide /path/to/wide.mp4 \
  --end-zone /path/to/end_zone.mp4 \
  --narration-text "Explain the play here." \
  --output /tmp/proof.mp4
```

## Production integration order

1. CFBD/fallback final-game polling + full play ingestion
2. normalized play/evidence schema
3. specialist football-analysis agents
4. claim/evidence reconciliation
5. evidence-bound script generator
6. footage ingestion + per-play multi-angle synchronization
7. broadcast/All-22/end-zone camera direction from analysis intent
8. player-aware telestration and production voice provider
9. rendered-video QA and repair loops
10. one-click YouTube publication

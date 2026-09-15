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
- can identify the quarterback from formation structure and team color
- can keep moving telestration attached using visual tracking plus detector-based re-identification
- hides tracking graphics when identity confidence is insufficient instead of circling the wrong player
- can infer OL, eligible receivers/backs, DL, LB, safety, and DB groups from pre-snap formation geometry
- can select a role such as `ELIGIBLE`, `LB`, or `SAFETY` and hand that target to the moving-telestration tracker

## Multi-angle proof result

The Oregon sample proof used separate wide and end-zone clips of the same play. The snap detector found a 5.2-second offset with 0.788 confidence, then rendered a wide → end-zone → wide sequence with overlays and narration. Sample footage itself is intentionally not stored in this repository.

## Player-aware telestration proof

The Oregon end-zone sample automatically identifies the quarterback from the offensive formation, tracks him frame-to-frame, and re-identifies him after traffic causes ordinary trackers to switch identities. A rendered 3.8-second proof kept the moving circle/arrow attached to the actual quarterback for 108 frames and deliberately hid the marker for 7 uncertain frames.

The first two simpler approaches were rejected during visual QA because they jumped to Colorado defender #92 during a collision. The current hybrid tracker uses team-color validation, motion continuity, periodic person detection, and confidence-gated hiding/reacquisition.

## Formation-role proof

Using the synchronized Oregon wide angle roughly 1.2 seconds before the snap, the formation classifier automatically produced:

- 5 offensive linemen
- 5 eligible offensive players
- 4 defensive linemen
- 2 linebackers
- 2 safeties
- 5 other defensive backs

The classifier first finds the five-man offensive-line geometry, uses that line as the line-of-scrimmage coordinate system, then classifies defenders by depth and width relative to it.

A four-second receiver-role render tracked its selected eligible receiver for 121/121 frames with no hide. Defensive role tracking is confidence-gated: linebacker and safety markers intentionally disappear during ambiguous traffic rather than jumping to the wrong team/player. Exact defender identity through pileups remains a next-stage problem rather than being treated as solved.

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

## Run the player-tracking proof

Requires FFmpeg, NumPy, `opencv-contrib-python-headless`, `ultralytics`, and a compatible person-detection model. Model weights and sample footage are intentionally not committed.

```bash
python scripts/render_player_tracking_proof.py \
  --video /path/to/end_zone.mp4 \
  --snap 3.5 \
  --output /tmp/player_track.mp4
```

## Production integration order

1. CFBD/fallback final-game polling + full play ingestion
2. normalized play/evidence schema
3. specialist football-analysis agents
4. claim/evidence reconciliation
5. evidence-bound script generator
6. footage ingestion + per-play multi-angle synchronization
7. broadcast/All-22/end-zone camera direction from analysis intent
8. formation-role recognition + role-aware telestration
9. jersey/player identity resolution across camera angles and occlusions
10. production voice provider and richer analytics graphics
11. rendered-video QA and repair loops
12. one-click YouTube publication

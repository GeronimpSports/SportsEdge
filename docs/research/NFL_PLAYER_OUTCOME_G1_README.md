# NFL Player Outcome Engine G1

Research-only NFL player outcome probability engine. This lane is deliberately isolated from production runtime and market pricing.

## Current scope

- Receptions baseline count distributions.
- Prior-game-only player features using stable player IDs.
- Chronological walk-forward evaluation only.
- Deterministic fixture replay.
- No sportsbook prices, external prediction values, or random train/test splits.

## Next research targets

1. Receiving-yard compound count x efficiency distributions.
2. Rushing-yard volume x efficiency distributions.
3. Passing-yard attempts x completion/efficiency distributions.
4. Touchdown opportunity/share engine.
5. Calibration and forward evidence.

## Authority

This branch does not alter `config/football_prop_engine_surface.json`. NFL props remain `NO_ENGINE` until independently validated and separately promoted through the existing certification path.

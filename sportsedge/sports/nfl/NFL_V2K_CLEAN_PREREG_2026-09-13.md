# NFL V2K — Clean Football-Native Candidate Preregistration

Status: PREREGISTERED_RESEARCH_ONLY
Authority: NO Model_P / NO promotion / NO staking / NO OFFICIAL
Implementation status: NOT YET ADMITTED TO REPO

## Purpose
V2K is the next materially distinct NFL game-market candidate. It is not a retune of M1/M2/V2G/V2J. It combines three predeclared components: (1) a football-native drive model, (2) hierarchical partial pooling for team strength, and (3) one joint final-score distribution with explicit signed key-number validation.

## Architecture frozen before implementation
1. **Hierarchical strength layer**
   - Team offense/defense/drive components use partial pooling with shrinkage derived from estimated variance components.
   - Small-sample teams shrink more strongly toward league mean than large-sample teams.
   - Unknown teams return the league mean; no invented rating.
   - No sportsbook or closing-line feature may enter estimation.

2. **Football-native drive layer**
   - Simulate possessions, drive outcomes, scoring conversions and final-game state rather than regressing box-score aggregates directly to margin.
   - Drive taxonomy must distinguish TD, FG, turnover, punt/other, safety and explicitly modeled exceptional scores.
   - Endgame behavior may create key-number concentration only through football mechanisms learned from training data. Hard-coded coefficients may exist only in local demonstrations and MUST NOT be used in untouched evaluation.
   - Tied-game winning-FG behavior, trailing-score-state behavior, overtime and end-of-half/game truncation must be explicit and versioned.

3. **Joint distribution layer**
   - One deterministic, versioned path set produces ML, spread, total and team-total probabilities.
   - Push probability remains explicit.
   - Signed margin mass at -7, -3, +3 and +7 is evaluated against an independently frozen empirical historical table.
   - No post-readout redistribution, bonus mass, rounding hack or coefficient change may target key-number residuals.

## Empirical signed-key prerequisite
Untouched V2K evaluation is BLOCKED until `NFL_V2K_EMPIRICAL_KEY_REFERENCE_V1.json` has status `FROZEN_READY`, includes real historical-game source provenance and SHA256 bindings, and contains signed empirical probabilities for -7, -3, +3 and +7. Placeholder or hand-entered stand-ins are forbidden as evaluation evidence.

Frozen tolerance after reference creation: absolute error <= 0.005 at every signed key. The empirical table itself may not be rebuilt after seeing V2K untouched results.

## Attempt budget
Candidate family: `NFL_V2K_DRIVE_HIERARCHICAL_JOINT_G1`
Maximum development attempts before first untouched readout: **5**.
An attempt is consumed whenever a materially different fitted specification is evaluated on the preregistered development/validation window. Pure bug fixes that restore the preregistered computation without changing model behavior do not consume an attempt, but must be documented.

The untouched readout is single-shot. Once read, V2K is frozen PASS or FAIL. Any response to untouched results requires a new candidate identity and fresh evidence.

## Evidence isolation
- V2J untouched values may not be used for V2K tuning.
- 2026 remains unavailable as a clean final holdout for V2K; any 2026 use is shadow/archive only under existing ownership rules.
- Any previously exposed season is labeled exposed/non-final and cannot be represented as untouched.
- No market price may be used as Model_P input or as a target for parameter fitting.

## Evaluation
Chronological/walk-forward only. Before first untouched readout, freeze folds, source manifests, feature allowlists, RNG/version/seed policy, simulation count and all thresholds.

Report at minimum: margin/total predictive error, ML/spread/total probability calibration, Brier/log loss where applicable, calibration slope/intercept, ECE, fold stability, and signed key-number mass at -7/-3/+3/+7.

Calibration cannot rescue predictive failure; predictive success cannot rescue key-number failure; key-number success cannot rescue calibration failure.

## Promotion boundary
A model-validity PASS would only establish candidate Model_P eligibility for the exact frozen artifact if the registry explicitly binds it. It does not establish betting promotion, OFFICIAL status or staking authority. Those still require the separate Truth Gate, market evidence, prospective CLV/performance, sample minimums and frozen floors.

## Player props
No NFL player-prop authority is granted by V2K. Player props remain on their separate volume -> efficiency -> joint distribution -> TD/PIT -> chronological validation -> market-binding path.
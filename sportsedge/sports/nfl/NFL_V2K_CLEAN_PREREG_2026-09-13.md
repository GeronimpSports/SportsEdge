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
Untouched V2K evaluation is BLOCKED until `NFL_V2K_EMPIRICAL_KEY_REFERENCE_V1.json` has status `FROZEN_READY`, includes real historical-game source provenance and SHA256 bindings, and contains signed empirical probabilities plus per-key uncertainty for -7, -3, +3 and +7. Placeholder or hand-entered stand-ins are forbidden as evaluation evidence.

The reference semantics are frozen before construction:
- **Window:** NFL regular seasons 2018 through 2025 inclusive. This deliberately prefers a post-2018 kickoff-rule regime over the larger 1999-2025 aggregate already observed elsewhere. The smaller sample is accepted in exchange for less regime mixing.
- **Sign convention:** margin = official-schedule home final score minus official-schedule away final score. Positive margins are home wins; negative margins are away wins.
- **Neutral sites:** included, using the official schedule home/away designation. No venue-based sign reassignment is permitted.
- **Overtime:** included. The reference quantity is the final score including overtime, because V2K itself resolves ties through overtime. Regulation-only margin is not an admissible substitute.
- **Season class:** REG only. Postseason games require a separately versioned reference if later needed.

Frozen tolerance: absolute error <= 0.005 at every signed key. That tolerance is intentionally conservative relative to expected reference sampling noise and may not be widened after candidate results are observed. The table itself may not be rebuilt after seeing V2K untouched results.

Uncertainty must be reported separately at every key: exact count, empirical probability, standard error `sqrt(p(1-p)/n)`, and two-sided 95% Wilson score interval. Pooling uncertainty across the four keys is forbidden. The confidence interval is interpretive only; it does not create an escape hatch from the 0.005 gate.

The reference window is immutable for V1. Silently appending future seasons is forbidden. A material NFL scoring/overtime rules change, or any decision to extend the end season, requires a new reference version rather than mutation of V1.

## Structural improvement gate
V2K is not allowed to pass by repairing only the visible key-number defect. Before candidate readout, the frozen NFL M2 control must have provenance-bound control metrics under the same evaluation contract.

Two distinct dimensions must both improve strictly versus that frozen control:
1. **Calibration slope:** `abs(slope - 1.0)` must be lower than the control's value.
2. **Signed key-number shape:** RMSE across the four signed masses (-7, -3, +3, +7) versus the frozen empirical reference must be lower than the control's value.

Improvement in only one dimension is a FAIL. In addition, every candidate key must still satisfy the absolute 0.005 per-key tolerance. This prevents a candidate from being tuned to the key-number gate while leaving the probability layer structurally overconfident, or vice versa.

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

Report at minimum: margin/total predictive error, ML/spread/total probability calibration, Brier/log loss where applicable, calibration slope/intercept, ECE, fold stability, and signed key-number mass at -7/-3/+3/+7 with per-key counts and uncertainty.

Calibration cannot rescue predictive failure; predictive success cannot rescue key-number failure; key-number success cannot rescue calibration failure. The structural-improvement gate additionally requires strict improvement over the frozen M2 control in both calibration-slope error and signed-key RMSE.

## Promotion boundary
A model-validity PASS would only establish candidate Model_P eligibility for the exact frozen artifact if the registry explicitly binds it. It does not establish betting promotion, OFFICIAL status or staking authority. Those still require the separate Truth Gate, market evidence, prospective CLV/performance, sample minimums and frozen floors.

## Player props
No NFL player-prop authority is granted by V2K. Player props remain on their separate volume -> efficiency -> joint distribution -> TD/PIT -> chronological validation -> market-binding path.

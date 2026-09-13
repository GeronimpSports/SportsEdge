# NFL V2K — Football-Native Drive/Score Candidate Preregistration

Status: PREREGISTERED_RESEARCH_ONLY
Authority: NO Model_P / NO promotion / NO staking / NO OFFICIAL
Parent evidence: V2J first readout is frozen rejection evidence and MUST NOT be used for V2K tuning.

## Hypothesis
V2J's joint-score distribution failed the frozen signed key-margin mass tolerance. V2K is a materially different generative architecture: it models possessions, starting field position and football-native drive outcomes, then simulates final scores using discrete scoring events and shared game state.

## Frozen source contract
Historical play-by-play/drive inputs must be PIT-safe and version-pinned. nflverse/nflfastR is the preferred public source family. Every acquired raw object must be cached and recorded with source URL/identifier, retrieval timestamp, season/week scope, byte SHA256 and parser/code SHA. No sportsbook prices, betting splits, capper opinions, 2026 forward outcomes or postgame information available after the prediction timestamp may enter model fitting or candidate selection.

## Drive taxonomy
Each offensive possession must resolve deterministically to one primary terminal class: TD, FG, TURNOVER, PUNT_OR_OTHER. Exceptional scoring is handled separately and explicitly: PAT, two-point try, safety, defensive TD, special-teams return TD and end-of-half/game truncation. Unknown/ambiguous drive parsing is BLOCKED, not silently coerced.

## Generative components
1. Drive-count/pace model for expected possessions by team/game.
2. Starting-field-position distribution conditional only on PIT-safe state.
3. Drive-outcome probability model using training-only data.
4. Scoring conversion layer for TD/FG/PAT/2PT/safety/defensive-ST events.
5. Shared game-state latent/regime so home and away scoring are correlated through pace, possession and state; independent team Poisson scores are prohibited.
6. Deterministic Monte Carlo joint final-score simulator with frozen RNG algorithm, seed policy and simulation count.

## PIT/train-serve contract
The exact feature builder used in historical evaluation must be the serving feature builder. Tests must prove future-row invariance, prediction-time cutoffs, source-field allowlisting, stable missingness behavior and identical train/serve transformations. Missing required features fail closed.

## Evaluation
Temporal/season-forward only; no random game split. Evaluation seasons/folds and all thresholds must be fixed before the first untouched readout. Report predictive score/margin/total metrics, probability calibration (including Brier/log loss where applicable, calibration slope/intercept and ECE), fold stability and signed empirical-vs-simulated margin mass at -7, -3, +3, +7.

Frozen key-number requirement: max absolute error <= 0.005 at every signed key. No post-hoc redistribution, rounding hack, mixture weight adjustment or calibration step may target the untouched key-number results after readout.

Calibration pass cannot rescue predictive failure; predictive pass cannot rescue calibration failure; neither can rescue key-number failure.

## Market derivation if and only if model-validity gates pass
ML, spread, game total, home team total and away team total must all be derived from the SAME frozen joint-score distribution. Push probability must be retained for integer lines. No independent market-specific probability model may contradict the joint distribution.

## Evidence boundary
Before reading untouched results, bind this preregistration, implementation/config hashes, source manifest, fold definition, feature allowlist, RNG/version/seed policy and evaluation thresholds to one candidate identity. The first untouched result is immediately frozen PASS or FAIL. A failed V2K cannot be retuned against that readout; revision requires a new candidate identity and genuinely fresh untouched evidence.

## Promotion boundary
A model-validity PASS may establish genuine game Model_P authority only if the authoritative registry explicitly binds the exact passing artifact. It does NOT by itself establish betting promotion/OFFICIAL. Market-specific contemporaneous price evidence, prospective CLV/performance, sample requirements and the frozen Truth Gate remain separately required.

## Props
Player props are not authorized by this preregistration. After a genuine game Model_P exists, existing prop candidates may be ported to the authoritative lineage. Each prop family requires its own PIT player/role/availability inputs, temporal calibration and evidence lane. One-sided props may compute EV from genuine prop Model_P plus offered price while no-vig market probability remains UNAVAILABLE_ONE_SIDED when the No side is absent.

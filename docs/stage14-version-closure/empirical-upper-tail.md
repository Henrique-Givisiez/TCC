# Empirical upper-tail policy v1

Use `EmpiricalUpperTail`, `StrictUpperTail` and the same
`upper_tail_spec(alpha=...)` through `pipeline.calibrate` and `pipeline.decide`.
The pipeline checks CALIBRATION roles, TEST isolation, source hashes and matching
detector/configuration, feature and baseline; it selects the approved temporal
interval before calling the calibrator. Scores retain causal history from the
run start. `CalibrationScores.seed` carries verified campaign metadata, with
`None` reserved for unbound development fixtures. Callbacks never receive paths
or labels. No simulator, detector, fitting or evaluator behavior changes.

Alpha must be exact decimal text, Decimal or Fraction, with 0 < alpha < 1;
binary floats are rejected. Configuration stores the canonical reduced rational.
For N available finite scores sorted ascending, compute q=1-alpha exactly and
j=ceil((N-1)*q), zero-based, then threshold=s[j]. There is no interpolation or
library quantile dependency. N=0 fails; N=1 and constant samples are valid.
Unavailable scores are excluded and counted independently for every run.

The global threshold is shared across runs. Calibration parameters record N, j,
threshold, counts below/equal/above and realized FPR (also exact numerator and
denominator), plus candidate/valid/unavailable counts and FPR per run/seed.
A run with no available score has undefined/null FPR. Alpha is a nominal benign
window-level target; ties and finite sample order statistics may yield lower FPR.
No adjustment equalizes runs or forces realized FPR to alpha.

A decision is positive iff score > threshold. Equality is negative. Missing
remains unavailable. Immutable threshold state adds no confirmation, hysteresis,
cooldown or history. The score's causal availability timestamp is preserved.
Existing artifact publication records class/version/configuration/source hashes.

The campaign manifest, rather than the algorithm, declares alpha=0.01 primary,
0.005/0.02 sensitivity; Z-score and CoV upper-tail; CoV L=6 primary, L=3/12
sensitivity; interval [48,360), Delta=1 s. Sensitivities cannot replace primary
settings after observation. TEST remains LOCKED. Operational policy materializes
only after the reviewed commit and clean-HEAD environment/binding capture.

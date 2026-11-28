# lc_calib: first LeetCode calibration (2026-11-21). Superseded by `results/lc_calib2/`

The model calls in `lc_calib_calls.jsonl` are real, but the outcomes in `lc_calib_calib.jsonl` and
`lc_calib_run.txt` were graded with three bugs in `lcb.py` that have since been fixed:

- the builtin `pow` was shadowed by `math.pow`, so correct code using three-argument `pow` failed (3 submissions);
- decimal answers were compared exactly instead of with LeetCode's 1e-5 tolerance (2 submissions);
- time limits were wall-clock, not CPU time.

Regraded with the fixed grader, 5 of the 18 failures become passes: easy 17/17 and 17/17
(thinking off and on), medium 25/26 and 23/26, hard 13/20 and 18/20. Use `results/lc_calib2/`.

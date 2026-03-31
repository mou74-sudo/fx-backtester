# Testing

`fx-backtester` has four test layers:

## 1) Unit / component tests
These lock small pieces in isolation: spec validation, data loading/quality, formalizer parsing, reviewer grading, and similar narrow behaviours.

## 2) Integration / smoke tests
These exercise the end-to-end pipeline from validated spec to run artifacts. They check that the main v1 path still works and that core artifact files are written.

## 3) Golden example tests
These pin the documented example flows so the CLI, run-label handling, and example-backed outputs stay stable for the frozen v1 workflow.

## 4) Post-v1 pressure regression tests
`tests/test_post_v1_pressure.py` adds broader regression coverage around the frozen v1 boundary.

It protects three things:
- unsupported request rejection boundaries
- accepted-but-thin strategy downgrade behaviour
- cross-artifact consistency across verdict, reviewer summary, analysis summary, memo, summary, and trades ledger

Some thin-strategy regression tests are intentionally fixture-sensitive. That is deliberate: v1 scope is frozen, so if the example-backed outcomes change from zero-trade or one-trade cases, the regression should fail and force a conscious review.

This file is documentation only. It does not change runtime logic, reviewer logic, benchmark logic, or artifact behaviour.

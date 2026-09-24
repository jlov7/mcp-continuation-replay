# Guarded stdio completion matrix

Source commit: `3db5a1d551c0000c1288adb71cbf22bab2816c2c`. Frozen protocol commit: `a529c959f990520857f5644b21e4ff2531bed7c9`.
Requested 12; executed 12; passed 12.

| Case | Expected classification | Status | SQLite issues | Wire replies |
|---|---|---|---:|---:|
| 01 | stored_result_one_effect | pass | 1 | 4 |
| 02 | unknown_no_retry | pass | 0 | 2 |
| 03 | reconciled_applied_one_effect | pass | 1 | 5 |
| 04 | conflict_before_second_effect | pass | 1 | 4 |
| 05 | conflict_before_second_effect | pass | 1 | 6 |
| 06 | unauthorized_not_equivalent | pass | 1 | 7 |
| 07 | write_rejected_observe_without_fresh_write_authority | pass | 1 | 6 |
| 08 | joined_one_apply_one_replay_one_effect | pass | 1 | 6 |
| 09 | unknown_then_authoritative_applied_no_redispatch | pass | 1 | 4 |
| 10 | valid_token_rejected_after_retention_tombstone_retained | pass | 1 | 9 |
| 11 | unsupported_rejected_no_effect | pass | 0 | 4 |
| 12 | durable_partial_no_first_effect_replay | pass | 1 | 4 |

Derived from `results.jsonl`. Raw transcripts and SQLite files remain in each case directory.

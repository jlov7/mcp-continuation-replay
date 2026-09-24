# TypeScript v2 guarded stdio matrix

Source commit: `c6e72f00ffee3e4740740000fd83097d33a058a8`. Frozen additive protocol: `5af1fb030f9dae00b4ed336f0bd99237b23d9b05`.
Same Python SQLite bridge; TypeScript SDK wire and state handling are exercised directly.

| Case | Expected classification | Status | SQLite issues | Wire replies |
|---|---|---|---:|---:|
| 01 | stored_result_one_effect | pass | 1 | 4 |
| 02 | unknown_no_retry | pass | 0 | 4 |
| 03 | reconciled_applied_one_effect | pass | 1 | 5 |
| 04 | conflict_before_second_effect | pass | 1 | 4 |
| 05 | conflict_before_second_effect_and_tamper_rejected | pass | 1 | 6 |
| 06 | principal_bound_unauthorized_alice_observation | pass | 1 | 9 |
| 07 | authority_expired_write_rejected_observe_without_fresh_write_authority | pass | 1 | 6 |
| 08 | concurrent_one_apply_one_replay_one_effect | pass | 1 | 6 |
| 09 | hard_exit_unknown_then_authoritative_applied_no_redispatch | pass | 1 | 4 |
| 10 | retention_rejected_tombstone_and_separate_sdk_expiry | pass | 1 | 9 |
| 11 | stripped_state_rejected_valid_initial_round | pass | 0 | 4 |
| 12 | durable_partial_failed_compensation_no_repeat_first_effect | pass | 1 | 6 |

Derived from `results.jsonl`; verify with `python -m scripts.run_typescript_guarded_matrix --verify ATTEMPT_DIR`.

# Experimental application profile — continuation replay and uncertain effects

> This is desired application behavior, not normative MCP behavior. MCP
> 2026-07-28 leaves single-use/at-most-once enforcement to servers that require
> it. See `CURRENT-FINDINGS.md`.

**Status:** implemented and tested against `mcp==2.2.0` (spec `2026-07-28`). Not normative. Not an MCP SEP.

This is the frozen protocol this repository implements and tests. Changes to it after Milestone A require a written entry in `STATUS.md` with the reason.

## 1. Logical model

An **operation** is not a network attempt. Equivalence binds:

```
principal  ⊗  tool_id/version  ⊗  canonical(arguments)
           ⊗  continuation_state
           ⊗  input_responses
```

Each of those five components participates in the fingerprint under a declared
canonicalization. Opaque or sensitive state is bound through a caller-supplied
secret key or a server-side authenticated reference. There is no public default
key. Digests still leak equality and must not be written to public logs when
that equality is sensitive.

We deliberately do **not** invent a shared semantic-equivalence oracle. **Byte equality under a specified canonicalization** is narrower, testable, and sufficient.

A materially changed approval, quote, principal, or answer is not a silent equivalent retry. It is a conflict.

## 2. Two orthogonal state axes

Do not collapse these.

**Submission state** — `not_admitted` | `admitted` | `unknown`

**Effect observation** — `not_applied` | `applied` | `partial` | `unknown` (within a declared observation scope)

Plus:
- **Reconciliation**: `available` | `unavailable` — produces *fresh evidence*, never a model assertion.
- **Repeat execution**: permitted only under an explicit backend-supported replay contract **and** current authority checks. Absence of a reply alone never permits replay.

`unknown` is not a fifth way of claiming success. It exists to **prevent an unsafe fresh write** while allowing bounded read-only reconciliation.

## 3. Interfaces (conceptual; resolve real signatures at Milestone A)

```python
fingerprint(logical_request) -> OperationFingerprint
dispatch(request, fingerprint) -> AttemptRecord
observe(operation_id, authority) -> EffectObservation     # read-only
decide_recovery(attempt, observation, backend_contract) -> RecoveryDecision
```

## 4. The 12 discriminating cases (Milestone C target)

| # | Case | Required behavior |
|---|---|---|
| 1 | Initial round requests input; continuation commits; identical retry | Same logical result returned |
| 2 | Initial round requests input; continuation never admitted | Timeout remains `unknown` until checked |
| 3 | Continuation commits, reply disappears; replay | **No second record** |
| 4 | Same identifier, changed `inputResponses` | **Conflict before dispatch** |
| 5 | Same identifier, changed `requestState` | **Conflict before dispatch** |
| 6 | Same payload, different principal | Not an authorized equivalent retry |
| 7 | Required approval expires between attempt and reconciliation | Read-back cannot become fresh write authority |
| 8 | Concurrent identical attempts | One backend effect; declared waiter/in-progress semantics |
| 9 | Crash after backend commit, before local receipt | Reconcile, or explicitly remain `unknown` |
| 10 | Key-retention window expires | No silent guarantee extension |
| 11 | Proxy removes experimental metadata | `unsupported`/`unknown`, not false conformance |
| 12 | Partial effect + failed compensation | Both records preserved, unresolved state preserved |

The matrix holds **12 semantic cases**. Generated timing schedules are repetitions/variants, **not** independent business-task diversity. Preserve denominators; do not report variants as new cases.

## 5. Unsafe control (labeled, never shipped)

A deliberate baseline that retries with a **new identity**, demonstrating duplicate execution. It exists to show the failure mode. It is a control, not a recommendation.

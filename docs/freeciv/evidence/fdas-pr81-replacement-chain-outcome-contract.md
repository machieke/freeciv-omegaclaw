# FDAS PR81 replacement-chain outcome contract

Date: 2026-08-04

## Result

PR81 passes all nine preregistered gates from clean implementation commit
`6c7cf12cba3a76d80117ef9d13fb21af9da4e031`. The deliberately reused
pathological seed `109633` completed the 160-turn horizon without resume or
infrastructure failure. It executed 408 engine actions with zero rejections
and emitted 140,411 valid events.

The persistent replacement lifecycle produced 59 durable operations, 717
terminal-chain reproposal suppressions, and 218 grounded safe-chain pairs. It
produced zero completed replacement operations. Consequently, the exact
completion-indexed outcome store is valid and unquarantined but contains zero
labels: zero pending, zero observed, zero positive, and zero negative.

That empty store is the correct result. The controller remains shadow-only, so
it cannot cause the two coordinated movement steps whose completion opens a
label. The audit neither fabricates an outcome from a proposal nor reuses the
one-step defense target.

The deterministic report is
`fdas-pr81-replacement-chain-outcome.json`, structural hash
`0f1854f437ea935a1b077fdbffa24671d4b6201f3f1de057e3e76096b405a2e2`.
A second invocation produced byte-identical JSON with SHA-256
`a0d1343fc36dc0dc4952385f4b55c60ce1324998dcb0ff95cf4707c0b6874e0d`.

## Mechanical interpretation

Focused tests establish the non-empty mechanics that the shadow run cannot
exercise: a label opens only after an operation completes its final step;
restart recovery preserves its operation/specification identity and due turn;
the 32-turn observation records each source-city, target-city, replacement,
and reinforcement conjunct; and terminal labels are idempotent and immutable.
The event surface and runtime status expose opened, pending, observed,
positive, and negative counts without truth, policy, readout, or action
authority.

The live audit establishes that this machinery is installed under the frozen
manifest capability, remains revision-current and non-authorizing, persists a
valid identity-bound store, reconciles exactly with event/status counters, and
preserves the parent replacement lifecycle/readout safety gates.

## Next boundary

The remaining bottleneck is data generation, not label definition. A bounded,
separately manifest-gated execution treatment must be able to reserve one
eligible grounded chain, revalidate and execute each authoritative step, and
continue or fail closed across snapshots. Treatment assignment and outcome
analysis must use an independent unit such as game/seed; repeated steps or
events from one chain are not independent samples.

That authority expansion must be preregistered and mechanically piloted before
any fresh confirmation cohort. It must preserve source coverage, current legal
bindings, operation-store durability, rollback/failure evidence, and the
existing scalar policy outside the selected chain.

## Claim boundary

PR81 establishes a mechanically correct, durable, completion-indexed outcome
lifecycle and its live activation. Zero completions mean it provides no chain
transition-value samples. It does not establish beneficial preference,
effective execution, causal defensive relief, score improvement, or win rate.

# FDAS PR80 replacement terminal-reproposal hardening

Date: 2026-08-04

## Result

PR80 passes all eight preregistered gates from clean implementation commit
`46cb9d1221158969dafeb63888ff5e7a535cc3a2`. The deliberately reused
pathological seed `109633` completed the 160-turn horizon without resume or
infrastructure failure. It executed 407 engine actions with zero rejections.

The persisted 32-turn logical-chain cooldown produced:

- 709 suppressed terminal-chain reproposals;
- 61 durable operations, down from 208 (70.67% reduction);
- 143,885 valid events, down from 508,032 (71.68% reduction);
- 55 distinct logical replacement keys;
- 228 grounded safe-chain pairs, so recall remained observable; and
- 61 terminal expirations with no terminal evidence deletion.

The unchanged PR77 lifecycle and PR78 readout audits both pass as the parent
mechanical gate. The operation ceiling of 80 and event ceiling of 300,000 pass
with substantial margin. The deterministic report is
`fdas-pr80-replacement-terminal-reproposal.json`, structural hash
`7a26ed8d5140d7b290138c771f87254fc7ad8896df367c6e912f59a55c88f204`.
A second invocation produced byte-identical output.

## Efficiency interpretation

Engine gameplay took 271.78 seconds, compared with 1,595.06 seconds in the
PR79 baseline run of the same seed and horizon. The event file shrank from
approximately 511 MB to 188 MB. These time and byte changes are descriptive:
host load and serialized row width are not controlled. Record and event counts
are the preregistered structural evidence.

The correction preserves the intended semantics. Active logical operations
still deduplicate without a timeout. Terminal records remain in the durable
store. Restart reloads their terminal observation turns, so it cannot erase a
cooldown. A different actor/source/target tuple remains independent, and an
exact current candidate may be proposed at the 32-turn boundary.

## Next boundary

Candidate recall and lifecycle evidence are now mechanically usable without
pathological amplification. The next scientific step is not more routing or
flow tuning. It is the previously deferred chain-completion-specific outcome
target: observation must begin when the replacement reaches the source and the
reinforcement reaches the target, rather than treating the first move as if it
were a complete defensive transition.

## Claim boundary

PR80 establishes bounded terminal-chain reproposal and reduced evidence
amplification on one known pathological seed. It does not establish portable
runtime improvement, beneficial chain transition value, preference quality,
action effectiveness, score improvement, or win rate.
